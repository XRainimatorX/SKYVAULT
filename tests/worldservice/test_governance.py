"""Phase 11 step A: governance at the door and at every tick, and partial results."""

import copy
import json
from pathlib import Path

import pytest

from skyvault.contracts import (
    ContractError,
    validate_governance,
    validate_governance_record,
    validate_result_package,
    validate_scenario,
)
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario
from skyvault.worldservice.governance import (
    Governor,
    Rejected,
    admit,
    clamp_duration,
    estimate_run,
    fingerprint,
    load_governance,
    scale,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = REPO_ROOT / "data" / "scenarios"
REFERENCE = SCENARIOS / "tactical_reference_001" / "v0.1.json"
JOBS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "service" / "jobs.json").read_text()
)["jobs"]


def policy(**changes):
    loaded = load_governance()
    for key, value in changes.items():
        if isinstance(value, dict):
            loaded[key] = {**loaded[key], **value}
        else:
            loaded[key] = value
    return loaded


def scenario(path=REFERENCE, **runtime):
    loaded = load_scenario(path)
    loaded["runtime"].update(runtime)
    return validate_scenario(loaded)


def governed(loaded, pol=None, perspective="RED", **kwargs):
    engine = SkyVaultTacticalReferenceEngine(
        loaded, governor=Governor(pol or policy(), perspective, **kwargs)
    )
    return engine, engine.run()


def record(package):
    return package["reproducibility"]["run_metadata"]["resource_compute_governance"]


def world(*cells, hp=30):
    """A snapshot with one RED unit per cell (and one BLUE far away)."""
    units = {
        f"r{i}": {
            "faction": "RED",
            "position": c,
            "state": {"hp": hp, "status": "active"},
        }
        for i, c in enumerate(cells)
    }
    units["b0"] = {
        "faction": "BLUE",
        "position": [9, 9],
        "state": {"hp": hp, "status": "active"},
    }
    return {"entities": units, "resources": {}}


# ── the policy ───────────────────────────────────────────────────────────────


def test_the_default_policy_passes_its_contract_with_every_default_filled():
    loaded = load_governance()

    assert loaded["policy_id"] == "default"
    assert loaded["max_batch_count"] == 1000
    assert loaded["auto_stop"] == {
        "no_new_state_change_ticks": 10,
        "infinite_loop_repeats": 3,
        "failure_loss_ratio": None,
    }
    assert load_governance(REPO_ROOT / "data" / "service" / "governance.json") == loaded


@pytest.mark.parametrize(
    "broken",
    [
        {"policy_id": "x", "run_priority": "urgent"},
        {"policy_id": "x", "max_parallel_runs": 0},
        {"policy_id": "x", "auto_stop": {"infinite_loop_repeats": 1}},
        {"policy_id": "x", "auto_stop": {"failure_loss_ratio": 1.5}},
        {"policy_id": "x", "unlimited": True},
    ],
)
def test_a_broken_policy_is_refused(broken):
    with pytest.raises(ContractError):
        validate_governance(broken)


# ── at the door ──────────────────────────────────────────────────────────────


def test_an_estimate_is_one_decision_per_unit_per_tick():
    # 6 units x 10 ticks = 60 decisions; 60 x 0.7 ms = 0.042 s
    assert estimate_run(scenario()) == {"runs": 1, "decisions": 60, "seconds": 0.042}
    assert scale({"runs": 1, "decisions": 60, "seconds": 0.042}, 600) == {
        "runs": 600,
        "decisions": 36000,
        "seconds": 25.2,
    }


def test_a_duration_over_the_limit_is_cut_and_the_cut_recorded():
    long_run = scenario(max_ticks=5000)
    short_run = scenario(max_ticks=150)

    assert clamp_duration(long_run, policy()) == 5000
    assert long_run["runtime"]["max_ticks"] == 200
    assert clamp_duration(short_run, policy()) is None
    assert short_run["runtime"]["max_ticks"] == 150
    assert (
        clamp_duration(scenario(max_ticks=5000), policy(max_scenario_duration=None))
        is None
    )


def test_the_reference_batch_is_admitted_and_the_oversized_one_refused():
    one = estimate_run(scenario())

    admit(scale(one, 600), policy(), queue_length=0)  # 600 runs <= 1000
    with pytest.raises(Rejected) as refused:
        admit(scale(one, 6 * 1_000_000), policy(), queue_length=0)
    assert refused.value.reason == "batch_too_large"


@pytest.mark.parametrize(
    ("estimate", "changes", "queued", "reason"),
    [
        ({"runs": 1, "decisions": 6000, "seconds": 1.0}, {}, 0, "budget_exceeded"),
        ({"runs": 1, "decisions": 10, "seconds": 61.0}, {}, 0, "budget_exceeded"),
        ({"runs": 1, "decisions": 10, "seconds": 0.1}, {}, 100, "queue_full"),
        ({"runs": 1001, "decisions": 10, "seconds": 0.1}, {}, 0, "batch_too_large"),
    ],
)
def test_each_reason_to_refuse_a_job(estimate, changes, queued, reason):
    with pytest.raises(Rejected) as refused:
        admit(estimate, policy(**changes), queue_length=queued)

    assert refused.value.reason == reason
    assert reason in str(refused.value)


def test_a_policy_without_limits_admits_anything():
    open_policy = policy(
        max_batch_count=None,
        max_queue_length=None,
        max_runtime_seconds=None,
        compute_budget={"max_decisions": None},
    )

    admit({"runs": 10**9, "decisions": 10**12, "seconds": 10**9}, open_policy, 10**6)


# ── every tick: the governor ─────────────────────────────────────────────────


def test_no_new_state_change_needs_the_whole_window():
    governor = Governor(policy(auto_stop={"no_new_state_change_ticks": 3}))
    still = world([0, 0])

    answers = [governor.after_tick(still, 0, 0, t) for t in range(1, 5)]

    # tick 1 first shows the state; ticks 2-4 repeat it: the third repeat stops
    assert answers == [None, None, None, "no_new_state_change"]


def test_a_state_reached_again_and_again_is_a_loop():
    governor = Governor(policy())
    a, b = world([0, 0]), world([1, 0])

    answers = [
        governor.after_tick(s, 0, 0, t) for t, s in enumerate([a, b, a, b, a], 1)
    ]

    assert answers == [None, None, None, None, "infinite_loop_detected"]


def test_switched_off_conditions_never_fire():
    governor = Governor(
        policy(
            auto_stop={"no_new_state_change_ticks": None, "infinite_loop_repeats": None}
        )
    )
    a, b = world([0, 0]), world([1, 0])

    assert all(
        governor.after_tick(s, 0, 0, t) is None
        for t, s in enumerate([a, a, a, b, a, b, a] * 3)
    )


def test_the_budget_stops_a_run_one_decision_or_event_past_it():
    governor = Governor(policy(compute_budget={"max_decisions": 10, "max_events": 50}))

    assert governor.after_tick(world([0, 0]), 10, 50, 1) is None
    assert governor.after_tick(world([1, 0]), 11, 50, 2) == "budget_exceeded"
    assert (
        Governor(
            policy(compute_budget={"max_decisions": 10, "max_events": 50})
        ).after_tick(world([0, 0]), 1, 51, 1)
        == "budget_exceeded"
    )


def test_runtime_is_measured_from_the_start(monkeypatch):
    clock = iter([100.0, 100.5, 161.0])
    monkeypatch.setattr(
        "skyvault.worldservice.governance.time.monotonic", lambda: next(clock)
    )
    governor = Governor(policy())  # started at 100.0; the limit is 60 s

    assert governor.after_tick(world([0, 0]), 0, 0, 1) is None  # 0.5 s
    assert governor.after_tick(world([1, 0]), 0, 0, 2) == "max_runtime_exceeded"  # 61 s


def test_runtime_counts_only_the_time_the_run_is_stepping(monkeypatch):
    """A persistent world waits between advances (code review, 2026-11-09)."""
    clock = iter([100.0, 100.0, 100.5, 101.0, 500.0, 500.5, 559.0, 562.0])
    monkeypatch.setattr(
        "skyvault.worldservice.governance.time.monotonic", lambda: next(clock)
    )
    governor = Governor(policy())  # 100.0
    governor.start()  # 100.0
    assert governor.after_tick(world([0, 0]), 0, 0, 1) is None  # 0.5 s
    governor.pause()  # 101.0: 1 s spent, then idle for 399 s
    governor.pause()  # pausing twice changes nothing
    assert governor.runtime() == 1.0  # paused: no clock read, nothing added
    governor.resume()  # 500.0
    governor.resume()  # resuming twice changes nothing
    assert governor.after_tick(world([1, 0]), 0, 0, 2) is None  # 1.5 s
    assert governor.after_tick(world([2, 0]), 0, 0, 3) is None  # 60 s
    assert governor.after_tick(world([3, 0]), 0, 0, 4) == "max_runtime_exceeded"


def test_a_persistent_world_cap_counts_ticks_and_events():
    cap = {"max_ticks": 3, "max_events": 100, "max_checkpoints": 5}

    assert Governor(policy(), cap=cap).after_tick(world([0, 0]), 0, 0, 2) is None
    assert (
        Governor(policy(), cap=cap).after_tick(world([0, 0]), 0, 0, 3)
        == "resource_cap_reached"
    )
    assert (
        Governor(policy(), cap=cap).after_tick(world([0, 0]), 0, 100, 1)
        == "resource_cap_reached"
    )


def test_losses_stop_a_run_only_for_the_judged_side_and_only_when_asked():
    half_lost = world([0, 0], [1, 0])
    half_lost["entities"]["r1"]["state"]["status"] = "destroyed"
    strict = policy(auto_stop={"failure_loss_ratio": 0.5})

    assert (
        Governor(strict, "RED").after_tick(half_lost, 0, 0, 1)
        == "failure_threshold_reached"
    )
    assert Governor(strict, "BLUE").after_tick(half_lost, 0, 0, 1) is None
    assert Governor(strict, None).after_tick(half_lost, 0, 0, 1) is None
    assert (
        Governor(policy(auto_stop={"failure_loss_ratio": 0.6}), "RED").after_tick(
            half_lost, 0, 0, 1
        )
        is None
    )


def test_a_cancel_wins_over_everything():
    governor = Governor(policy())
    governor.cancel()

    assert governor.after_tick(world([0, 0]), 10**9, 10**9, 1) == "cancelled"


def test_the_fingerprint_ignores_the_tick_but_not_the_units():
    a = world([0, 0])

    assert fingerprint(dict(a, tick=1)) == fingerprint(dict(a, tick=9))
    assert fingerprint(a) != fingerprint(world([0, 1]))
    assert fingerprint(a) != fingerprint(world([0, 0], hp=29))


# ── in the engine: real runs prove each threshold fires ──────────────────────


def test_the_runaway_job_is_stopped_and_hands_over_its_partial_result():
    loaded = scenario(**JOBS["runaway_run"]["runtime"])
    cut = clamp_duration(loaded, policy())

    _, package = governed(
        loaded, duration_clamped_from=cut, estimated_cost=estimate_run(loaded)
    )
    rec = record(package)

    # ticks 2..11 repeat tick 1's state: the tenth repeat, at tick 11, stops it
    assert package["final_world_state"]["tick"] == 11
    assert (
        package["evaluation_result"]["termination_reason"]
        == "auto_stop:no_new_state_change"
    )
    assert validate_result_package(package) == package
    assert (rec["stopped"], rec["partial"], rec["stop_reason"]) == (
        True,
        True,
        "no_new_state_change",
    )
    assert rec["usage"] == {**rec["usage"], "ticks": 11, "decisions": 66, "events": 67}
    assert rec["duration_clamped_from"] == 5000
    assert rec["estimated_cost"] == {"runs": 1, "decisions": 1200, "seconds": 0.84}
    assert package["event_memory"][-1]["event_type"] == "SCENARIO_END"


def test_a_real_run_over_its_budget_is_stopped():
    _, package = governed(scenario(), policy(compute_budget={"max_decisions": 20}))

    # 6 decisions a tick: 18 after tick 3, 24 after tick 4 -> stopped at tick 4
    assert package["final_world_state"]["tick"] == 4
    assert record(package)["stop_reason"] == "budget_exceeded"


def test_a_real_run_that_loses_a_third_of_its_side_is_stopped():
    _, unstopped = governed(scenario())
    # a BLUE attacker destroying a RED unit: RED has lost 1 of 3 (>= 0.3)
    first_loss = next(
        e["time"]
        for e in unstopped["event_memory"]
        if e["event_type"] == "ENTITY_DESTROYED"
        and e["source"].get("actor_id", "").startswith("blue")
    )

    _, package = governed(scenario(), policy(auto_stop={"failure_loss_ratio": 0.3}))

    assert record(package)["stop_reason"] == "failure_threshold_reached"
    assert package["final_world_state"]["tick"] == first_loss


def test_a_real_run_walking_back_and_forth_is_a_loop():
    there_and_back = [
        {
            "tick": t,
            "entity_id": "red_001",
            "action_type": "move",
            "target": {"location": [1, 1] if t % 2 else [0, 0]},
        }
        for t in range(1, 11)
    ]
    hold = {"name": "rule_based", "params": {"rules": ["hold"]}}
    loaded = scenario(
        participants=[
            {
                "participant_id": "walker",
                "policy": {"name": "scripted", "params": {"orders": there_and_back}},
                "controls": {"entity_ids": ["red_001"]},
            },
            {
                "participant_id": "rest",
                "policy": hold,
                "controls": {
                    "entity_ids": [
                        "red_002",
                        "red_003",
                        "blue_001",
                        "blue_002",
                        "blue_003",
                    ]
                },
            },
        ]
    )

    _, package = governed(loaded)

    # tick 1 A (out), 2 B (back), 3 A, 4 B, 5 A: A is reached a third time
    assert record(package)["stop_reason"] == "infinite_loop_detected"
    assert package["final_world_state"]["tick"] == 5


def test_a_real_run_over_its_time_is_stopped():
    _, package = governed(scenario(), policy(max_runtime_seconds=1e-9))

    assert record(package)["stop_reason"] == "max_runtime_exceeded"
    assert package["final_world_state"]["tick"] == 1


def test_a_governed_run_that_is_not_stopped_is_exactly_the_ungoverned_run():
    for path in (REFERENCE, SCENARIOS / "military_squad_001" / "v0.1.json"):
        plain = SkyVaultTacticalReferenceEngine(scenario(path)).run()
        _, under_policy = governed(scenario(path))

        assert (
            under_policy["reproducibility"]["output_hash"]
            == plain["reproducibility"]["output_hash"]
        )
        assert record(under_policy)["stopped"] is False
        assert record(under_policy)["policy_id"] == "default"


def test_every_run_records_its_governance_even_without_a_policy():
    package = SkyVaultTacticalReferenceEngine(scenario()).run()
    rec = record(package)

    assert validate_governance_record(rec) == rec
    assert (rec["policy_id"], rec["limits"], rec["stopped"]) == (
        "ungoverned",
        None,
        False,
    )
    assert rec["usage"]["runs"] == 1
    assert rec["usage"]["ticks"] == 10 and rec["usage"]["decisions"] == 46
    assert rec["usage"]["events"] == len(package["event_memory"]) == 97


# ── begin, step, finish ──────────────────────────────────────────────────────


def test_stepping_a_run_by_hand_is_the_same_run():
    engine = SkyVaultTacticalReferenceEngine(scenario())
    engine.begin()
    steps = 0
    while engine.step():
        steps += 1

    package = engine.finish()

    # RED wins during tick 10: that step answers False, after 9 that answered True
    assert steps == 9 and engine.over
    assert package["reproducibility"]["output_hash"].startswith("63090026e137")
    assert engine.step() is False


def test_a_run_stopped_from_outside_ends_after_the_tick():
    engine = SkyVaultTacticalReferenceEngine(scenario())
    engine.begin()
    engine.step()
    engine.step()
    engine.stop("cancelled")

    package = engine.finish()

    assert package["final_world_state"]["tick"] == 2
    assert package["evaluation_result"]["termination_reason"] == "auto_stop:cancelled"
    assert record(package)["policy_id"] == "ungoverned"


def test_the_run_steps_must_come_in_order():
    engine = SkyVaultTacticalReferenceEngine(scenario())
    with pytest.raises(RuntimeError, match="begin"):
        engine.step()
    with pytest.raises(RuntimeError, match="begin"):
        engine.finish()
    engine.begin()
    with pytest.raises(RuntimeError, match="already begun"):
        engine.begin()
    engine.finish()
    with pytest.raises(RuntimeError, match="already finished"):
        engine.finish()


def test_the_engine_never_imports_the_world_service():
    text = (REPO_ROOT / "src" / "skyvault" / "engine.py").read_text()

    assert "worldservice" not in text.split('"""', 2)[2]


def test_a_finished_package_keeps_its_hash_when_copied():
    _, package = governed(scenario())

    assert copy.deepcopy(package) == package
