"""The engine judges every run under a profile and packages the Phase 7 outputs."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
PROFILES = REPO_ROOT / "data" / "evaluation_profiles"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import ContractError, validate_result_package
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import (
    default_evaluation_profile,
    load_evaluation_profile,
    load_scenario,
    scenario_perspective,
)

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"


def scenario():
    return load_scenario(REFERENCE_SCENARIO)


def test_without_a_profile_the_run_is_judged_by_balanced_from_the_first_side():
    engine = SkyVaultTacticalReferenceEngine(scenario())

    package = engine.run()

    verdict = package["evaluation_result"]
    assert engine.evaluation_profile["profile_id"] == "balanced"
    assert verdict["perspective"] == "RED"
    assert verdict["overall_judgement"]["status"] == "risky"
    assert package["tradeoff_report"]["profile_id"] == "balanced"


def test_a_scenario_can_declare_whose_plan_it_is():
    declared = scenario()
    declared["evaluation"]["perspective"] = "BLUE"

    assert scenario_perspective(declared) == "BLUE"
    assert default_evaluation_profile(declared)["perspective"] == "BLUE"
    verdict = SkyVaultTacticalReferenceEngine(declared).run()["evaluation_result"]
    assert verdict["overall_judgement"]["status"] == "fail"


def test_the_engine_judges_under_the_profile_it_is_given():
    tactical = load_evaluation_profile(PROFILES / "tactical.json")

    package = SkyVaultTacticalReferenceEngine(scenario(), tactical).run()

    assert package["evaluation_result"]["profile_id"] == "tactical"
    assert package["evaluation_result"]["perspective"] == "RED"
    assert package["evaluation_result"]["overall_judgement"]["status"] == "pass"


def test_a_broken_profile_fails_before_the_run_starts():
    broken = load_evaluation_profile(PROFILES / "tactical.json")
    broken["weights"] = {"luck": 1.0}

    with pytest.raises(ContractError, match="evaluation_profile"):
        SkyVaultTacticalReferenceEngine(scenario(), broken)


def test_every_package_carries_the_three_phase_7_outputs():
    package = SkyVaultTacticalReferenceEngine(scenario()).run()

    validate_result_package(package)
    assert set(package["score_breakdown"]) == set(
        load_evaluation_profile(PROFILES / "balanced.json")["weights"]
    )
    assert package["anti_gaming_report"]["scenario_id"] == "tactical_reference_001"
    assert package["tradeoff_report"]["required"] is True


def test_changing_the_profile_never_changes_what_happened():
    tactical = load_evaluation_profile(PROFILES / "tactical.json")

    balanced_run = SkyVaultTacticalReferenceEngine(scenario()).run()
    tactical_run = SkyVaultTacticalReferenceEngine(scenario(), tactical).run()

    def facts(package):
        return [
            (e["time"], e["event_type"], e["source"]["actor_id"], e["data"])
            for e in package["event_memory"]
        ]

    assert facts(balanced_run) == facts(tactical_run)
    assert balanced_run["final_world_state"] == tactical_run["final_world_state"]
