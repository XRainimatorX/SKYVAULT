"""Formal Spec 8.2 / 8.3 axes and the section 16.2 anti-gaming document."""

import copy
import json

import pytest
from conftest import REPO_ROOT

from skyvault.compiler import compile_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario

DATA = REPO_ROOT / "data" / "scenarios"


def document(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def urban():
    return SkyVaultEngine(
        load_scenario(DATA / "military_urban_001" / "v0.2.json")
    ).run()


@pytest.fixture(scope="module")
def city():
    return SkyVaultEngine(load_scenario(DATA / "city_blackout_001" / "v0.1.json")).run()


def test_equipment_brought_into_a_scenario_is_screened_on_the_first_two_axes():
    scenario = document("military_urban_001/v0.1")
    scenario["participants"]["equipment_profiles"] = ["exo_test_001", "msx_test_001"]

    package = SkyVaultEngine(compile_scenario(scenario)).run()
    scores = package["evaluation_result"]["scores"]
    breakdown = package["score_breakdown"]

    assert scores["physical_possibility"] == pytest.approx(0.4774, abs=1e-4)
    assert scores["engineering_feasibility"] == pytest.approx(0.4934, abs=1e-4)
    assert "exo_test_001 0.95" in breakdown["physical_possibility"]["explanation"]
    assert breakdown["physical_possibility"]["in_scope"] is True


def test_without_equipment_the_first_two_axes_are_null_and_say_why(urban):
    scores = urban["evaluation_result"]["scores"]
    breakdown = urban["score_breakdown"]

    assert scores["physical_possibility"] is None
    assert scores["engineering_feasibility"] is None
    assert "participants.equipment_profiles" in (
        breakdown["engineering_feasibility"]["explanation"]
    )


def test_a_city_measures_governance_and_crisis_in_its_own_terms(city):
    scores = city["evaluation_result"]["scores"]
    breakdown = city["score_breakdown"]

    assert scores["governance_stability"] == pytest.approx(0.4691, abs=1e-4)
    assert scores["crisis_resilience"] == pytest.approx(0.535, abs=1e-3)
    assert breakdown["crisis_resilience"]["explanation"].startswith(
        "lowest governance score 0.28 at tick 13"
    )


def test_a_world_without_order_does_not_judge_governance(urban):
    assert urban["evaluation_result"]["scores"]["governance_stability"] is None
    assert urban["score_breakdown"]["governance_stability"]["in_scope"] is False


def test_crisis_resilience_follows_own_strength_to_its_lowest_point(urban):
    entry = urban["score_breakdown"]["crisis_resilience"]

    assert entry["explanation"] == "own strength at its lowest 32 of 286 hp (tick 20)"
    assert urban["evaluation_result"]["scores"]["crisis_resilience"] == pytest.approx(
        32 / 286, abs=1e-4
    )


def test_the_run_level_axes_are_checklists_of_what_the_run_keeps(urban):
    axes = urban["evaluation_result"]["additional_axes"]
    breakdown = urban["score_breakdown"]

    assert axes["commercial_demonstrability"] == 1.0
    assert axes["imperial_core_value"] == 1.0
    assert "yes failure variables declared" in (
        breakdown["imperial_core_value"]["explanation"]
    )
    assert breakdown["imperial_core_value"]["weight"] == 0.0  # reported, not weighed


def test_an_unreplayable_run_loses_demonstrability_and_core_value():
    scenario = document("military_squad_001/v0.1")
    scenario["execution_settings"]["random_seed_policy"] = "stochastic"
    scenario["output"]["replay_required"] = False

    axes = SkyVaultEngine(compile_scenario(scenario)).run()["evaluation_result"][
        "additional_axes"
    ]

    assert axes["commercial_demonstrability"] == pytest.approx(2 / 3, abs=1e-4)
    # the squad's world declares no failure variables either: 2 of 4
    assert axes["imperial_core_value"] == pytest.approx(2 / 4, abs=1e-4)


def test_an_axis_a_domain_does_not_know_is_refused():
    from skyvault.evaluation import evaluate_run

    package = SkyVaultEngine(
        load_scenario(DATA / "military_squad_001" / "v0.1.json")
    ).run()
    summary = {
        k: package["evaluation_result"][k]
        for k in (
            "termination_reason",
            "event_count",
            "active_entities",
            "destroyed_entities",
            "active_factions",
            "winner_or_result",
            "key_findings",
            "failure_points",
        )
    }
    profile = copy.deepcopy(
        json.loads(
            (REPO_ROOT / "data" / "evaluation_profiles" / "balanced.json").read_text()
        )
    )
    profile["perspective"] = "RED"

    with pytest.raises(ValueError, match="unknown axis 'morale'"):
        evaluate_run(
            package["initial_world_state"],
            package["event_memory"],
            package["final_world_state"],
            summary,
            profile,
            40,
            domain_axes={"morale": (0.5, "made up")},
        )


# ── section 16.2 ─────────────────────────────────────────────────────────────


def test_the_anti_gaming_report_carries_section_16_2_field_by_field(urban):
    report = urban["anti_gaming_report"]

    assert {
        "scenario_id",
        "primary_metric",
        "secondary_metrics",
        "anti_gaming_metrics",
        "forbidden_optimization_behaviors",
        "tradeoff_report_required",
    } <= set(report)
    assert {entry["metric"] for entry in report["anti_gaming_metrics"]} >= {
        "inaction_penalty",
        "stability_penalty",
        "risk_spike_penalty",
    }
    assert all("reason" in entry for entry in report["anti_gaming_metrics"])
    assert {
        "maximize_score_by_inaction",
        "sacrifice_long_term_stability_for_short_term_success",
        "ignore_hidden_risk_to_improve_visible_score",
    } <= set(report["forbidden_optimization_behaviors"])
    assert report["tradeoff_report_required"] is True
