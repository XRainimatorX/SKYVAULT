"""Phase 11 step B: the store, the queues and the jobs a worker runs."""

import threading
import time

import pytest
from service_data import JOBS, job_request

from skyvault.contracts import ContractError, validate_job
from skyvault.worldservice.governance import Rejected
from skyvault.worldservice.jobs import (
    NotFound,
    execute_job,
    exploration_runs,
    new_job,
    plan,
    scenario_for,
)
from skyvault.worldservice.queues import InProcessQueue, RQQueue
from skyvault.worldservice.store import SQLiteStore, open_store

# the store, redis_url and policy fixtures
pytest_plugins = ["service_fixtures"]


def submit(store, policy, name_or_request, queue_length=0):
    request = (
        job_request(name_or_request)
        if isinstance(name_or_request, str)
        else name_or_request
    )
    return new_job(store, request, plan(request, policy, queue_length, store), policy)


def run(store, policy, name_or_request):
    job = submit(store, policy, name_or_request)
    execute_job(job["job_id"], store, policy)
    return store.get_job(job["job_id"])


# ── the store ────────────────────────────────────────────────────────────────


def test_jobs_are_numbered_kept_and_listed_in_order(store, policy):
    first = submit(store, policy, "reference_run")
    second = submit(store, policy, "reference_batch")

    assert (first["job_id"], second["job_id"]) == ("job_000001", "job_000002")
    assert [j["job_id"] for j in store.list_jobs()] == ["job_000001", "job_000002"]
    assert validate_job(store.get_job("job_000001")) == store.get_job("job_000001")
    updated = store.update_job("job_000001", lifecycle_state="running")
    assert (
        updated["lifecycle_state"]
        == store.get_job("job_000001")["lifecycle_state"]
        == "running"
    )
    assert updated["updated_at"] >= first["updated_at"]
    with pytest.raises(KeyError, match="no job"):
        store.get_job("job_999999")


def test_results_checkpoints_and_events_are_kept_in_order(store):
    store.save_result("job_000001", {"a": 1})
    store.save_result("job_000001", {"a": 2})

    assert store.get_result("job_000001") == {"a": 2}
    assert store.get_result("job_000002") is None
    assert [store.add_checkpoint("w1", {"tick": t}) for t in (5, 10)] == [1, 2]
    assert store.add_checkpoint("w2", {"tick": 1}) == 1
    assert store.checkpoints("w1") == [{"tick": 5}, {"tick": 10}]
    store.log("job_000001", "one")
    store.log("job_000001", "two")
    assert [(e["n"], e["message"]) for e in store.events("job_000001")] == [
        (1, "one"),
        (2, "two"),
    ]
    assert store.events("job_000009") == []


def test_a_store_is_opened_from_its_spec(tmp_path):
    on_disk = open_store(f"sqlite:///{tmp_path / 's.sqlite'}")
    on_disk.log("job_000001", "kept")

    assert open_store(on_disk.spec).events("job_000001")[0]["message"] == "kept"
    assert isinstance(open_store("sqlite://"), SQLiteStore)
    with pytest.raises(ValueError, match="unknown store"):
        open_store("mysql://nope")


# ── planning: what a request costs, and what is refused ──────────────────────


def test_each_kind_of_request_is_estimated(store, policy):
    run(store, policy, "reference_run")

    assert plan(job_request("reference_run"), policy, 0)["estimated_cost"]["runs"] == 1
    # the reference batch: 9 variants (6 + 2 branches + no-branch) x 5 repeats
    assert (
        plan(job_request("reference_batch"), policy, 0)["estimated_cost"]["runs"] == 45
    )
    # failure exploration: (1 + 6x4) + 1 branch + 2 alternatives x (1 + 6x4) = 76
    assert (
        plan(job_request("failure_exploration"), policy, 0)["estimated_cost"]["runs"]
        == 76
    )
    assert plan(job_request("runaway_run"), policy, 0)["duration_clamped_from"] == 5000
    assert (
        plan({"kind": "replay", "replay": "job_000001"}, policy, 0, store)[
            "estimated_cost"
        ]["runs"]
        == 1
    )


def test_the_oversized_batch_is_refused_at_the_door(policy):
    with pytest.raises(Rejected) as refused:
        plan(job_request("oversized_batch"), policy, 0)

    assert refused.value.reason == "batch_too_large"


@pytest.mark.parametrize(
    "request_",
    [
        {"kind": "scenario_run", "scenario": "../../../etc/passwd"},
        {"kind": "scenario_run", "scenario": "tactical_reference_001/v9.9"},
        {"kind": "batch", "batch": "../scenarios/tactical_reference_001/v0.1"},
    ],
)
def test_only_what_skyvault_has_can_be_named(request_, policy):
    with pytest.raises((NotFound, ContractError)):
        plan(request_, policy, 0)


def test_a_request_may_override_only_runtime_fields_it_is_allowed():
    with pytest.raises(ValueError, match="may not set"):
        scenario_for(
            {
                "scenario": "tactical_reference_001/v0.1",
                "runtime": {"world_contract": {}},
            }
        )


def test_a_replay_needs_a_run_with_a_result(store, policy):
    with pytest.raises(ValueError, match="needs the store"):
        plan({"kind": "replay", "replay": "job_000001"}, policy, 0)
    job = submit(store, policy, "reference_run")
    with pytest.raises(NotFound, match="no result"):
        plan({"kind": "replay", "replay": job["job_id"]}, policy, 0, store)


def test_a_request_without_what_its_kind_needs_is_refused(policy):
    with pytest.raises(ContractError, match="needs scenario"):
        plan({"kind": "scenario_run"}, policy, 0)


def test_the_exploration_estimate_counts_the_alternatives_without_a_branch():
    scenario = scenario_for({"scenario": "tactical_reference_001/v0.1"})

    assert exploration_runs(scenario, 1) == 76
    assert exploration_runs(scenario, None) == 760


# ── executing jobs ───────────────────────────────────────────────────────────


def test_a_scenario_run_leaves_its_result_and_record(store, policy):
    job = run(store, policy, "reference_run")

    assert job["lifecycle_state"] == "completed" and job["error"] is None
    assert job["summary"]["result"] == "RED_survived"
    assert job["summary"]["output_hash"].startswith("63090026e137")
    assert (
        job["governance"]["policy_id"] == "default" and not job["governance"]["stopped"]
    )
    assert store.get_result(job["job_id"])["reproducibility"]["output_hash"] == (
        store.get_result(job["job_id"])["reproducibility"]["output_hash"]
    )
    assert [e["message"] for e in store.events(job["job_id"])] == [
        "created by NEXUS",
        "running on a worker (scenario_run)",
        "completed: RED_survived",
    ]


def test_the_runaway_job_is_stopped_and_its_partial_result_kept(store, policy):
    job = run(store, policy, "runaway_run")
    result = store.get_result(job["job_id"])

    assert job["summary"]["termination_reason"] == "auto_stop:no_new_state_change"
    assert job["summary"]["result"] == "no_winner_stopped_early"
    assert job["summary"]["partial"] and job["summary"]["result_kept"]
    assert result["final_world_state"]["tick"] == 11
    assert job["governance"]["duration_clamped_from"] == 5000


def test_without_partial_export_a_stopped_run_keeps_only_its_record(store, policy):
    job = run(store, dict(policy, partial_result_export=False), "runaway_run")

    assert store.get_result(job["job_id"]) is None
    assert job["summary"]["result_kept"] is False
    assert job["governance"]["stop_reason"] == "no_new_state_change"


def test_a_failing_job_is_recorded_and_the_worker_goes_on(store, policy):
    broken = {
        "kind": "scenario_run",
        "scenario": "tactical_reference_001/v0.1",
        "runtime": {"policy": {"name": "no_such_policy"}},
    }

    failed = run(store, policy, broken)
    after = run(store, policy, "reference_run")

    assert failed["lifecycle_state"] == "failed"
    assert "no policy named 'no_such_policy'" in failed["error"]
    assert after["lifecycle_state"] == "completed"


def test_a_job_cancelled_before_it_runs_never_runs(store, policy):
    job = submit(store, policy, "reference_run")
    store.update_job(
        job["job_id"], summary={**job["summary"], "cancel_requested": True}
    )

    execute_job(job["job_id"], store, policy)

    assert store.get_job(job["job_id"])["lifecycle_state"] == "failed"
    assert store.get_job(job["job_id"])["error"] == "cancelled before it ran"
    assert store.get_result(job["job_id"]) is None


def test_a_running_job_is_cancelled_at_the_end_of_a_tick(store, policy):
    endless = dict(
        policy,
        max_scenario_duration=None,
        max_runtime_seconds=None,
        auto_stop={
            "no_new_state_change_ticks": None,
            "infinite_loop_repeats": None,
            "failure_loss_ratio": None,
        },
        compute_budget={"max_decisions": None, "max_events": None},
    )
    request = {
        **job_request("runaway_run"),
        "runtime": {**JOBS["runaway_run"]["runtime"], "max_ticks": 100000},
    }
    job = submit(store, endless, request)
    worker = threading.Thread(target=execute_job, args=(job["job_id"], store, endless))
    worker.start()
    while store.get_job(job["job_id"])["lifecycle_state"] != "running":
        time.sleep(0.01)
    time.sleep(0.2)
    current = store.get_job(job["job_id"])
    store.update_job(
        job["job_id"], summary={**current["summary"], "cancel_requested": True}
    )
    worker.join(timeout=60)

    done = store.get_job(job["job_id"])
    assert done["summary"]["termination_reason"] == "auto_stop:cancelled"
    assert 0 < store.get_result(job["job_id"])["final_world_state"]["tick"] < 100000


def test_a_batch_job_runs_exactly_the_runs_it_was_admitted_for(store, policy):
    job = run(store, policy, "reference_batch")

    assert job["summary"]["runs"] == job["estimated_cost"]["runs"] == 45
    assert job["summary"]["workers"] == 2  # the batch asks for 4; the policy allows 2
    assert job["governance"]["usage"]["runs"] == 45
    assert job["governance"]["usage"]["ticks"] is None
    assert job["governance"]["limits"]["max_batch_count"] == 1000
    assert store.get_result(job["job_id"])["batch_result"]["total_runs"] == 45


def test_a_failure_exploration_job_leaves_its_failure_map(store, policy):
    job = run(store, policy, "failure_exploration")

    assert job["lifecycle_state"] == "completed"
    assert (
        job["summary"]["crushing_variable"]
        == store.get_result(job["job_id"])["crushing_variable"]
    )
    assert job["governance"]["usage"]["runs"] == 76


def test_a_replay_reruns_history_and_hands_back_its_frames(store, policy):
    original = run(store, policy, "reference_run")

    replay = run(store, policy, {"kind": "replay", "replay": original["job_id"]})
    result = store.get_result(replay["job_id"])

    assert replay["summary"]["reproduced"] is True
    assert (
        result["replayed_output_hash"]
        == result["original_output_hash"]
        == original["summary"]["output_hash"]
    )
    assert {"0", "10", "final"} <= set(result["replay"]["states"])
    assert store.get_job(original["job_id"])["lifecycle_state"] == "replayed"


def test_a_replay_of_something_that_is_not_a_run_fails(store, policy):
    batch = run(store, policy, "reference_batch")

    replay = run(store, policy, {"kind": "replay", "replay": batch["job_id"]})

    assert replay["lifecycle_state"] == "failed" and "not a run" in replay["error"]


# ── the in-process queue ─────────────────────────────────────────────────────


def recorder(delay=0.0):
    order, active, peak = [], [0], [0]
    lock = threading.Lock()

    def execute(job_id):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(delay)
        with lock:
            order.append(job_id)
            active[0] -= 1

    return execute, order, peak


def test_a_higher_priority_goes_first_and_equals_keep_their_order():
    execute, order, _ = recorder()
    queue = InProcessQueue(execute, 1, start=False)
    for job_id, priority in [
        ("a", "low"),
        ("b", "normal"),
        ("c", "critical"),
        ("d", "high"),
        ("e", "normal"),
    ]:
        queue.submit(job_id, priority)

    assert queue.depth() == 5
    queue.start()
    assert queue.wait_idle()
    queue.close()

    assert order == ["c", "d", "b", "e", "a"]


def test_under_fifo_priority_is_ignored():
    execute, order, _ = recorder()
    queue = InProcessQueue(execute, 1, queue_policy="fifo", start=False)
    for job_id, priority in [("a", "low"), ("b", "critical"), ("c", "high")]:
        queue.submit(job_id, priority)
    queue.start()
    queue.wait_idle()
    queue.close()

    assert order == ["a", "b", "c"]


def test_no_more_than_max_parallel_runs_run_at_once():
    execute, order, peak = recorder(delay=0.05)
    queue = InProcessQueue(execute, 2)
    for n in range(6):
        queue.submit(f"j{n}", "normal")
    queue.start()  # already started: a second start does nothing

    assert queue.wait_idle()
    queue.close()
    assert sorted(order) == [f"j{n}" for n in range(6)]
    assert peak[0] == 2


def test_a_waiting_job_can_be_taken_out_of_the_queue():
    gate = threading.Event()
    started = threading.Event()
    ran = []

    def execute(job_id):
        started.set()
        gate.wait(5)
        ran.append(job_id)

    queue = InProcessQueue(execute, 1)
    queue.submit("first", "normal")
    started.wait(5)
    queue.submit("second", "normal")

    assert queue.running() == ["first"]
    assert queue.cancel("second") is True
    assert (
        queue.cancel("first") is False
    )  # running: cancelled through the store instead
    assert queue.wait_idle(timeout=0.05) is False
    gate.set()
    assert queue.wait_idle()
    queue.close()
    assert ran == ["first"]


# ── RQ on Redis ──────────────────────────────────────────────────────────────


def test_rq_workers_take_the_higher_priority_first(store, policy, redis_url):
    queue = RQQueue(redis_url, store.spec)
    queue.clear()
    low = submit(store, policy, {**job_request("reference_run"), "priority": "low"})
    high = submit(
        store, policy, {**job_request("reference_run"), "priority": "critical"}
    )
    queue.submit(low["job_id"], "low")
    queue.submit(high["job_id"], "critical")

    assert queue.depth() == 2
    queue.worker(burst=True).work(burst=True, logging_level="WARNING")

    finished = {
        j: store.get_job(j)["updated_at"] for j in (low["job_id"], high["job_id"])
    }
    assert finished[high["job_id"]] < finished[low["job_id"]]
    assert store.get_job(low["job_id"])["summary"]["output_hash"].startswith(
        "63090026e137"
    )
    assert queue.depth() == 0 and queue.running() == []


def test_a_queued_rq_job_can_be_cancelled(store, policy, redis_url):
    queue = RQQueue(redis_url, store.spec)
    queue.clear()
    job = submit(store, policy, "reference_run")
    queue.submit(job["job_id"], "normal")

    assert queue.cancel(job["job_id"]) is True
    assert queue.cancel(job["job_id"]) is False
    assert queue.cancel("job_unknown") is False
    queue.worker(burst=True).work(burst=True, logging_level="WARNING")
    assert store.get_job(job["job_id"])["lifecycle_state"] == "created"


def test_rq_also_bounds_a_job_by_time(store, redis_url):
    assert RQQueue(redis_url, store.spec).job_timeout == 120  # twice the 60 s limit
    assert (
        RQQueue(
            redis_url,
            store.spec,
            policy={"queue_policy": "fifo", "max_runtime_seconds": None},
        ).job_timeout
        is None
    )
