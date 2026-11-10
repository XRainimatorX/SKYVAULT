"""Phase 11 step C: the HTTP API and persistent worlds, end to end."""

import ast
import threading
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from service_data import JOBS, REDIS, job_request

from skyvault.worldservice.api import create_world_service, in_process_queue
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import execute_job
from skyvault.worldservice.queues import InProcessQueue, RQQueue
from skyvault.worldservice.store import SQLiteStore

# the store, redis_url and policy fixtures
pytest_plugins = ["service_fixtures"]

REPO_ROOT = Path(__file__).resolve().parents[2]


def service(store, policy, started=True):
    queue = InProcessQueue(
        lambda job_id: execute_job(job_id, store, policy),
        policy["max_parallel_runs"],
        policy["queue_policy"],
        start=started,
    )
    return TestClient(create_world_service(store, queue, policy)), queue


@pytest.fixture
def api(store, policy):
    client, queue = service(store, policy)
    yield client, queue
    queue.close()


def changed(policy, **changes):
    out = dict(policy)
    for key, value in changes.items():
        out[key] = {**out[key], **value} if isinstance(value, dict) else value
    return out


# ── acceptance 1-4: submit, run in the background, look up, download ────────


def test_a_submitted_run_is_run_in_the_background_and_its_result_downloaded(api):
    client, queue = api

    submitted = client.post("/api/jobs", json=job_request("reference_run"))
    assert submitted.status_code == 202
    assert submitted.json()["lifecycle_state"] == "created"
    assert queue.wait_idle()

    job = client.get("/api/jobs/job_000001").json()
    result = client.get("/api/jobs/job_000001/result").json()
    assert job["lifecycle_state"] == "completed"
    assert [e["message"] for e in job["events"]][-1] == "completed: RED_survived"
    assert result["reproducibility"]["output_hash"].startswith("7debca2af332")
    assert (
        result["reproducibility"]["run_metadata"]["resource_compute_governance"][
            "policy_id"
        ]
        == "default"
    )
    assert [j["job_id"] for j in client.get("/api/jobs").json()] == ["job_000001"]


def test_a_result_that_is_not_ready_says_so(store, policy):
    client, queue = service(store, policy, started=False)

    client.post("/api/jobs", json=job_request("reference_run"))
    response = client.get("/api/jobs/job_000001/result")

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "not_ready"
    assert client.get("/api/jobs/job_000009").status_code == 404
    assert client.get("/api/jobs/job_000009/result").status_code == 404


def test_a_job_that_kept_no_result_says_why(store, policy):
    client, queue = service(store, changed(policy, partial_result_export=False))
    client.post("/api/jobs", json=job_request("runaway_run"))
    queue.wait_idle()
    queue.close()

    response = client.get("/api/jobs/job_000001/result")

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no_result"


# ── refusals at the door ─────────────────────────────────────────────────────


def test_the_oversized_batch_is_refused_with_its_reason(api):
    client, _ = api

    response = client.post("/api/jobs", json=job_request("oversized_batch"))

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "batch_too_large"
    assert client.get("/api/jobs").json() == []


def test_a_full_queue_refuses_with_429(store, policy):
    client, queue = service(store, changed(policy, max_queue_length=1), started=False)

    assert (
        client.post("/api/jobs", json=job_request("reference_run")).status_code == 202
    )
    response = client.post("/api/jobs", json=job_request("reference_run"))

    assert response.status_code == 429
    assert response.json()["detail"]["reason"] == "queue_full"


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"kind": "scenario_run", "scenario": "nowhere/v0.1"}, 404),
        ({"kind": "scenario_run"}, 422),
        ({"kind": "teleport", "scenario": "tactical_reference_001/v0.1"}, 422),
        ({"kind": "persistent_world", "scenario": "tactical_reference_001/v0.1"}, 422),
    ],
)
def test_bad_requests_are_refused(api, body, status):
    client, _ = api

    assert client.post("/api/jobs", json=body).status_code == status


# ── cancelling and replaying ─────────────────────────────────────────────────


def test_a_waiting_job_is_cancelled_and_never_runs(store, policy):
    client, queue = service(store, policy, started=False)
    client.post("/api/jobs", json=job_request("reference_run"))

    cancelled = client.post("/api/jobs/job_000001/cancel").json()
    queue.start()
    queue.wait_idle()
    queue.close()

    assert cancelled["lifecycle_state"] == "failed"
    assert cancelled["error"] == "cancelled before it ran"
    assert client.post("/api/jobs/job_000001/cancel").status_code == 409
    assert client.post("/api/jobs/job_000009/cancel").status_code == 404


def test_a_running_job_is_asked_to_stop_and_hands_over_its_partial_result(
    store, policy
):
    endless = changed(
        policy,
        max_scenario_duration=None,
        max_runtime_seconds=None,
        auto_stop={"no_new_state_change_ticks": None, "infinite_loop_repeats": None},
        compute_budget={"max_decisions": None, "max_events": None},
    )
    client, queue = service(store, endless)
    request = {
        **job_request("runaway_run"),
        "runtime": {**JOBS["runaway_run"]["runtime"], "max_ticks": 100000},
    }
    client.post("/api/jobs", json=request)
    while client.get("/api/jobs/job_000001").json()["lifecycle_state"] != "running":
        time.sleep(0.01)

    asked = client.post("/api/jobs/job_000001/cancel").json()
    assert queue.wait_idle(timeout=60)
    queue.close()

    assert asked["summary"]["cancel_requested"] is True
    result = client.get("/api/jobs/job_000001/result").json()
    assert result["evaluation_result"]["termination_reason"] == "auto_stop:cancelled"
    assert (
        result["reproducibility"]["run_metadata"]["resource_compute_governance"][
            "partial"
        ]
        is True
    )


def test_a_finished_run_can_be_replayed(api):
    client, queue = api
    client.post("/api/jobs", json=job_request("reference_run"))
    queue.wait_idle()

    assert client.post("/api/jobs/job_000001/replay").status_code == 202
    queue.wait_idle()

    replay = client.get("/api/jobs/job_000002/result").json()
    assert replay["reproduced"] is True and replay["replay_of"] == "job_000001"
    assert client.get("/api/jobs/job_000001").json()["lifecycle_state"] == "replayed"
    assert client.post("/api/jobs/job_000009/replay").status_code == 404


# ── status: modes and health ─────────────────────────────────────────────────


def test_an_idle_service_is_on_standby_and_healthy(api):
    client, _ = api

    status = client.get("/api/status").json()

    assert status["service_status"] == {"mode": "standby", "health": "normal"}
    assert status["queue"] == {"depth": 0, "running": []}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_the_mode_follows_what_is_running(store, policy):
    client, _ = service(store, policy, started=False)
    for name in ("reference_run", "reference_batch", "failure_exploration"):
        client.post("/api/jobs", json=job_request(name))

    def mode():
        return client.get("/api/status").json()["service_status"]["mode"]

    store.update_job("job_000001", lifecycle_state="running")
    assert mode() == "running"
    store.update_job("job_000002", lifecycle_state="running")
    assert mode() == "batch"
    store.update_job("job_000003", lifecycle_state="running")
    assert mode() == "failure_exploration"


def test_health_degrades_when_half_the_recent_jobs_failed(store, policy):
    client, queue = service(store, policy)
    broken = {
        "kind": "scenario_run",
        "scenario": "tactical_reference_001/v0.1",
        "runtime": {"policy": {"name": "missing"}},
    }
    client.post("/api/jobs", json=job_request("reference_run"))
    client.post("/api/jobs", json=broken)
    queue.wait_idle()

    assert (
        client.get("/api/status").json()["service_status"]["health"] == "degraded"
    )  # 1 of 2
    client.post("/api/jobs", json=job_request("reference_run"))
    queue.wait_idle()
    queue.close()
    assert (
        client.get("/api/status").json()["service_status"]["health"] == "normal"
    )  # 1 of 3


# ── acceptance 10: persistent worlds and their cap ───────────────────────────


def test_a_persistent_world_advances_and_checkpoints(api):
    client, _ = api

    created = client.post(
        "/api/worlds", json={"scenario": JOBS["persistent_world"]["scenario"]}
    ).json()
    world = created["world_id"]
    ticks = [
        client.post(f"/api/worlds/{world}/advance", json={"ticks": n}).json()["tick"]
        for n in JOBS["persistent_world"]["advance"]
    ]

    assert created["lifecycle_state"] == "initialized" and created["tick"] == 0
    assert ticks == [5, 10, 15]
    assert [
        c["tick"] for c in client.get(f"/api/worlds/{world}/checkpoints").json()
    ] == [5, 10, 15]
    assert client.get(f"/api/worlds/{world}").json()["lifecycle_state"] == "paused"
    assert client.get(f"/api/jobs/{world}").json()["lifecycle_state"] == "paused"
    assert client.get("/api/status").json()["service_status"]["mode"] == "persistent"


def test_a_persistent_world_stops_at_its_tick_cap(store, policy):
    capped = changed(policy, persistent_world_resource_cap={"max_ticks": 12})
    client, queue = service(store, capped)
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]

    states = [
        client.post(f"/api/worlds/{world}/advance", json={"ticks": 5}).json()
        for _ in range(3)
    ]
    result = client.get(f"/api/jobs/{world}/result").json()
    queue.close()

    # 5, 10, then the third advance reaches the 12-tick cap
    assert [s["tick"] for s in states] == [5, 10, 12]
    assert (
        states[-1]["lifecycle_state"] == "completed"
        and states[-1]["stop_reason"] == "resource_cap_reached"
    )
    assert (
        result["evaluation_result"]["termination_reason"]
        == "auto_stop:resource_cap_reached"
    )
    rec = result["reproducibility"]["run_metadata"]["resource_compute_governance"]
    assert rec["partial"] and rec["estimated_cost"] == {
        "runs": 1,
        "decisions": 96,
        "seconds": 0.067,
    }
    assert (
        client.post(f"/api/worlds/{world}/advance", json={"ticks": 1}).status_code
        == 409
    )


def test_a_persistent_world_stops_at_its_checkpoint_cap(store, policy):
    capped = changed(policy, persistent_world_resource_cap={"max_checkpoints": 2})
    client, queue = service(store, capped)
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]

    states = [
        client.post(f"/api/worlds/{world}/advance", json={"ticks": 3}).json()
        for _ in range(2)
    ]
    queue.close()

    assert [s["lifecycle_state"] for s in states] == ["paused", "completed"]
    assert (
        states[-1]["stop_reason"] == "resource_cap_reached"
        and states[-1]["checkpoints"] == 2
    )


def test_finishing_a_world_early_exports_its_partial_result_and_delete_closes_it(api):
    client, _ = api
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 4})

    finished = client.post(f"/api/worlds/{world}/finish").json()
    again = client.post(f"/api/worlds/{world}/finish").json()
    deleted = client.delete(f"/api/worlds/{world}").json()

    assert finished["evaluation_result"]["termination_reason"] == "auto_stop:cancelled"
    assert finished["final_world_state"]["tick"] == 4 and again == finished
    assert deleted == {"world_id": world, "lifecycle_state": "deleted"}
    assert client.get(f"/api/jobs/{world}").json()["lifecycle_state"] == "deleted"
    assert client.get(f"/api/worlds/{world}").status_code == 404


def test_cancelling_a_world_finishes_it_with_its_partial_result(api):
    """The cancel used to return 200 and change nothing (code review, 2026-11-09)."""
    client, _ = api
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 3})

    cancelled = client.post(f"/api/jobs/{world}/cancel")
    after = client.post(f"/api/worlds/{world}/advance", json={"ticks": 1})
    result = client.get(f"/api/jobs/{world}/result").json()

    assert cancelled.status_code == 200
    assert cancelled.json()["lifecycle_state"] == "completed"
    assert cancelled.json()["summary"]["termination_reason"] == "auto_stop:cancelled"
    assert after.status_code != 200
    assert result["final_world_state"]["tick"] == 3
    assert client.post(f"/api/jobs/{world}/cancel").status_code == 409


def test_time_a_world_waits_between_advances_is_not_its_runtime(store, policy):
    """Idle time used to count toward max_runtime_seconds (code review, 2026-11-09)."""
    client, queue = service(store, changed(policy, max_runtime_seconds=0.5))
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]
    time.sleep(0.8)

    state = client.post(f"/api/worlds/{world}/advance", json={"ticks": 1}).json()
    queue.close()

    assert state["tick"] == 1 and state["lifecycle_state"] == "paused"
    assert state["stop_reason"] is None


def test_status_reads_the_live_worlds_under_their_lock(api):
    """Status iterated the worlds unlocked (code review, 2026-11-09)."""
    client, _ = api
    client.post("/api/worlds", json={"scenario": "military_squad_001/v0.1"})
    answers: list = []
    with client.app.state.worlds_lock:
        reader = threading.Thread(
            target=lambda: answers.append(client.get("/api/status"))
        )
        reader.start()
        reader.join(0.5)
        waited = reader.is_alive()
    reader.join(10)

    assert waited  # it could not read the worlds while another thread held them
    assert answers[0].status_code == 200
    assert len(answers[0].json()["worlds"]) == 1


def test_deleting_a_world_that_never_finished_keeps_its_result(api):
    client, _ = api
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 2})

    client.delete(f"/api/worlds/{world}")

    assert (
        client.get(f"/api/jobs/{world}/result").json()["final_world_state"]["tick"] == 2
    )


@pytest.mark.parametrize("ticks", [0, -3, "five", None])
def test_a_world_advances_a_whole_number_of_ticks(api, ticks):
    client, _ = api
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]

    assert (
        client.post(f"/api/worlds/{world}/advance", json={"ticks": ticks}).status_code
        == 422
    )


def test_unknown_worlds_and_bad_world_requests_are_refused(api):
    client, _ = api

    assert (
        client.post("/api/worlds/job_000009/advance", json={"ticks": 1}).status_code
        == 404
    )
    assert client.get("/api/worlds/job_000009/checkpoints").status_code == 404
    assert (
        client.post("/api/worlds", json={"scenario": "nowhere/v0.1"}).status_code == 404
    )
    response = client.post(
        "/api/worlds",
        json={
            "scenario": "military_squad_001/v0.1",
            "runtime": {"policy": {"name": "missing"}},
        },
    )
    assert response.status_code == 404
    assert client.get("/api/jobs/job_000001").json()["lifecycle_state"] == "failed"


def test_two_advances_at_once_never_step_the_same_world_together(api):
    client, _ = api
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]
    threads = [
        threading.Thread(
            target=client.post,
            args=(f"/api/worlds/{world}/advance",),
            kwargs={"json": {"ticks": 3}},
        )
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [
        c["tick"] for c in client.get(f"/api/worlds/{world}/checkpoints").json()
    ] == [3, 6, 9, 12]


def test_a_world_with_no_tick_cap_has_no_estimate(store, policy):
    open_world = changed(policy, persistent_world_resource_cap={"max_ticks": None})
    client, queue = service(store, open_world)
    world = client.post(
        "/api/worlds", json={"scenario": "military_squad_001/v0.1"}
    ).json()["world_id"]

    client.post(f"/api/worlds/{world}/advance", json={"ticks": 1})
    result = client.post(f"/api/worlds/{world}/finish").json()
    queue.close()

    assert (
        result["reproducibility"]["run_metadata"]["resource_compute_governance"][
            "estimated_cost"
        ]
        is None
    )


# ── the default queue, the worker script and the deployment files ───────────


def test_the_default_queue_follows_the_policy():
    queue = in_process_queue(SQLiteStore(), load_governance())

    assert (queue.max_parallel_runs, queue.queue_policy) == (2, "priority_then_fifo")
    queue.close()


def test_the_worker_script_runs_what_the_api_queued(store, policy, redis_url):
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from world_worker import main

    queue = RQQueue(redis_url, store.spec)
    queue.clear()
    client = TestClient(create_world_service(store, queue, policy))
    client.post("/api/jobs", json=job_request("reference_run"))

    main(["--redis", redis_url, "--store", store.spec, "--burst"])

    assert client.get("/api/jobs/job_000001").json()["lifecycle_state"] == "completed"


def test_the_compose_file_runs_the_api_and_a_worker_on_redis_and_postgres():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())

    assert set(compose["services"]) == {"api", "worker", "redis", "postgres"}
    for name, script in (("api", "serve_world.py"), ("worker", "world_worker.py")):
        command = compose["services"][name]["command"]
        assert script in command and (REPO_ROOT / "scripts" / script).exists()
        assert "redis://redis:6379" in command and "postgresql://" in command
    assert "serve_world.py" in (REPO_ROOT / "Dockerfile").read_text()


def test_the_world_service_never_imports_the_ui_backend():
    for path in (REPO_ROOT / "src" / "skyvault" / "worldservice").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {
            getattr(node, "module", "") or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(
            m.startswith("..service") or m.startswith("skyvault.service")
            for m in modules
        ), path.name


def test_redis_is_only_needed_when_asked_for():
    assert REDIS is None or REDIS.startswith("redis://")
