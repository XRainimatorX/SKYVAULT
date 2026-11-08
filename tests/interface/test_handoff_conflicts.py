"""Phase 12 step A: authority handoff, and conflicts played out but never judged."""

import copy
import json
from pathlib import Path

import pytest

from skyvault.batch.variants import branch_variant
from skyvault.contracts import ContractError, validate_authority_handoff
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.failure import build_failure_map, explore_failures
from skyvault.interface.conflicts import SubmissionWindow, find_conflicts, resolve
from skyvault.interface.handoff import (
    authority_handoff,
    decide,
    handoff_triggers,
    map_crossed,
)
from skyvault.scenario_loader import default_evaluation_profile, load_scenario
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import (
    execute_job,
    full_request,
    new_job,
    plan,
)
from skyvault.worldservice.store import SQLiteStore
from skyvault.worldservice.worlds import PersistentWorld, WorldAwaiting, WorldClosed

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = REPO_ROOT / "data" / "scenarios"
REFERENCE = SCENARIOS / "tactical_reference_001" / "v0.1.json"
SQUAD = SCENARIOS / "military_squad_001" / "v0.1.json"
SUBMISSIONS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "external" / "submissions.json").read_text()
)


def run(path, seed, thresholds=("all_entities_destroyed",)):
    scenario = load_scenario(path)
    scenario["runtime"]["random_seed"] = seed
    scenario["evaluation"]["failure_thresholds"] = list(thresholds)
    return SkyVaultTacticalReferenceEngine(scenario).run()


def failure_map(threshold):
    scenario = load_scenario(REFERENCE)
    config = copy.deepcopy(scenario["failure_exploration"])
    config["run_policy"]["repeat_count"] = 3
    config["survival_threshold"] = threshold
    return build_failure_map(
        explore_failures(scenario, default_evaluation_profile(scenario), config)
    )


@pytest.fixture(scope="module")
def maps():
    return {"strict": failure_map(0.7), "default": failure_map(0.5)}


# ── the four triggers, each proven on a real run ─────────────────────────────


def test_a_run_flagged_for_extreme_risk_is_handed_off():
    # military squad seed 45: Phase 7 flagged extreme_high_risk_optimization
    assert handoff_triggers(run(SQUAD, 45)) == ["high_risk_outcome"]


def test_a_short_term_win_bought_with_stability_is_handed_off():
    # the reference run itself (seed 42): RED survives, stability sacrificed
    assert handoff_triggers(run(REFERENCE, 42)) == ["strategic_tradeoff"]


def test_a_run_that_reaches_a_failure_threshold_is_handed_off():
    # seed 43 BLUE survives: RED is eliminated, which crosses perspective_eliminated
    crossed = run(REFERENCE, 43, ("all_entities_destroyed", "perspective_eliminated"))
    unwatched = run(REFERENCE, 43)

    assert handoff_triggers(crossed) == ["failure_threshold_crossed"]
    assert handoff_triggers(unwatched) == []


def test_a_quiet_run_hands_nothing_off():
    # seed 45: nobody wins in time, nothing flagged, no threshold reached
    assert handoff_triggers(run(REFERENCE, 45)) == []
    assert authority_handoff([], result=run(REFERENCE, 45)) is None


def test_a_failure_map_crosses_when_its_plan_fails_without_stress(maps):
    # baseline survival 0.667: under a 0.7 threshold it fails unstressed;
    # under 0.5 it holds and its earliest break is severe
    assert map_crossed(maps["strict"]) and not map_crossed(maps["default"])
    assert handoff_triggers(failure_map=maps["strict"]) == ["failure_threshold_crossed"]
    assert handoff_triggers(failure_map=maps["default"]) == []


def test_a_failure_map_also_crosses_when_a_variable_breaks_early():
    holding = {
        "baseline": {"survival_rate": 0.9},
        "survival_threshold": 0.5,
        "variables": [{"variable": "weather_degradation", "breaking_level": None}],
    }
    for level, crossed in (
        ("mild", True),
        ("moderate", True),
        ("severe", False),
        ("collapse", False),
    ):
        holding["variables"].append(
            {"variable": "sensor_failure", "breaking_level": level}
        )
        assert map_crossed(holding) is crossed, level
        holding["variables"].pop()


def test_a_conflict_that_requires_a_decision_is_handed_off():
    package = {"recommendation_to_nexus": {"required_decision": True}}
    settled = {"recommendation_to_nexus": {"required_decision": False}}

    assert handoff_triggers(conflict_package=package) == ["conflicting_branches"]
    assert handoff_triggers(conflict_package=settled) == []


# ── the handoff package ──────────────────────────────────────────────────────


def test_the_package_carries_the_seven_items_and_may_never_execute():
    result = run(SQUAD, 43, ("all_entities_destroyed", "perspective_eliminated"))

    handoff = authority_handoff(handoff_triggers(result), result=result)

    assert handoff["triggers"] == ["high_risk_outcome", "failure_threshold_crossed"]
    assert set(handoff) >= {
        "result_summary",
        "branch_comparison",
        "failure_map",
        "required_decision",
        "skyvault_position",
        "may_recommend",
        "may_execute_final_decision",
    }
    assert (
        handoff["may_recommend"] is True
        and handoff["may_execute_final_decision"] is False
    )
    assert handoff["status"] == "awaiting_decision" and handoff["decision"] is None
    assert handoff["decision_authority"] == ["NEXUS", "SOVEREIGN"]
    assert handoff["result_summary"]["run"]["result"] == "BLUE_survived"
    assert handoff["skyvault_position"]["statement"].startswith(
        "SKYVAULT simulated and recommends; it does not decide."
    )
    assert (
        handoff["skyvault_position"]["recommended_next_tests"]
        == result["evaluation_result"]["recommended_next_tests"]
    )
    assert (
        authority_handoff(handoff_triggers(result), result=result)["handoff_id"]
        == handoff["handoff_id"]
    )


def test_a_failure_map_handoff_lists_where_the_plan_breaks(maps):
    handoff = authority_handoff(
        handoff_triggers(failure_map=maps["strict"]), failure_map=maps["strict"]
    )

    assert (
        handoff["failure_map"]["baseline_survival_rate"]
        == maps["strict"]["baseline"]["survival_rate"]
    )
    assert set(handoff["failure_map"]["breaking_levels"].values()) == {"mild"}
    assert (
        "stress sensor_failure below mild"
        in handoff["skyvault_position"]["recommended_next_tests"]
    )


def test_only_an_authority_decides_and_only_once():
    handoff = authority_handoff(["strategic_tradeoff"], result=run(REFERENCE, 42))

    for impostor in ("SKYVAULT", "TAC_ANGEL", "STARTX"):
        with pytest.raises(PermissionError):
            decide(handoff, impostor, "go ahead")
    decided = decide(handoff, "SOVEREIGN", "hold the plan")
    assert (decided["status"], decided["decided_by"], decided["decision"]) == (
        "decided",
        "SOVEREIGN",
        "hold the plan",
    )
    with pytest.raises(ValueError, match="already decided"):
        decide(decided, "NEXUS", "go ahead")


def test_the_contract_refuses_a_handoff_that_could_execute_or_a_stranger_decided():
    handoff = authority_handoff(["strategic_tradeoff"], result=run(REFERENCE, 42))

    for broken in (
        {**handoff, "may_execute_final_decision": True},
        {**handoff, "may_recommend": False},
        {**handoff, "status": "decided"},
        {**handoff, "status": "decided", "decided_by": "SKYVAULT"},
        {**handoff, "triggers": []},
        {**handoff, "triggers": ["gut_feeling"]},
    ):
        with pytest.raises(ContractError):
            validate_authority_handoff(broken)


# ── the submission window ────────────────────────────────────────────────────


def submit_all(window, actions):
    return [
        window.submit(
            a["tick"],
            a["system"],
            a["actor_id"],
            {k: v for k, v in a.items() if k not in ("system", "tick", "actor_id")},
        )
        for a in actions
    ]


def test_actions_wait_in_the_window_named_by_system():
    window = SubmissionWindow()
    proposals = submit_all(window, SUBMISSIONS["conflicting_actions"])

    assert [p["proposal_id"] for p in proposals] == [
        "TAC_ANGEL:1",
        "STARTX:2",
        "HADES:3",
    ]
    assert [p["system_id"] for p in proposals] == ["TAC_ANGEL", "STARTX", "HADES"]
    assert window.take(1) == proposals and window.take(1) == []


def test_a_malformed_action_is_refused_at_the_window():
    with pytest.raises(Exception, match="action_type"):
        SubmissionWindow().submit(
            1, "TAC_ANGEL", "red_001", {"target": {"location": [1, 1]}}
        )


def test_the_fixture_actions_conflict_and_the_tac_angel_plan_does_not():
    base = load_scenario(REFERENCE)
    window = SubmissionWindow()
    conflicting = submit_all(window, SUBMISSIONS["conflicting_actions"])
    plan_ = submit_all(
        window,
        [
            dict(a, system="TAC_ANGEL")
            for a in SUBMISSIONS["tac_angel_plan"]["actions"][:1]
        ],
    )

    kinds = {k for c in find_conflicts(base, conflicting) for k in c["conflict_types"]}
    assert {"location_conflict", "objective_conflict"} <= kinds
    assert find_conflicts(base, plan_) == []


# ── a running world: carried out, or held at the conflict ────────────────────


@pytest.fixture
def world():
    store = SQLiteStore()
    policy = load_governance()
    request = {"kind": "persistent_world", "scenario": "tactical_reference_001/v0.1"}
    job = new_job(store, request, plan(request, policy, 0, store), policy)
    return PersistentWorld(job["job_id"], full_request(request), policy, store), store


def test_actions_that_do_not_conflict_are_carried_out_under_their_system(world):
    world_, store = world
    for a in SUBMISSIONS["tac_angel_plan"]["actions"]:
        order = {k: v for k, v in a.items() if k not in ("tick", "actor_id")}
        world_.submit("TAC_ANGEL", a["tick"], a["actor_id"], order)

    state = world_.advance(3)
    events = world_.finish()["event_memory"]

    assert state["tick"] == 3 and state["awaiting_decision"] is None
    moves = [
        (e["time"], e["source"]["system_id"])
        for e in events
        if e["event_type"] == "MOVE"
        and e["source"].get("actor_id") == "red_001"
        and e["time"] <= 3
    ]
    assert moves == [(1, "TAC_ANGEL"), (2, "TAC_ANGEL"), (3, "TAC_ANGEL")]
    assert any(
        e["message"] == "carrying out TAC_ANGEL:3 at tick 3"
        for e in store.events(world_.world_id)
    )


def test_conflicting_actions_hold_the_world_until_an_authority_decides(world):
    world_, store = world
    submit_all(world_.window, SUBMISSIONS["conflicting_actions"])

    state = world_.advance(5)
    record = store.get_conflict("conflict_000001")

    # nothing of tick 1 was played: the world waits at tick 0
    assert state["tick"] == 0 and state["awaiting_decision"] == "conflict_000001"
    assert record["status"] == "awaiting_decision" and record["decided_by"] is None
    assert sorted(record["branches"]) == ["STARTX:2+HADES:3", "TAC_ANGEL:1", "none"]
    assert (
        record["conflict_package"]["recommendation_to_nexus"]["required_decision"]
        is True
    )
    assert record["handoff"]["triggers"] == ["conflicting_branches"]
    with pytest.raises(WorldAwaiting):
        world_.advance(1)
    with pytest.raises(ValueError, match="has been played"):
        world_.submit(
            "TAC_ANGEL",
            0,
            "red_001",
            {"action_type": "move", "target": {"location": [1, 0]}},
        )


def test_skyvault_itself_never_picks_a_branch(world):
    world_, store = world
    submit_all(world_.window, SUBMISSIONS["conflicting_actions"])
    world_.advance(1)

    for impostor in ("SKYVAULT", "TAC_ANGEL", "STARTX", "HADES"):
        with pytest.raises(PermissionError):
            world_.decide("conflict_000001", "TAC_ANGEL:1", impostor)

    assert store.get_conflict("conflict_000001")["status"] == "awaiting_decision"
    assert world_.state()["awaiting_decision"] == "conflict_000001"


def test_an_authority_picks_a_branch_and_the_world_goes_on_with_it(world):
    world_, store = world
    submit_all(world_.window, SUBMISSIONS["conflicting_actions"])
    world_.advance(1)

    decided = world_.decide("conflict_000001", "STARTX:2+HADES:3", "NEXUS")
    state = world_.advance(2)
    events = world_.finish()["event_memory"]

    assert (
        decided["status"] == "decided" and decided["handoff"]["decided_by"] == "NEXUS"
    )
    assert state["tick"] == 2 and state["awaiting_decision"] is None
    tick1 = {
        (e["source"]["actor_id"], e["source"]["system_id"])
        for e in events
        if e["time"] == 1 and e["event_type"] == "ACTION_SELECTED"
    }
    assert {("red_001", "STARTX"), ("red_002", "HADES")} <= tick1
    assert ("red_001", "TAC_ANGEL") not in tick1
    with pytest.raises(ValueError, match="already decided by NEXUS"):
        world_.decide("conflict_000001", "none", "NEXUS")
    assert any(
        e["message"] == "NEXUS decided conflict_000001: branch STARTX:2+HADES:3"
        for e in store.events(world_.world_id)
    )


def test_choosing_none_keeps_none_of_the_conflicting_actions(world):
    world_, store = world
    submit_all(world_.window, SUBMISSIONS["conflicting_actions"])
    world_.advance(1)

    world_.decide("conflict_000001", "none", "SOVEREIGN")
    world_.advance(1)
    events = world_.finish()["event_memory"]

    systems = {
        e["source"]["system_id"]
        for e in events
        if e["time"] == 1 and e["event_type"] == "ACTION_SELECTED"
    }
    assert not systems & {"TAC_ANGEL", "STARTX", "HADES"}


def test_each_branch_is_the_same_history_forked_at_the_conflict(world):
    world_, store = world
    early = SUBMISSIONS["tac_angel_plan"]["actions"][0]
    world_.submit(
        "TAC_ANGEL",
        1,
        early["actor_id"],
        {"action_type": "move", "target": early["target"]},
    )
    world_.advance(1)
    late = [dict(a, tick=2) for a in SUBMISSIONS["conflicting_actions"]]
    late[0]["target"] = {"location": [2, 2]}
    submit_all(world_.window, late)
    world_.advance(1)
    record = store.get_conflict("conflict_000001")

    # the branch that keeps STARTX's order, whatever the window numbered it
    chosen = next(b for b in record["branches"] if b.startswith("STARTX"))
    world_.decide("conflict_000001", chosen, "NEXUS")
    world_.advance(20)
    lived = [
        e for e in world_.finish()["event_memory"] if e["event_type"] != "SCENARIO_END"
    ]

    # the branch's first run, replayed by hand: the earlier action plus the chosen ones
    base = load_scenario(REFERENCE)
    base["runtime"]["scheduled_actions"] = list(world_.applied[:1])
    by_id = {p["proposal_id"]: p for p in record["proposals"]}
    branch = branch_variant(
        base,
        chosen,
        [by_id[p] for p in record["branches"][chosen]],
    )
    replayed = SkyVaultTacticalReferenceEngine(branch.scenario).run()["event_memory"][
        :-1
    ]

    def strip(e):
        return (
            e["time"],
            e["event_type"],
            e["source"].get("actor_id"),
            e["target_entity_id"],
            e["after_state"],
        )

    assert [strip(e) for e in lived][: len(replayed)] == [strip(e) for e in replayed]


def test_a_decided_conflict_and_an_unknown_branch_are_refused():
    record = {
        "conflict_id": "conflict_000009",
        "status": "awaiting_decision",
        "branches": {"A:1": ["A:1"], "none": []},
        "proposals": [{"proposal_id": "A:1"}],
        "handoff": authority_handoff(
            ["conflicting_branches"],
            conflict_package={
                "conflict_id": "c",
                "conflict_type": ["location_conflict"],
                "branch_runs": [],
                "recommendation_to_nexus": {
                    "required_decision": True,
                    "decision_reason": "x",
                },
            },
        ),
    }

    with pytest.raises(KeyError, match="no branch"):
        resolve(record, "B:2", "NEXUS")
    decided, kept = resolve(record, "A:1", "NEXUS")
    assert kept == [{"proposal_id": "A:1"}]
    with pytest.raises(ValueError, match="already decided"):
        resolve(decided, "none", "NEXUS")


def test_a_closed_world_takes_no_more_actions(world):
    world_, _ = world
    world_.finish()

    with pytest.raises(WorldClosed):
        world_.submit(
            "TAC_ANGEL",
            5,
            "red_001",
            {"action_type": "move", "target": {"location": [1, 0]}},
        )
    with pytest.raises(WorldClosed):
        world_.advance(1)


def test_an_unknown_unit_is_refused(world):
    world_, _ = world

    with pytest.raises(KeyError, match="no unit"):
        world_.submit(
            "TAC_ANGEL",
            1,
            "red_999",
            {"action_type": "move", "target": {"location": [1, 0]}},
        )


# ── jobs hand off, and STARTX compares branches ──────────────────────────────


def test_every_job_records_whether_it_hands_off():
    store, policy = SQLiteStore(), load_governance()

    def done(request):
        job = new_job(store, request, plan(request, policy, 0, store), policy)
        execute_job(job["job_id"], store, policy)
        return store.get_job(job["job_id"])["summary"]["handoff"]

    assert done({"kind": "scenario_run", "scenario": "tactical_reference_001/v0.1"})[
        "triggers"
    ] == ["strategic_tradeoff"]
    assert done(
        {"kind": "batch", "batch": "tactical_reference_001", "repeat_count": 2}
    )["triggers"] == ["conflicting_branches"]
    assert (
        done(
            {
                "kind": "failure_exploration",
                "scenario": "tactical_reference_001/v0.1",
                "repeat_count": 1,
            }
        )
        is None
    )


def test_startx_branches_are_compared_with_the_baseline():
    store, policy = SQLiteStore(), load_governance()
    branches = SUBMISSIONS["startx_branches"]
    request = {
        "kind": "branch_compare",
        "scenario": branches["scenario"],
        "branches": branches["branches"],
        "repeat_count": 5,
        "source_system": "STARTX",
    }

    planned = plan(request, policy, 0, store)
    job = new_job(store, request, planned, policy)
    execute_job(job["job_id"], store, policy)
    result = store.get_result(job["job_id"])

    # (2 branches + the baseline) x 5 runs
    assert planned["estimated_cost"]["runs"] == 15 == len(result["runs"])
    assert sorted(result["branch_comparison"]["table"]) == [
        "branch:hold",
        "branch:none",
        "branch:press",
    ]
    assert {r["variant_id"] for r in result["runs"]} == {
        "branch:press",
        "branch:hold",
        "branch:none",
    }


def test_a_branch_that_orders_one_unit_twice_is_refused_at_the_door():
    twice = [
        {
            "branch_id": "muddle",
            "actions": [
                {
                    "tick": 1,
                    "actor_id": "red_002",
                    "action_type": "move",
                    "target": {"location": [2, 1]},
                },
                {
                    "tick": 1,
                    "actor_id": "red_002",
                    "action_type": "move",
                    "target": {"location": [0, 1]},
                },
            ],
        }
    ]

    with pytest.raises(ContractError, match="two scheduled actions"):
        plan(
            {
                "kind": "branch_compare",
                "scenario": "tactical_reference_001/v0.1",
                "branches": twice,
            },
            load_governance(),
            0,
        )


def test_a_branch_keeps_what_its_base_already_scheduled():
    base = load_scenario(REFERENCE)
    earlier = {
        "tick": 1,
        "actor_id": "red_001",
        "system_id": "TAC_ANGEL",
        "action_type": "move",
        "target": {"location": [1, 1]},
    }
    base["runtime"]["scheduled_actions"] = [earlier]
    later = {**earlier, "tick": 2, "target": {"location": [2, 2]}, "proposal_id": "P1"}

    scheduled = branch_variant(base, "P1", [later]).scenario["runtime"][
        "scheduled_actions"
    ]

    assert [a["tick"] for a in scheduled] == [1, 2]
    assert scheduled[1]["metadata"] == {"proposal_id": "P1"}


def test_a_world_decides_only_the_conflict_it_waits_on(world):
    world_, store = world
    submit_all(world_.window, SUBMISSIONS["conflicting_actions"])
    world_.advance(1)
    # another world's conflict, still awaiting, in the same store
    other = store.save_conflict(
        {**store.get_conflict("conflict_000001"), "world_id": "job_000099"}
    )
    with pytest.raises(KeyError, match="not waiting on conflict_000002"):
        world_.decide(other["conflict_id"], "none", "NEXUS")
    assert world_.state()["awaiting_decision"] == "conflict_000001"
