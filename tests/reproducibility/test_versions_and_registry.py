"""Phase 8 acceptance 2: versions compare; runs are registered and replayable."""

import ast
import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.reproducibility import (
    CHANGE_CATEGORIES,
    RunRegistry,
    compare_runs,
    compare_scenarios,
    output_hash,
)
from skyvault.scenario_loader import load_scenario
from skyvault.verification import locate_inputs, verify_reproducibility

SCENARIOS = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001"


def scenario(version: str) -> dict:
    return load_scenario(SCENARIOS / f"{version}.json")


@pytest.fixture(scope="module")
def runs():
    return {
        version: SkyVaultTacticalReferenceEngine(scenario(version)).run()
        for version in ("v0.1", "v0.2")
    }


# ── comparing scenario versions ──────────────────────────────────────────────


def test_v0_2_names_exactly_the_change_from_v0_1():
    old, new = scenario("v0.1"), scenario("v0.2")

    changes = compare_scenarios(old, new)

    assert changes == {
        "assumptions_changed": [],
        "data_changed": ["entities[blue_002].capabilities.accuracy: 0.55 -> 0.75"],
        "rules_changed": [],
        "metrics_changed": [],
        "failure_variables_changed": [],
    }
    assert new["version_control"]["changed_from_previous"] == changes
    assert new["version_control"]["parent_version"] == "v0.1"
    assert scenario("v0.1")["version_control"]["parent_version"] is None


def test_reordering_entities_is_not_a_change():
    old = scenario("v0.1")
    new = copy.deepcopy(old)
    new["entities"].reverse()

    assert all(not found for found in compare_scenarios(old, new).values())


def test_each_kind_of_change_lands_in_its_spec_category():
    old = scenario("v0.1")
    new = copy.deepcopy(old)
    new["world_contract"]["assumption_registry"]["movement_model"] = "two_step_grid"
    new["world_contract"]["rule_set"] = {"max_squad": 3}
    new["runtime"]["random_seed"] = 7
    new["evaluation"]["failure_thresholds"] = []
    new["world_contract"]["failure_variables"] = ["sensor_failure"]

    changes = compare_scenarios(old, new)

    assert changes["assumptions_changed"] == [
        "world_contract.assumption_registry.movement_model: "
        "'one_step_grid' -> 'two_step_grid'"
    ]
    assert changes["rules_changed"] == [
        "world_contract.rule_set.max_squad: absent -> 3",
        "runtime.random_seed: 42 -> 7",
    ]
    assert changes["metrics_changed"] == [
        "evaluation.failure_thresholds: ['all_entities_destroyed'] -> []"
    ]
    assert changes["failure_variables_changed"] == [
        "world_contract.failure_variables: ['sensor_failure', "
        "'communication_failure', 'weather_degradation', 'enemy_reaction_speed', "
        "'equipment_overheat', 'civilian_pressure'] -> ['sensor_failure']"
    ]
    assert set(changes) == set(CHANGE_CATEGORIES)


# ── comparing runs ───────────────────────────────────────────────────────────


def test_the_two_versions_lead_to_different_outcomes(runs):
    diff = compare_runs(runs["v0.1"], runs["v0.2"])

    assert diff["same_input"] is False
    assert diff["same_output"] is False
    assert diff["same_rules"] is True
    assert diff["scenario_version"] == {"before": "v0.1", "after": "v0.2"}
    assert diff["outcome"] == {"before": "RED_survived", "after": "BLUE_survived"}
    assert diff["event_count"] == {"before": 97, "after": 91}
    assert diff["status"] == {"before": "risky", "after": "fail"}
    assert diff["score_changes"]["mission_success"] == {"before": 1.0, "after": 0.0}


def test_a_rerun_of_the_same_input_differs_in_nothing(runs):
    again = SkyVaultTacticalReferenceEngine(scenario("v0.1")).run()

    diff = compare_runs(runs["v0.1"], again)

    assert diff["same_input"] and diff["same_output"] and diff["same_rules"]
    assert diff["score_changes"] == {}


# ── the run registry ─────────────────────────────────────────────────────────


def test_the_registry_records_and_finds_runs(tmp_path, runs):
    registry = RunRegistry(tmp_path / "runs" / "registry.jsonl")
    rerun = SkyVaultTacticalReferenceEngine(scenario("v0.1")).run()

    first = registry.record(runs["v0.1"])
    registry.record(runs["v0.2"])
    registry.record(rerun)

    assert len(registry.all()) == 3
    assert registry.get(first["run_id"]) == first
    assert first["outcome"] == "RED_survived"
    same_input = registry.by_input(first["input_hash"])
    assert [entry["run_id"] for entry in same_input] == [
        first["run_id"],
        rerun["reproducibility"]["run_id"],
    ]
    assert {entry["output_hash"] for entry in same_input} == {first["output_hash"]}


def test_an_absent_registry_is_empty_and_an_unknown_run_raises(tmp_path):
    registry = RunRegistry(tmp_path / "missing.jsonl")

    assert registry.all() == []
    with pytest.raises(KeyError, match="Unknown run_id: run_x"):
        registry.get("run_x")


# ── deterministic replay ─────────────────────────────────────────────────────


def test_a_recorded_run_reproduces(runs):
    package = runs["v0.2"]
    found_scenario, found_profile = locate_inputs(package)

    report = verify_reproducibility(package, found_scenario, found_profile)

    assert found_scenario["scenario_version"] == "v0.2"
    assert found_profile["profile_id"] == "balanced"
    assert report["reproduced"] is True
    assert report["input_hash_matches"] is True
    assert report["actual_output_hash"] == package["reproducibility"]["output_hash"]


def test_an_edited_package_does_not_reproduce(runs):
    package = copy.deepcopy(runs["v0.1"])
    package["event_memory"][10]["data"]["damage"] = 999

    report = verify_reproducibility(package, *locate_inputs(package))

    assert report["reproduced"] is False
    assert report["expected_output_hash"] == output_hash(package)
    assert report["expected_output_hash"] != report["recorded_output_hash"]


def test_a_changed_scenario_does_not_reproduce(runs):
    package = runs["v0.1"]
    edited = scenario("v0.1")
    edited["entities"][0]["state"]["hp"] = 99

    report = verify_reproducibility(package, edited)

    assert report["reproduced"] is False
    assert report["input_hash_matches"] is False


def test_a_stochastic_run_is_not_replayed(runs):
    stochastic = scenario("v0.1")
    stochastic["runtime"]["random_seed_policy"] = "stochastic"
    package = SkyVaultTacticalReferenceEngine(stochastic).run()

    report = verify_reproducibility(package, stochastic)

    assert report == {
        "reproduced": False,
        "replay_available": False,
        "input_hash_matches": None,
        "expected_output_hash": output_hash(package),
        "recorded_output_hash": package["reproducibility"]["output_hash"],
        "actual_output_hash": None,
    }


@pytest.mark.parametrize("module", ["hashing.py", "versioning.py", "registry.py"])
def test_reproducibility_never_imports_the_engine(module):
    path = SRC_PATH / "skyvault" / "reproducibility" / module
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)

    assert not names & {"engine", "verification", "tactical_reference_policy"}
