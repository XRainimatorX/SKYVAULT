"""The verdict, anti-gaming and the trade-off report, on runs the engine made."""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
PROFILES = REPO_ROOT / "data" / "evaluation_profiles"

for path in (SRC_PATH, REPO_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from reference_trace import reference_package  # noqa: E402

from skyvault.contracts import ANTI_GAMING_BEHAVIORS
from skyvault.engine import SkyVaultEngine
from skyvault.evaluation import BEHAVIORS, evaluate_run, render_tradeoff_report
from skyvault.scenario_loader import load_evaluation_profile, load_scenario

REFERENCE_SCENARIO = (
    REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"
)


def profile(name: str, perspective: str = "RED", **changes) -> dict:
    loaded = load_evaluation_profile(PROFILES / f"{name}.json")
    loaded["perspective"] = perspective
    loaded.update(changes)
    return loaded


def evaluate(package, chosen, thresholds=("all_entities_destroyed",)):
    return evaluate_run(
        package["initial_world_state"],
        package["event_memory"],
        package["final_world_state"],
        package["evaluation_result"],
        chosen,
        10,
        list(thresholds),
    )


def run_with(seed=None, idle=False):
    scenario = load_scenario(REFERENCE_SCENARIO)
    if seed is not None:
        scenario["runtime"]["random_seed"] = seed
    engine = SkyVaultEngine(scenario)
    if idle:
        engine.policy.decide_action = lambda world, actor: None
    return engine.run()


@pytest.fixture(scope="module")
def reference():
    return reference_package()


# ── acceptance 1: the same run under different profiles ─────────────────────


def test_two_profiles_judge_the_same_run_differently(reference):
    balanced = evaluate(reference, profile("balanced"))["evaluation_result"]
    tactical = evaluate(reference, profile("tactical"))["evaluation_result"]

    assert balanced["overall_judgement"] == {"status": "risky", "confidence": 0.9231}
    assert balanced["overall_score"] == pytest.approx(0.5045, abs=1e-4)
    assert tactical["overall_judgement"] == {"status": "pass", "confidence": 1.0}
    assert tactical["overall_score"] == pytest.approx(0.7775, abs=1e-4)
    assert balanced["profile_id"] == "balanced"
    assert tactical["profile_id"] == "tactical"


def test_the_overall_score_is_the_weighted_mean_minus_penalties(reference):
    result = evaluate(reference, profile("balanced"))
    breakdown = result["score_breakdown"]

    counted = [e for e in breakdown.values() if e["applicable"] and e["weight"] > 0]
    mean = sum(e["score"] * e["weight"] for e in counted) / sum(
        e["weight"] for e in counted
    )

    penalty = result["anti_gaming_report"]["penalty_total"]
    assert penalty == 0.15
    assert result["evaluation_result"]["overall_score"] == pytest.approx(
        mean - penalty, abs=1e-3
    )


# ── acceptance 2 and 3: more than a winner; costs, risks and failure points ──


def test_the_verdict_reports_eleven_axes_not_just_a_winner(reference):
    result = evaluate(reference, profile("balanced"))
    verdict = result["evaluation_result"]

    assert verdict["winner_or_result"] == "RED_survived"
    assert len(result["score_breakdown"]) == 11
    assert set(verdict["scores"]) == set(result["score_breakdown"]) - {
        "logistics_burden"
    }
    for axis in ("resource_cost", "time_cost", "risk_growth", "logistics_burden"):
        assert {"score", "raw", "unit", "explanation"} <= set(
            result["score_breakdown"][axis]
        )


def test_failure_causes_name_the_losses_and_the_weak_axes(reference):
    causes = evaluate(reference, profile("balanced"))["evaluation_result"][
        "failure_causes"
    ]

    assert causes == [
        "red_003 destroyed at tick 6 by blue_002",
        "time_cost 0.00: ended at tick 10 of 10",
        "recovery_ability 0.00: 0 hp restored against 40 hp still lost",
        "Anti-gaming: sacrifice_long_term_stability_for_short_term_success",
    ]


def test_an_axis_without_data_lowers_confidence_and_asks_for_a_test(reference):
    verdict = evaluate(reference, profile("balanced"))["evaluation_result"]

    assert verdict["overall_judgement"]["confidence"] == pytest.approx(
        12 / 13, abs=1e-4
    )
    assert (
        "Exercise logistics_burden: the world holds no resources to spend"
        in verdict["recommended_next_tests"]
    )


# ── acceptance 4 and 5: gaming is shown and flagged ─────────────────────────


def test_a_scorched_earth_win_is_flagged_as_sacrificing_stability(reference):
    verdict = evaluate(reference, profile("balanced"))["evaluation_result"]

    assert verdict["anti_gaming"] == {
        "gaming_detected": True,
        "flagged_behaviors": ["sacrifice_long_term_stability_for_short_term_success"],
        "penalty_total": 0.15,
    }


def test_doing_nothing_scores_high_on_cost_axes_and_is_flagged():
    idle = run_with(idle=True)
    cautious = profile(
        "balanced",
        weights={"resource_cost": 1.0, "strategic_value": 1.0, "stability_impact": 1.0},
    )

    result = evaluate(idle, cautious)
    verdict = result["evaluation_result"]

    assert idle["evaluation_result"]["winner_or_result"] == "no_winner_duration_limit"
    assert verdict["scores"]["resource_cost"] == 1.0
    assert verdict["scores"]["strategic_value"] == 1.0
    assert verdict["anti_gaming"]["flagged_behaviors"] == ["maximize_score_by_inaction"]
    inaction = result["anti_gaming_report"]["checks"][0]
    assert inaction["metric"] == "inaction_penalty"
    assert inaction["value"] == 1.0
    assert verdict["overall_score"] == pytest.approx(0.8)
    assert verdict["overall_judgement"]["status"] == "fail"  # mission_success is 0


def test_a_win_that_hides_a_critically_damaged_survivor_is_flagged():
    # Seed 11: BLUE wins with two survivors; blue_002 ends on 6 of its 32 hp
    package = run_with(seed=11)
    blue_002 = package["final_world_state"]["entities"]["blue_002"]["state"]

    verdict = evaluate(package, profile("balanced", perspective="BLUE"))[
        "evaluation_result"
    ]

    assert package["evaluation_result"]["winner_or_result"] == "BLUE_survived"
    assert (blue_002["hp"], blue_002["status"]) == (6, "active")
    assert (
        "ignore_hidden_risk_to_improve_visible_score"
        in verdict["anti_gaming"]["flagged_behaviors"]
    )


def test_a_tactical_win_that_burns_strategic_value_is_flagged(reference):
    chosen = profile("balanced")
    for check in chosen["anti_gaming_metrics"]:
        if check["metric"] == "long_term_cost_penalty":
            check["threshold"] = 0.7  # RED kept 2 of 3 units: 0.67

    verdict = evaluate(reference, chosen)["evaluation_result"]

    assert (
        "sacrifice_strategic_value_for_short_term_tactical_value"
        in verdict["anti_gaming"]["flagged_behaviors"]
    )


def test_a_tick_that_destroys_most_of_a_force_is_a_risk_spike(reference):
    chosen = profile("balanced", perspective="BLUE")
    for check in chosen["anti_gaming_metrics"]:
        if check["metric"] == "risk_spike_penalty":
            check["threshold"] = 0.2  # BLUE lost one of three units in a single tick

    report = evaluate(reference, chosen)["anti_gaming_report"]

    spike = next(c for c in report["checks"] if c["metric"] == "risk_spike_penalty")
    assert spike["value"] == pytest.approx(1 / 3, abs=1e-4)
    assert spike["triggered"]


def test_a_triggered_check_the_profile_allows_costs_nothing(reference):
    tactical = profile("tactical")
    tactical["anti_gaming_metrics"].append(
        {
            "metric": "stability_penalty",
            "reason": "reported, not forbidden",
            "threshold": 0.5,
            "penalty": 0.15,
        }
    )

    result = evaluate(reference, tactical)
    check = result["anti_gaming_report"]["checks"][-1]

    assert check["triggered"] and not check["forbidden"]
    assert check["penalty"] == 0.0
    assert not result["evaluation_result"]["anti_gaming"]["gaming_detected"]
    assert "Triggered but allowed by this profile" in render_tradeoff_report(
        result["tradeoff_report"]
    )


def test_the_behaviour_names_match_the_profile_contract():
    assert BEHAVIORS == ANTI_GAMING_BEHAVIORS


# ── the four verdicts ────────────────────────────────────────────────────────


def test_the_losing_side_fails_and_its_elimination_is_a_cause(reference):
    verdict = evaluate(
        reference, profile("tactical", perspective="BLUE"), ["perspective_eliminated"]
    )["evaluation_result"]

    assert verdict["overall_judgement"]["status"] == "fail"
    assert (
        "Failure threshold reached: perspective_eliminated" in verdict["failure_causes"]
    )


def test_a_middling_score_needs_more_testing(reference):
    strict = profile("tactical", thresholds={"pass": 0.9, "fail": 0.3})

    verdict = evaluate(reference, strict)["evaluation_result"]

    assert verdict["overall_judgement"]["status"] == "needs_more_test"


def test_an_unknown_failure_threshold_becomes_a_next_test(reference):
    verdict = evaluate(reference, profile("tactical"), ["moral_collapse"])[
        "evaluation_result"
    ]

    assert (
        "Failure threshold 'moral_collapse' is not evaluated yet"
        in verdict["recommended_next_tests"]
    )


# ── acceptance 6: the trade-off report ───────────────────────────────────────


def test_the_tradeoff_report_names_what_was_paid_for_what(reference):
    report = evaluate(reference, profile("balanced"))["tradeoff_report"]

    assert report["required"] is True
    assert report["judgement"]["status"] == "risky"
    pairs = {(t["gain"], t["cost"]): t["assessment"] for t in report["tradeoffs"]}
    assert pairs[("mission_success", "stability_impact")] == (
        "mission_success bought at the expense of stability_impact"
    )
    assert pairs[("tactical_value", "strategic_value")] == "both strong"
    assert report["strongest"][0] == {"metric": "mission_success", "score": 1.0}
    assert report["weakest"][0] == {"metric": "recovery_ability", "score": 0.0}


def test_the_markdown_report_carries_the_verdict_and_every_tradeoff(reference):
    text = render_tradeoff_report(
        evaluate(reference, profile("balanced"))["tradeoff_report"]
    )

    assert text.startswith("# Trade-off report — tactical_reference_001\n")
    assert "- Verdict: **risky** (overall 0.50, confidence 0.92)" in text
    assert text.count("\n| ") == 5  # header plus four trade-offs
    assert (
        "Gaming detected: sacrifice_long_term_stability_for_short_term_success." in text
    )


# ── purity and layering ──────────────────────────────────────────────────────


def test_evaluation_never_changes_its_inputs_and_repeats_itself(reference):
    before = copy.deepcopy(reference)

    first = evaluate(reference, profile("balanced"))
    second = evaluate(reference, profile("balanced"))

    assert reference == before
    assert first == second


def test_evaluation_needs_a_resolved_perspective(reference):
    with pytest.raises(ValueError, match="no perspective"):
        evaluate(reference, profile("balanced", perspective=None))


@pytest.mark.parametrize(
    "module",
    sorted((SRC_PATH / "skyvault" / "evaluation").glob("*.py")),
    ids=lambda path: path.name,
)
def test_evaluation_imports_nothing_from_the_project(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.level <= 1, f"{module.name} reaches outside evaluation/"
            assert not (node.module or "").startswith("skyvault")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("skyvault") for alias in node.names)


def test_profiles_are_plain_json_the_evaluation_can_read():
    with (PROFILES / "balanced.json").open(encoding="utf-8") as file:
        raw = json.load(file)

    assert raw["thresholds"] == {"pass": 0.6, "fail": 0.3}
