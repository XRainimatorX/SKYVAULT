"""Formal Spec section 10: service contract, lifecycle, recovery, monitoring."""

import pytest
from fastapi.testclient import TestClient
from service_data import JOBS, job_request

from skyvault.contracts.service import OPERATION_MODES, SERVICE_ACTIONS
from skyvault.worldservice.api import create_world_service
from skyvault.worldservice.jobs import execute_job
from skyvault.worldservice.monitoring import material_changes
from skyvault.worldservice.queues import InProcessQueue

pytest_plugins = ["service_fixtures"]

SCENARIO = JOBS["persistent_world"]["scenario"]
# Formal Spec 10.3, every state a world instance must be able to reach
LIFECYCLE = (
    "created",
    "initialized",
    "running",
    "paused",
    "branched",
    "completed",
    "failed",
    "archived",
    "replayed",
    "deleted",
)


def service(store, policy):
    queue = InProcessQueue(
        lambda job_id: execute_job(job_id, store, policy),
        policy["max_parallel_runs"],
        policy["queue_policy"],
    )
    return TestClient(create_world_service(store, queue, policy)), queue


@pytest.fixture
def api(store, policy):
    client, queue = service(store, policy)
    yield client, queue
    queue.close()


def new_world(client) -> str:
    return client.post("/api/worlds", json={"scenario": SCENARIO}).json()["world_id"]


# ── 10.4 world_service_contract ──────────────────────────────────────────────


def test_the_service_describes_itself_as_section_10_4_field_by_field(api):
    client, queue = api
    standby = client.get("/api/service").json()

    assert set(standby) >= {
        "service_status",
        "task_intake",
        "world_instance",
        "service_actions",
    }
    assert standby["service_status"] == {"mode": "standby", "health": "normal"}
    assert standby["task_intake"]["task_type"] is None
    assert standby["world_instance"] is None
    assert standby["service_actions"] == list(SERVICE_ACTIONS)
    assert standby["operation_modes"] == list(OPERATION_MODES)
    assert set(standby["routes"]) == set(SERVICE_ACTIONS)

    client.post("/api/jobs", json=job_request("reference_run"))
    queue.wait_idle()
    world = new_world(client)
    after = client.get("/api/service").json()

    assert after["task_intake"] == {
        "source_system": "user",
        "task_type": "persistent_world",
        "priority": "medium",
        "required_result_package": True,
    }
    assert after["world_instance"]["world_id"] == world


# ── 10.3 world instance lifecycle and 10.4 service actions ──────────────────


def test_pause_resume_branch_terminate_and_archive_move_a_world_through_its_life(
    api,
):
    client, _ = api
    world = new_world(client)

    client.post(f"/api/worlds/{world}/advance", json={"ticks": 3})
    assert client.get(f"/api/worlds/{world}").json()["lifecycle_state"] == "running"

    paused = client.post(f"/api/worlds/{world}/pause").json()
    assert paused["lifecycle_state"] == "paused"
    refused = client.post(f"/api/worlds/{world}/advance", json={"ticks": 1})
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == "paused"

    resumed = client.post(f"/api/worlds/{world}/resume").json()
    assert resumed["lifecycle_state"] == "running"

    branched = client.post(f"/api/worlds/{world}/branch")
    assert branched.status_code == 201
    twin = branched.json()
    assert twin["lifecycle_state"] == "branched" and twin["tick"] == 3
    assert client.get(f"/api/jobs/{twin['world_id']}").json()["summary"][
        "branched_from"
    ] == {"world_id": world, "tick": 3}
    # the branch is the same world as it stood, then goes its own way
    assert client.get(f"/api/worlds/{twin['world_id']}/checkpoints").json() == []
    client.post(f"/api/worlds/{twin['world_id']}/advance", json={"ticks": 2})
    assert client.get(f"/api/worlds/{twin['world_id']}").json()["tick"] == 5
    assert client.get(f"/api/worlds/{world}").json()["tick"] == 3

    ended = client.post(f"/api/worlds/{world}/terminate").json()
    assert ended["evaluation_result"]["termination_reason"] == "auto_stop:terminated"
    assert client.get(f"/api/jobs/{world}").json()["lifecycle_state"] == "completed"

    archived = client.post(f"/api/worlds/{world}/archive").json()
    assert archived["lifecycle_state"] == "archived"
    assert client.get(f"/api/jobs/{world}").json()["lifecycle_state"] == "archived"
    assert client.get(f"/api/worlds/{world}").status_code == 404
    assert client.get(f"/api/jobs/{world}/result").status_code == 200


def test_a_live_world_cannot_be_archived_and_only_a_paused_one_resumes(api):
    client, _ = api
    world = new_world(client)

    early = client.post(f"/api/worlds/{world}/archive")
    assert early.status_code == 409
    assert early.json()["detail"]["reason"] == "invalid_state"
    assert client.post(f"/api/worlds/{world}/resume").status_code == 409


def corrupt_inputs(store, world: str) -> None:
    """Make the kept inputs of world lead somewhere else than its checkpoint."""
    job = store.get_job(world)
    inputs = job["summary"]["world_inputs"]
    inputs["tick"] += 1  # one tick further than the checkpoint recorded
    actor = next(iter(store.checkpoints(world)[-1]["world"]["entities"]))
    inputs["applied"].append(
        {
            "tick": 1,
            "actor_id": actor,
            "system_id": "STARTX",
            "action_type": "wait",
            "target": {},
        }
    )
    store.update_job(world, summary_fields={"world_inputs": inputs})


def test_every_section_10_3_state_is_reachable(store, policy):
    client, queue = service(store, policy)
    seen: set[str] = set()

    job = client.post("/api/jobs", json=job_request("reference_run")).json()
    seen.add(job["lifecycle_state"])  # created
    queue.wait_idle()
    seen.add(client.get(f"/api/jobs/{job['job_id']}").json()["lifecycle_state"])
    client.post(f"/api/jobs/{job['job_id']}/replay")
    queue.wait_idle()
    seen.add(client.get(f"/api/jobs/{job['job_id']}").json()["lifecycle_state"])

    world = new_world(client)
    seen.add(client.get(f"/api/worlds/{world}").json()["lifecycle_state"])
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 1})
    seen.add(client.get(f"/api/worlds/{world}").json()["lifecycle_state"])
    seen.add(client.post(f"/api/worlds/{world}/pause").json()["lifecycle_state"])
    client.post(f"/api/worlds/{world}/resume")
    seen.add(client.post(f"/api/worlds/{world}/branch").json()["lifecycle_state"])
    client.post(f"/api/worlds/{world}/terminate")
    seen.add(client.get(f"/api/jobs/{world}").json()["lifecycle_state"])
    seen.add(client.post(f"/api/worlds/{world}/archive").json()["lifecycle_state"])

    doomed = new_world(client)
    seen.add(client.delete(f"/api/worlds/{doomed}").json()["lifecycle_state"])

    broken = new_world(client)
    client.post(f"/api/worlds/{broken}/advance", json={"ticks": 1})
    queue.close()
    corrupt_inputs(store, broken)
    restarted, queue = service(store, policy)
    seen.add(restarted.get(f"/api/jobs/{broken}").json()["lifecycle_state"])
    queue.close()

    assert seen == set(LIFECYCLE)


# ── persistent worlds outlive the process ───────────────────────────────────


def test_a_restarted_service_rebuilds_its_live_worlds_to_their_last_checkpoint(
    store, policy
):
    client, queue = service(store, policy)
    world = new_world(client)
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 4})
    before = client.get(f"/api/worlds/{world}/checkpoints").json()[-1]["world"]
    queue.close()

    # a new process: the same store, nothing in memory
    restarted, queue = service(store, policy)
    state = restarted.get(f"/api/worlds/{world}").json()
    assert state["tick"] == 4 and state["lifecycle_state"] == "running"
    restarted.post(f"/api/worlds/{world}/advance", json={"ticks": 2})
    assert restarted.get(f"/api/worlds/{world}").json()["tick"] == 6

    # and it is the very same world: an uninterrupted twin agrees
    twin_client, twin_queue = service(store, policy)
    twin = new_world(twin_client)
    twin_client.post(f"/api/worlds/{twin}/advance", json={"ticks": 4})
    assert (
        twin_client.get(f"/api/worlds/{twin}/checkpoints").json()[-1]["world"][
            "entities"
        ]
        == before["entities"]
    )
    queue.close()
    twin_queue.close()


def test_a_world_that_does_not_rebuild_to_its_checkpoint_is_marked_failed(
    store, policy
):
    client, queue = service(store, policy)
    world = new_world(client)
    client.post(f"/api/worlds/{world}/advance", json={"ticks": 2})
    queue.close()
    corrupt_inputs(store, world)  # the kept inputs lead to another world

    restarted, queue = service(store, policy)
    assert restarted.get(f"/api/worlds/{world}").status_code == 404
    record = restarted.get(f"/api/jobs/{world}").json()
    assert record["lifecycle_state"] == "failed"
    assert record["error"].startswith("restore: ")
    queue.close()


# ── 10.2 Monitoring Mode ─────────────────────────────────────────────────────


def test_a_monitor_reruns_only_when_the_outside_data_moves_enough(api):
    client, queue = api
    monitor = client.post(
        "/api/monitors",
        json={"scenario": SCENARIO, "source_system": "EIDEN_01", "threshold": 0.2},
    ).json()
    assert monitor["lifecycle_state"] == "running"
    mid = monitor["job_id"]
    units = {"red_01": {"state": {"hp": 30}}}

    first = client.post(f"/api/monitors/{mid}/data", json={"entity_changes": units})
    small = client.post(
        f"/api/monitors/{mid}/data",
        json={"entity_changes": {"red_01": {"state": {"hp": 27}}}},
    )
    large = client.post(
        f"/api/monitors/{mid}/data",
        json={"entity_changes": {"red_01": {"state": {"hp": 12}}}},
    )
    queue.wait_idle()

    assert first.json()["rerun"] is True
    assert first.json()["changes"] == ["first data for this scenario"]
    assert small.json()["rerun"] is False
    assert "20%" in small.json()["reason"]
    assert large.json()["rerun"] is True
    assert large.json()["changes"] == ["red_01.state.hp: 27 -> 12 (56%)"]
    rerun = client.get(f"/api/jobs/{large.json()['job_id']}").json()
    assert rerun["lifecycle_state"] == "completed"
    assert rerun["request"]["entity_changes"]["red_01"]["state"] == {"hp": 12}
    assert client.get(f"/api/monitors/{mid}").json()["summary"]["monitor"][
        "reruns"
    ] == [first.json()["job_id"], large.json()["job_id"]]

    stopped = client.delete(f"/api/monitors/{mid}").json()
    assert stopped["lifecycle_state"] == "completed"
    assert (
        client.post(
            f"/api/monitors/{mid}/data", json={"entity_changes": units}
        ).status_code
        == 409
    )


def test_a_monitor_needs_a_known_scenario_and_a_sane_threshold(api):
    client, _ = api

    assert (
        client.post("/api/monitors", json={"scenario": "atlantis/v1"}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/monitors", json={"scenario": SCENARIO, "threshold": 2}
        ).status_code
        == 422
    )
    assert client.get("/api/monitors/job_999999").status_code == 404


@pytest.mark.parametrize(
    "before, after, expected",
    [
        (None, {"a": {}}, ["first data for this scenario"]),
        ({"a": {"x": 1}}, {"b": {"x": 1}}, ["b: new unit"]),
        ({"a": {"x": 10}}, {"a": {"x": 10.5}}, []),
        ({"a": {"x": "open"}}, {"a": {"x": "shut"}}, ["a.x: 'open' -> 'shut'"]),
        ({"a": {"on": True}}, {"a": {"on": False}}, ["a.on: True -> False"]),
        ({"a": {}}, {"a": {"y": 1}}, ["a.y: newly reported"]),
        ({"a": {"x": 0}}, {"a": {"x": 1}}, ["a.x: 0 -> 1 (100%)"]),
    ],
)
def test_what_counts_as_a_material_change(before, after, expected):
    assert material_changes(before, after, 0.1) == expected


# ── 3.3 output.failure_map_required ──────────────────────────────────────────


def test_a_run_that_requires_a_failure_map_brings_its_exploration_along(
    store, policy, tmp_path, monkeypatch
):
    import json
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "scenarios"
        / "military_urban_001"
        / "v0.2.json"
    )
    scenario = json.loads(source.read_text(encoding="utf-8"))
    scenario["identity"]["scenario_id"] = "site_urban"
    scenario["scenario_version_control"]["scenario_id"] = "site_urban"
    scenario["output"]["failure_map_required"] = True
    exploring = scenario["failure_exploration"]
    exploring["failure_variables"] = ["sensor_failure"]
    exploring["stress_levels"] = {"severe": {}}
    exploring["run_policy"] = {"repeat_count": 1, "random_seed_policy": "fixed"}
    exploring["alternatives"] = []
    folder = tmp_path / "site_urban"
    folder.mkdir()
    (folder / "v0.2.json").write_text(json.dumps(scenario), encoding="utf-8")
    monkeypatch.setenv("SKYVAULT_SCENARIO_PATH", str(tmp_path))

    client, queue = service(store, policy)
    job = client.post(
        "/api/jobs", json={"kind": "scenario_run", "scenario": "site_urban/v0.2"}
    ).json()
    queue.wait_idle()

    linked = client.get(f"/api/jobs/{job['summary']['failure_map_job']}").json()
    assert linked["request"]["kind"] == "failure_exploration"
    assert linked["lifecycle_state"] == "completed"
    assert (
        client.get(f"/api/jobs/{linked['job_id']}/result").json()["scenario_id"]
        == "site_urban"
    )
    plain = client.post(
        "/api/jobs", json={"kind": "scenario_run", "scenario": SCENARIO}
    ).json()
    queue.wait_idle()
    assert "failure_map_job" not in plain["summary"]
    queue.close()
