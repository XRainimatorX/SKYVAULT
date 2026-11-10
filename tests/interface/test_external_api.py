"""Phase 12 step C: the external interface over HTTP, on the world service."""

import ast
import os
from pathlib import Path

import pytest
from external_runs import SUBMISSIONS, submission
from fastapi.testclient import TestClient

from skyvault.worldservice.api import create_world_service
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import execute_job
from skyvault.worldservice.queues import InProcessQueue
from skyvault.worldservice.store import PostgresStore, SQLiteStore

SRC = Path(__file__).resolve().parents[2] / "src" / "skyvault"
POSTGRES = os.environ.get("SKYVAULT_TEST_POSTGRES")
REFERENCE = "tactical_reference_001/v0.1"


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SQLiteStore(str(tmp_path / "external.sqlite"))
    if not POSTGRES:
        pytest.skip("SKYVAULT_TEST_POSTGRES is not set (CI sets it)")
    pg = PostgresStore(POSTGRES)
    pg._run("DROP TABLE IF EXISTS jobs, results, checkpoints, job_events, conflicts")
    pg.setup()
    return pg


def service(store, started=True, policy=None):
    policy = policy or load_governance()
    queue = InProcessQueue(
        lambda job_id: execute_job(job_id, store, policy),
        policy["max_parallel_runs"],
        policy["queue_policy"],
        start=started,
    )
    return TestClient(create_world_service(store, queue, policy)), queue


@pytest.fixture
def api(store):
    client, queue = service(store)
    yield client, queue
    queue.close()


def order_of(action):
    return {k: v for k, v in action.items() if k not in ("tick", "actor_id", "system")}


def submit_actions(client, world_id, actions, system=None):
    for action in actions:
        response = client.post(
            "/action/submit",
            json={
                "world_id": world_id,
                "system": system or action["system"],
                "tick": action["tick"],
                "actor_id": action["actor_id"],
                "order": order_of(action),
            },
        )
        assert response.status_code == 202, response.json()


# ── acceptance 1, 2, 4: TAC ANGEL acts in a running world ────────────────────


def test_tac_angel_acts_in_a_world_and_gets_its_state_action_outcome(api):
    client, _ = api
    created = client.post("/world/create", json={"scenario": REFERENCE})
    assert created.status_code == 201
    world_id = created.json()["world_id"]
    submit_actions(
        client, world_id, SUBMISSIONS["tac_angel_plan"]["actions"], "TAC_ANGEL"
    )
    assert client.get(f"/run/{world_id}").json()["world"]["pending_actions"] == 3

    advanced = client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 3}).json()
    assert advanced["tick"] == 3 and advanced["pending_actions"] == 0
    live = client.get(f"/run/{world_id}/events").json()["event_memory"]
    assert any(e["source"]["system_id"] == "TAC_ANGEL" for e in live)
    client.post(f"/api/worlds/{world_id}/finish")

    sao = client.get(
        f"/run/{world_id}/state_action_outcome", params={"system": "TAC_ANGEL"}
    ).json()["state_action_outcome"]
    assert [(r["tick"], r["action"]["actor_id"]) for r in sao] == [
        (1, "red_001"),
        (2, "red_001"),
        (3, "red_001"),
    ]
    assert [r["action"]["target_location"] for r in sao] == [[1, 1], [2, 2], [3, 3]]
    everyone = client.get(f"/run/{world_id}/state_action_outcome").json()
    assert len(everyone["state_action_outcome"]) > len(sao)


def test_tac_angel_submission_with_a_world_goes_into_its_window(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    answer = client.post(
        "/scenario/submit", json=submission("TAC_ANGEL", world_id=world_id)
    ).json()
    assert answer["run_ids"] == [] and answer["submission_id"] is None
    assert [p["proposal_id"] for p in answer["proposals"]] == [
        "TAC_ANGEL:1",
        "TAC_ANGEL:2",
        "TAC_ANGEL:3",
    ]
    assert client.get(f"/run/{world_id}").json()["world"]["pending_actions"] == 3


# ── acceptance 3: NEXUS takes the whole result package ───────────────────────


def test_nexus_submits_a_task_and_takes_the_package_briefing_and_status(api):
    client, queue = api
    answer = client.post("/scenario/submit", json=submission("NEXUS"))
    assert answer.status_code == 202
    run_id = answer.json()["submission_id"]
    assert answer.json()["run_ids"] == [run_id]
    assert queue.wait_idle()

    returned = client.get(f"/submission/{run_id}").json()
    assert returned["result_package"]["evaluation_result"]["winner_or_result"] == (
        "RED_survived"
    )
    assert returned["briefing"].startswith("# SKYVAULT briefing")
    assert returned["system_status"]["lifecycle_state"] == "completed"

    run = client.get(f"/run/{run_id}").json()
    assert run["handoff"]["triggers"] == ["strategic_tradeoff"]
    assert run["handoff"]["decision_authority"] == ["NEXUS", "SOVEREIGN"]
    assert len(client.get(f"/run/{run_id}/result").json()["event_memory"]) == 97
    events = client.get(f"/run/{run_id}/events").json()
    assert len(events["event_memory"]) == 97
    assert events["job_events"][0]["message"] == "created by NEXUS"


def test_a_submission_is_returned_only_when_all_its_runs_are_done(store):
    client, queue = service(store, started=False)
    answer = client.post("/scenario/submit", json=submission("SKYFOX")).json()
    assert answer["run_ids"] == ["job_000001", "job_000002", "job_000003"]
    waiting = client.get("/submission/job_000001")
    assert (
        waiting.status_code == 409 and waiting.json()["detail"]["reason"] == "not_ready"
    )
    queue.start()
    assert queue.wait_idle()
    returned = client.get("/submission/job_000001").json()
    assert returned["mission_success_rate"] == 1.0 and len(returned["runs"]) == 3
    assert client.get("/submission/job_000002").status_code == 404
    queue.close()


def test_a_failed_run_fails_its_submission(store):
    client, queue = service(store, started=False)
    client.post("/scenario/submit", json=submission("NEXUS"))
    store.update_job("job_000001", lifecycle_state="failed", error="worker lost")
    failed = client.get("/submission/job_000001")
    assert failed.status_code == 409
    assert failed.json()["detail"] == {
        "reason": "failed",
        "detail": "job_000001 failed: worker lost",
    }
    queue.close()


# ── acceptance 5: STARTX submits branches ────────────────────────────────────


def test_startx_submits_branches_and_takes_their_comparison(api):
    client, queue = api
    run_id = client.post("/scenario/submit", json=submission("STARTX")).json()[
        "submission_id"
    ]
    direct = client.post(
        "/branch_compare/run",
        json={
            "scenario": REFERENCE,
            "source_system": "STARTX",
            "branches": SUBMISSIONS["startx_branches"]["branches"],
            "repeat_count": 5,
        },
    )
    assert (
        direct.status_code == 202
        and direct.json()["request"]["kind"] == "branch_compare"
    )
    assert queue.wait_idle()
    returned = client.get(f"/submission/{run_id}").json()
    assert [b["branch_id"] for b in returned["branches"]] == ["press", "hold"]
    stored = client.get(f"/run/{direct.json()['job_id']}/result").json()
    assert stored["branch_comparison"] == returned["branch_comparison"]


# ── acceptance 6-9, 13, 14: conflicts over HTTP ──────────────────────────────


def test_conflicting_actions_are_held_played_out_and_returned(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    submit_actions(client, world_id, SUBMISSIONS["conflicting_actions"])

    held = client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 5}).json()
    assert held["tick"] == 0 and held["awaiting_decision"] == "conflict_000001"
    again = client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 1})
    assert again.status_code == 409
    assert again.json()["detail"]["reason"] == "awaiting_decision"

    record = client.get("/conflict/conflict_000001").json()
    assert record["status"] == "awaiting_decision" and record["world_id"] == world_id
    branches = client.get("/conflict/conflict_000001/branches").json()
    assert sorted(branches["branches"]) == ["STARTX:2+HADES:3", "TAC_ANGEL:1", "none"]
    assert sorted(branches["branch_comparison"]["variants"]) == [
        "branch:STARTX:2+HADES:3",
        "branch:TAC_ANGEL:1",
        "branch:none",
    ]
    package = client.get("/conflict/conflict_000001/package").json()
    assert package["recommendation_to_nexus"]["required_decision"] is True
    assert (package["conflict_id"], package["tick"], package["status"]) == (
        "conflict_000001",
        1,
        "awaiting_decision",
    )
    assert record["handoff"]["triggers"] == ["conflicting_branches"]
    assert record["handoff"]["may_execute_final_decision"] is False


def test_skyvault_or_any_non_authority_deciding_is_refused(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    submit_actions(client, world_id, SUBMISSIONS["conflicting_actions"])
    client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 1})

    for impostor in ("SKYVAULT", "TAC_ANGEL", "STARTX", ""):
        refused = client.post(
            "/branch_conflict/resolve",
            json={
                "conflict_id": "conflict_000001",
                "branch_id": "TAC_ANGEL:1",
                "decided_by": impostor,
            },
        )
        assert refused.status_code == 403
        assert refused.json()["detail"]["reason"] == "not_an_authority"
    assert client.get("/conflict/conflict_000001").json()["status"] == (
        "awaiting_decision"
    )
    assert client.get(f"/run/{world_id}").json()["world"]["awaiting_decision"] == (
        "conflict_000001"
    )


def test_an_authority_decides_and_the_world_goes_on_with_its_branch(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    submit_actions(client, world_id, SUBMISSIONS["conflicting_actions"])
    client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 1})

    unknown = client.post(
        "/branch_conflict/resolve",
        json={
            "conflict_id": "conflict_000001",
            "branch_id": "P9",
            "decided_by": "NEXUS",
        },
    )
    assert unknown.status_code == 404
    decided = client.post(
        "/branch_conflict/resolve",
        json={
            "conflict_id": "conflict_000001",
            "branch_id": "TAC_ANGEL:1",
            "decided_by": "NEXUS",
        },
    )
    assert decided.status_code == 200
    assert (decided.json()["decided_by"], decided.json()["branch_id"]) == (
        "NEXUS",
        "TAC_ANGEL:1",
    )
    twice = client.post(
        "/branch_conflict/resolve",
        json={
            "conflict_id": "conflict_000001",
            "branch_id": "none",
            "decided_by": "SOVEREIGN",
        },
    )
    assert twice.status_code == 409
    late = client.post(
        "/branch_conflict/resolve",
        json={
            "conflict_id": "conflict_000001",
            "branch_id": "none",
            "decided_by": "SKYVAULT",
        },
    )
    assert late.status_code == 403

    moved = client.post(f"/api/worlds/{world_id}/advance", json={"ticks": 1}).json()
    assert moved["tick"] == 1 and moved["awaiting_decision"] is None
    events = client.get(f"/run/{world_id}/events").json()
    assert any(
        e["message"] == "NEXUS decided conflict_000001: branch TAC_ANGEL:1"
        for e in events["job_events"]
    )
    first = [
        (e["source"]["actor_id"], e["source"]["system_id"])
        for e in events["event_memory"]
        if e["event_type"] == "MOVE" and e["time"] == 1
    ]
    assert ("red_001", "TAC_ANGEL") in first
    # the other side of the conflict was not carried out
    assert ("red_002", "HADES") not in first


def test_unknown_conflicts_and_worlds_are_not_found(api):
    client, _ = api
    assert client.get("/conflict/conflict_000009").status_code == 404
    assert client.get("/conflict/conflict_000009/package").status_code == 404
    assert (
        client.post(
            "/branch_conflict/resolve",
            json={
                "conflict_id": "conflict_000009",
                "branch_id": "x",
                "decided_by": "NEXUS",
            },
        ).status_code
        == 404
    )
    assert client.get("/run/job_000099").status_code == 404
    assert client.get("/submission/job_000099").status_code == 404


# ── acceptance 10-12, 14: a run's own handoff ────────────────────────────────


def test_a_run_s_handoff_is_decided_only_by_an_authority(api):
    client, queue = api
    run_id = client.post("/scenario/submit", json=submission("NEXUS")).json()[
        "submission_id"
    ]
    assert queue.wait_idle()

    impostor = client.post(
        f"/run/{run_id}/decision", json={"decided_by": "SKYVAULT", "decision": "accept"}
    )
    assert impostor.status_code == 403
    empty = client.post(f"/run/{run_id}/decision", json={"decided_by": "NEXUS"})
    assert empty.status_code == 422
    decided = client.post(
        f"/run/{run_id}/decision",
        json={"decided_by": "SOVEREIGN", "decision": "accept the trade-off"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "decided"
    assert client.get(f"/run/{run_id}").json()["handoff"]["decided_by"] == "SOVEREIGN"
    again = client.post(
        f"/run/{run_id}/decision", json={"decided_by": "NEXUS", "decision": "reject"}
    )
    assert again.status_code == 409


def test_a_run_that_needs_no_decision_has_no_handoff(api):
    client, queue = api
    quiet = client.post(
        "/api/jobs",
        json={
            "kind": "scenario_run",
            "scenario": REFERENCE,
            "runtime": {"random_seed": 45},
        },
    ).json()
    assert queue.wait_idle()
    assert client.get(f"/run/{quiet['job_id']}").json()["handoff"] is None
    answer = client.post(
        f"/run/{quiet['job_id']}/decision",
        json={"decided_by": "NEXUS", "decision": "x"},
    )
    assert answer.status_code == 404


def test_a_failure_exploration_hands_its_failure_map_over(api):
    client, queue = api
    job = client.post(
        "/failure_exploration/run",
        json={"scenario": REFERENCE, "repeat_count": 1, "source_system": "NEXUS"},
    )
    assert job.status_code == 202
    assert queue.wait_idle()
    run = client.get(f"/run/{job.json()['job_id']}").json()
    assert run["lifecycle_state"] == "completed"
    if run["handoff"] is not None:
        assert run["handoff"]["failure_map"] is not None
    no_events = client.get(f"/run/{job.json()['job_id']}/state_action_outcome")
    assert no_events.status_code == 422


# ── what has no model, and malformed submissions ─────────────────────────────


def test_cyberhound_comes_back_unsupported_without_running_anything(api):
    client, _ = api
    answer = client.post("/scenario/submit", json=submission("CYBERHOUND")).json()
    assert answer["supported"] is False and answer["run_ids"] == []
    assert answer["returned"]["gaps"] == answer["gaps"]
    assert client.get("/api/jobs").json() == []


def test_malformed_submissions_and_actions_are_refused(api):
    client, _ = api
    wrong_kind = {**submission("TAC_ANGEL"), "kind": "branches"}
    assert client.post("/scenario/submit", json=wrong_kind).status_code == 422
    assert (
        client.post(
            "/scenario/submit", json={**submission("NEXUS"), "system": "SKYNET"}
        ).status_code
        == 422
    )
    lost = client.post(
        "/scenario/submit", json=submission("TAC_ANGEL", world_id="job_000042")
    )
    assert lost.status_code == 404
    assert (
        client.post("/action/submit", json={"world_id": "job_000001"}).status_code
        == 422
    )

    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    base = {
        "world_id": world_id,
        "system": "TAC_ANGEL",
        "order": {"action_type": "wait"},
    }
    assert (
        client.post(
            "/action/submit", json={**base, "tick": 0, "actor_id": "red_001"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/action/submit", json={**base, "tick": 1, "actor_id": "red_099"}
        ).status_code
        == 404
    )
    client.post(f"/api/worlds/{world_id}/finish")
    closed = client.post(
        "/action/submit", json={**base, "tick": 5, "actor_id": "red_001"}
    )
    assert closed.status_code == 409


def test_a_refused_job_fails_the_rest_of_its_submission(store):
    client, queue = service(store, started=False)
    admit = client.app.state.admit
    calls = []

    def second_refused(request, ahead=0):
        calls.append(request)
        if len(calls) == 2:
            from fastapi import HTTPException

            raise HTTPException(429, {"reason": "queue_full", "detail": "full"})
        return admit(request, ahead)

    client.app.state.admit = second_refused
    refused = client.post("/scenario/submit", json=submission("SKYFOX"))
    assert refused.status_code == 429
    (only,) = client.get("/api/jobs").json()
    assert only["lifecycle_state"] == "failed"
    assert only["error"] == "another job of its submission was refused"
    assert queue.depth() == 0
    queue.close()


def test_one_submission_s_jobs_count_against_the_queue_length_together(store):
    """Each job used to be admitted against the same depth (code review, 2026-11-09)."""
    policy = {**load_governance(), "max_queue_length": 3}
    client, queue = service(store, started=False, policy=policy)

    refused = client.post("/scenario/submit", json=submission("SKYFOX", repeat_count=5))

    assert refused.status_code == 429
    assert refused.json()["detail"]["reason"] == "queue_full"
    assert queue.depth() == 0
    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 3 and {j["lifecycle_state"] for j in jobs} == {"failed"}
    queue.close()


def test_one_submission_s_runs_count_against_max_batch_count_together(store):
    policy = {**load_governance(), "max_batch_count": 4}
    client, queue = service(store, started=False, policy=policy)

    refused = client.post("/scenario/submit", json=submission("SKYFOX", repeat_count=5))
    fits = client.post("/scenario/submit", json=submission("SKYFOX", repeat_count=4))

    assert refused.status_code == 422
    assert refused.json()["detail"]["reason"] == "batch_too_large"
    assert "5 runs" in refused.json()["detail"]["detail"]
    assert fits.status_code == 202 and len(fits.json()["run_ids"]) == 4
    assert queue.depth() == 4
    queue.close()


def test_a_refused_world_action_leaves_none_of_its_submission_queued(api):
    """The first action used to stay in the window (code review, 2026-11-09)."""
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    stray = submission("TAC_ANGEL", world_id=world_id)
    stray["content"]["actions"][1]["actor_id"] = "red_099"

    refused = client.post("/scenario/submit", json=stray)

    assert refused.status_code == 404
    assert client.get(f"/api/worlds/{world_id}").json()["pending_actions"] == 0


def test_a_malformed_later_action_takes_back_the_ones_before_it(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    broken = submission("TAC_ANGEL", world_id=world_id)
    broken["content"]["actions"][2]["target"] = "nowhere"

    refused = client.post("/scenario/submit", json=broken)

    assert refused.status_code == 422
    assert client.get(f"/api/worlds/{world_id}").json()["pending_actions"] == 0


def test_a_refused_world_action_fails_the_jobs_admitted_with_it(store, monkeypatch):
    from skyvault.interface import api as interface_api

    client, queue = service(store, started=False)
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    planned = interface_api.to_request(submission("TAC_ANGEL", world_id=world_id))
    planned["world_actions"]["actions"][0]["actor_id"] = "red_099"
    planned["jobs"] = [{"kind": "scenario_run", "scenario": REFERENCE}]
    monkeypatch.setattr(interface_api, "to_request", lambda _: planned)

    refused = client.post("/scenario/submit", json={"system": "TAC_ANGEL"})
    jobs = [j for j in client.get("/api/jobs").json() if j["job_id"] != world_id]

    assert refused.status_code == 404
    assert queue.depth() == 0
    assert [(j["lifecycle_state"], j["error"]) for j in jobs] == [
        ("failed", "its submission's world actions were refused")
    ]
    queue.close()


def test_a_refused_job_leaves_none_of_its_world_actions_queued(store, monkeypatch):
    from skyvault.interface import api as interface_api

    client, queue = service(store, started=False)
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    planned = interface_api.to_request(submission("TAC_ANGEL", world_id=world_id))
    planned["jobs"] = [{"kind": "scenario_run", "scenario": "no_such_scenario"}]
    monkeypatch.setattr(interface_api, "to_request", lambda _: planned)

    refused = client.post("/scenario/submit", json={"system": "TAC_ANGEL"})

    assert refused.status_code == 404
    assert client.get(f"/api/worlds/{world_id}").json()["pending_actions"] == 0
    assert queue.depth() == 0
    queue.close()


# ── layering ─────────────────────────────────────────────────────────────────


def test_the_simulation_never_imports_the_interface():
    for path in [SRC / "engine.py", *(SRC / "batch").rglob("*.py")]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "interface" not in (node.module or ""), path


def test_handoff_and_conflict_logic_runs_no_simulation_by_itself():
    tree = ast.parse((SRC / "interface" / "handoff.py").read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any("engine" in (m or "") or "batch" in (m or "") for m in modules)


def test_intel_with_nothing_to_map_is_answered_at_once(api):
    client, _ = api
    intel = submission("EIDEN_01", parameters=[{"world": "weather", "value": "fog"}])
    answer = client.post("/scenario/submit", json=intel).json()
    assert answer["run_ids"] == []
    assert answer["returned"] == {
        "system": "EIDEN_01",
        "supported": False,
        "gaps": [
            "world parameter weather='fog': tactical_reference_001 has no model for it"
        ],
    }


def test_a_run_s_result_waits_until_it_exists(store):
    client, queue = service(store, started=False)
    run_id = client.post("/scenario/submit", json=submission("NEXUS")).json()[
        "submission_id"
    ]
    waiting = client.get(f"/run/{run_id}/result")
    assert waiting.status_code == 409
    assert client.get(f"/run/{run_id}/events").json()["event_memory"] is None
    store.update_job(run_id, lifecycle_state="failed", error="worker lost")
    gone = client.get(f"/run/{run_id}/result")
    assert gone.status_code == 404
    assert gone.json()["detail"] == {"reason": "no_result", "detail": "worker lost"}
    queue.close()


def test_a_world_action_the_world_refuses_refuses_the_submission(api):
    client, _ = api
    world_id = client.post("/world/create", json={"scenario": REFERENCE}).json()[
        "world_id"
    ]
    stray = submission("TAC_ANGEL", world_id=world_id)
    stray["content"]["actions"][0]["actor_id"] = "red_099"
    refused = client.post("/scenario/submit", json=stray)
    assert refused.status_code == 404
    assert "red_099" in refused.json()["detail"]["detail"]


def test_a_submission_run_here_raises_when_its_job_fails():
    from skyvault.interface.api import run_submission

    lost = submission("SKYFOX", drone="red_99", repeat_count=1)
    with pytest.raises(RuntimeError, match="job_000001 failed: .*red_99"):
        run_submission(lost, SQLiteStore(), load_governance())


def test_the_script_writes_what_each_system_gets_back(tmp_path):
    import json
    import subprocess
    import sys

    done = subprocess.run(
        [
            sys.executable,
            str(SRC.parents[1] / "scripts" / "run_external.py"),
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "CYBERHOUND  0 job(s), not supported, 2 gap(s)" in done.stdout
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(
        [
            f"{s.lower()}.json"
            for s in (
                "NEXUS",
                "STARTX",
                "TAC_ANGEL",
                "EIDEN_01",
                "AEROGRID",
                "SKYFOX",
                "HADES",
                "CYBERHOUND",
                "STAR_GUARD",
            )
        ]
        + [
            "nexus_briefing.md",
            "conflict_package.json",
            "conflict_handoff.json",
            "conflict_decided.json",
        ]
    )
    decided = json.loads((tmp_path / "conflict_decided.json").read_text())
    assert decided["decided_by"] == "NEXUS" and decided["status"] == "decided"
    handoff = json.loads((tmp_path / "conflict_handoff.json").read_text())
    assert handoff["status"] == "awaiting_decision"
    assert handoff["may_execute_final_decision"] is False
