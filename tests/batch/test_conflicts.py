"""Conflicting orders: detected, branched, packaged — never decided."""

import ast
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
SCENARIOS = REPO_ROOT / "data" / "scenarios"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
BATCH = REPO_ROOT / "data" / "batches" / "tactical_reference_001.json"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.batch.aggregate import aggregate, render_comparative_report
from skyvault.batch.conflicts import (
    build_conflict_package,
    compatible_sets,
    detect_conflicts,
)
from skyvault.batch.run import run_batch
from skyvault.contracts import validate_conflict_package
from skyvault.scenario_loader import load_scenario

REFERENCE = load_scenario(SCENARIOS / "tactical_reference_001" / "v0.1.json")
LOGISTICS = load_scenario(FIXTURES / "scenario_logistics.json")


def order(pid, actor, action_type="move", tick=1, **extra):
    target = {
        "entity_id": extra.pop("entity", None),
        "location": extra.pop("location", None),
        "system_id": None,
    }
    return {
        "proposal_id": pid,
        "tick": tick,
        "system_id": extra.pop("system", "TAC_ANGEL"),
        "actor_id": actor,
        "action_type": action_type,
        "target": target,
        "intent": extra.pop("intent", ""),
        **extra,
    }


def types(scenario, *proposals):
    return [c["conflict_types"] for c in detect_conflicts(scenario, list(proposals))]


# ── the six conflict types ───────────────────────────────────────────────────


def test_one_actor_given_two_orders_is_an_objective_conflict():
    first = order("A", "red_002", location=[1, 1], priority="high")
    second = order("B", "red_002", location=[0, 1], priority="normal")

    assert types(REFERENCE, first, second) == [["objective_conflict"]]


def test_two_actors_on_two_places_do_not_conflict():
    first = order("A", "red_002", location=[1, 1], priority="high")
    second = order("B", "red_001", location=[0, 1], priority="high")

    assert types(REFERENCE, first, second) == []


def test_two_actors_sent_to_one_place_is_a_location_conflict():
    first = order("A", "red_002", location=[1, 1], priority="high")
    second = order("B", "red_001", location=[1, 1], priority="normal")

    assert types(REFERENCE, first, second) == [["location_conflict"]]


def test_only_orders_that_occupy_a_place_can_clash_over_it():
    first = order("A", "red_002", location=[1, 1])
    second = order("B", "red_001", "observe", location=[1, 1])

    assert types(REFERENCE, first, second) == []


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            order("A", "red_002", location=[1, 1], priority="high"),
            order("B", "red_002", location=[0, 1], priority="high"),
        ),
        (
            order("A", "red_002", location=[1, 1], priority="high"),
            order("B", "red_001", location=[1, 1], priority="high"),
        ),
    ],
    ids=["same actor", "same place"],
)
def test_equal_priority_adds_a_priority_conflict(first, second):
    [found] = types(REFERENCE, first, second)

    assert "priority_conflict" in found


def test_equal_priority_alone_is_no_conflict():
    first = order("A", "red_002", location=[1, 1], priority="high")
    second = order("B", "red_001", location=[0, 1], priority="high")

    assert types(REFERENCE, first, second) == []


def test_harming_and_supporting_one_entity_is_an_objective_conflict():
    first = order("A", "red_001", "attack", entity="red_003")
    second = order("B", "red_002", "repair", entity="red_003")

    assert types(REFERENCE, first, second) == [["objective_conflict"]]


def test_two_orders_that_change_one_entity_are_a_timing_conflict():
    # red_003 repairing itself (no target) and red_002 repairing red_003
    first = order("A", "red_003", "repair")
    second = order("B", "red_002", "repair", entity="red_003")

    assert types(REFERENCE, first, second) == [["timing_conflict"]]


def test_orders_on_different_entities_have_no_timing_conflict():
    first = order("A", "red_003", "repair")
    second = order("B", "red_002", "repair", entity="red_001")

    assert types(REFERENCE, first, second) == []


def test_orders_affordable_alone_but_not_together_are_a_resource_conflict():
    first = order("A", "truck_1", location="junction", required_resources={"fuel": 30})
    second = order("B", "squad_1", location="depot", required_resources={"fuel": 30})

    assert types(LOGISTICS, first, second) == [["resource_conflict"]]


@pytest.mark.parametrize(
    ("fuel", "other"),
    [(20, 30), (60, 10)],
    ids=["fits together", "one alone is unaffordable"],
)
def test_no_resource_conflict_unless_each_fits_and_both_do_not(fuel, other):
    first = order(
        "A", "truck_1", location="junction", required_resources={"fuel": fuel}
    )
    second = order("B", "squad_1", location="depot", required_resources={"fuel": other})

    assert types(LOGISTICS, first, second) == []


def test_the_rule_set_cost_is_what_counts():
    # The world charges repair 1 spare part, whatever the order asks for
    first = order("A", "truck_1", "repair", required_resources={"fuel": 30})
    second = order("B", "squad_1", "repair", required_resources={"fuel": 30})

    assert types(LOGISTICS, first, second) == []


def test_a_different_risk_level_adds_a_risk_conflict():
    first = order("A", "red_002", location=[1, 1], risk_profile={"level": "medium"})
    second = order("B", "red_002", location=[0, 1], risk_profile={"level": "low"})

    [found] = types(REFERENCE, first, second)

    assert "risk_conflict" in found


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            order("A", "red_002", location=[1, 1], risk_profile={"level": "low"}),
            order("B", "red_002", location=[0, 1], risk_profile={"level": "low"}),
        ),
        (
            order("A", "red_002", location=[1, 1], risk_profile={"level": "high"}),
            order("B", "red_001", location=[0, 1], risk_profile={"level": "low"}),
        ),
        (
            order("A", "red_002", location=[1, 1], risk_profile={"level": "high"}),
            order("B", "red_002", location=[0, 1]),
        ),
    ],
    ids=["same level", "no other conflict", "one level unknown"],
)
def test_no_risk_conflict_otherwise(first, second):
    for found in types(REFERENCE, first, second):
        assert "risk_conflict" not in found


def test_orders_for_different_ticks_never_conflict():
    first = order("A", "red_002", location=[1, 1], tick=1)
    second = order("B", "red_002", location=[0, 1], tick=2)

    assert types(REFERENCE, first, second) == []


# ── the reference proposals ──────────────────────────────────────────────────


def proposals():
    with BATCH.open(encoding="utf-8") as file:
        return json.load(file)["conflicts"]["proposals"]


def test_the_reference_proposals_conflict_twice():
    conflicts = detect_conflicts(REFERENCE, proposals())

    assert [
        (c["conflict_id"], c["proposals"], c["conflict_types"]) for c in conflicts
    ] == [
        (
            "C1",
            ["P1", "P2"],
            ["objective_conflict", "priority_conflict", "risk_conflict"],
        ),
        ("C2", ["P1", "P3"], ["location_conflict"]),
    ]
    assert conflicts[0]["reason"] == (
        "P1 vs P2 at tick 1: both order red_002; both high priority; risk medium vs low"
    )


def test_compatible_sets_are_the_maximal_sets_without_a_conflict():
    assert compatible_sets(proposals(), detect_conflicts(REFERENCE, proposals())) == [
        ["P1"],
        ["P2", "P3"],
    ]


def test_compatible_sets_follow_request_order():
    chain = [order(p, "x") for p in "ABC"]
    conflicts = [{"proposals": ["A", "B"]}, {"proposals": ["B", "C"]}]

    assert compatible_sets(chain, conflicts) == [["A", "C"], ["B"]]
    assert compatible_sets(chain, []) == [["A", "B", "C"]]
    assert compatible_sets([], []) == []


# ── the package never decides ────────────────────────────────────────────────


def stats(variant, wins, fails, hp):
    records = [
        {
            "variant_id": variant,
            "kind": "branch",
            "scenario_version": "v",
            "seed": i,
            "outcome": "RED_survived" if i < wins else "no_winner_duration_limit",
            "status": "fail" if i < fails else "risky",
            "score": 0.5,
            "hp_lost": hp,
            "risk_events": 1.0,
            "event_count": 90,
            "output_hash": f"h{i}",
        }
        for i in range(10)
    ]
    [result] = aggregate(records, "RED")
    return result


def package(**overrides):
    conflicts = detect_conflicts(REFERENCE, proposals())
    branches = overrides.get(
        "branches", [stats("branch:P1", 5, 4, 60.0), stats("branch:P2+P3", 2, 1, 50.0)]
    )
    return build_conflict_package(
        REFERENCE, proposals(), conflicts, branches, stats("branch:none", 1, 3, 70.0)
    )


def test_every_branch_is_measured_against_the_baseline():
    result = validate_conflict_package(package())
    first, second = result["branch_runs"]

    assert (first["branch_id"], first["action_set"]) == ("P1", ["P1"])
    assert (second["branch_id"], second["action_set"]) == ("P2+P3", ["P2", "P3"])
    assert first["evaluation_delta"]["win_rate"] == 0.4
    assert second["evaluation_delta"]["mean_hp_lost"] == -20.0
    assert result["baseline"]["branch_id"] == "none"
    assert set(result["baseline"]["evaluation_delta"].values()) == {0.0}
    assert first["result_summary"].startswith("10 runs: win 50% (95% CI")


def test_the_package_lists_who_conflicts_with_whom():
    result = package()

    assert [
        (a["action_id"], a["conflict_with"]) for a in result["conflicting_actions"]
    ] == [
        ("P1", ["P2", "P3"]),
        ("P2", ["P1"]),
        ("P3", ["P1"]),
    ]
    assert result["conflicting_actions"][1]["system_id"] == "HADES"
    assert result["conflict_type"] == [
        "objective_conflict",
        "location_conflict",
        "priority_conflict",
        "risk_conflict",
    ]


def test_the_recommendation_states_trade_offs_and_leaves_the_choice():
    recommendation = package()["recommendation_to_nexus"]
    reason = recommendation["decision_reason"]

    assert recommendation["required_decision"] is True
    # P1 wins more, P2+P3 fails less and loses less hp: both are said
    assert "Highest win_rate: branch P1 (0.5)" in reason
    assert "Lowest failure_frequency: branch P2+P3 (0.1)" in reason
    assert "Lowest mean_hp_lost: branch P2+P3 (50)" in reason
    assert "Highest mean_score: branch P1 (0.5)" in reason  # a tie names the first
    assert "does not choose" in reason


def test_without_conflicts_no_decision_is_required():
    calm = [
        order("A", "red_002", location=[1, 1]),
        order("B", "red_001", location=[0, 1]),
    ]

    result = build_conflict_package(
        REFERENCE,
        calm,
        [],
        [stats("branch:A+B", 1, 1, 50.0)],
        stats("none", 1, 1, 50.0),
    )

    assert result["recommendation_to_nexus"]["required_decision"] is False
    assert result["conflicting_actions"] == []
    assert result["conflict_id"].endswith(":none")


def test_one_result_per_compatible_set_is_required():
    with pytest.raises(ValueError, match="2 compatible sets but 1 branch results"):
        package(branches=[stats("branch:P1", 5, 4, 60.0)])


# ── acceptance 4–7 through run_batch ─────────────────────────────────────────


@pytest.fixture(scope="module")
def branched():
    with BATCH.open(encoding="utf-8") as file:
        request = json.load(file)
    request["variants"], request["sweeps"] = [], []
    return run_batch(request, repeats=5)


def test_every_compatible_set_runs_as_its_own_branch(branched):
    result = branched["batch_result"]

    assert [s["variant_id"] for s in result["variants"]] == [
        "branch:P1",
        "branch:P2+P3",
        "branch:none",
    ]
    assert result["total_runs"] == 15
    assert {r["scenario_version"] for r in result["runs"]} == {
        "v0.1+branch:P1",
        "v0.1+branch:P2+P3",
        "v0.1+branch:none",
    }


def test_the_orders_change_what_happens(branched):
    table = branched["branch_comparison"]["table"]

    assert table["branch:P1"] != table["branch:none"]
    assert table["branch:P2+P3"] != table["branch:none"]


def test_the_conflict_package_passes_its_contract_and_asks_for_a_decision(branched):
    result = branched["conflict_package"]

    assert validate_conflict_package(result) == result
    assert [b["branch_id"] for b in result["branch_runs"]] == ["P1", "P2+P3"]
    assert result["recommendation_to_nexus"]["required_decision"] is True


def test_the_report_puts_variants_branches_and_the_open_decision_together(branched):
    report = render_comparative_report(
        branched["batch_result"],
        branched["branch_comparison"],
        branched["conflict_package"],
    )

    assert report.startswith("# Comparative report — tactical_reference_001_doctrine")
    assert "| branch:P1 | branch |" in report
    assert "- C2: P1 vs P3 at tick 1: both send a unit to [1, 1]" in report
    assert "| none | — |" in report
    assert "Decision required: **yes**" in report

    plain = render_comparative_report(
        branched["batch_result"], branched["branch_comparison"]
    )
    assert "Conflicting orders" not in plain


def test_conflict_detection_imports_nothing_that_runs_a_simulation():
    path = SRC_PATH / "skyvault" / "batch" / "conflicts.py"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            assert (node.module, node.level) == ("aggregate", 1)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in ("itertools", "typing")
        elif isinstance(node, ast.Import):
            assert all(alias.name == "networkx" for alias in node.names)
