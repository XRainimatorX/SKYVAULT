import json
import sys
from pathlib import Path
from typing import get_args

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import (
    SCHEMA_VERSION,
    ContractError,
    Scenario,
    validate_assumption_registry,
    validate_data_provenance,
    validate_scenario,
    validate_world_contract,
)
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def error_fields(caught: pytest.ExceptionInfo) -> set[str]:
    return {error.split(":")[0] for error in caught.value.errors}


# ── acceptance criterion 1: a scenario without scenario_id is rejected ──────


def test_loading_a_scenario_without_scenario_id_is_rejected():
    with pytest.raises(ContractError) as caught:
        load_scenario(FIXTURES / "scenario_missing_scenario_id.json")

    assert caught.value.contract == "scenario"
    assert "scenario_id" in error_fields(caught)


def test_contract_error_is_still_a_value_error():
    with pytest.raises(ValueError):
        load_scenario(FIXTURES / "scenario_missing_scenario_id.json")


def test_reference_scenario_loads_unchanged():
    with REFERENCE_SCENARIO.open(encoding="utf-8") as file:
        raw = json.load(file)

    assert load_scenario(REFERENCE_SCENARIO) == raw


def test_valid_fixture_passes_and_keeps_its_shape():
    scenario = fixture("scenario_valid")

    assert validate_scenario(scenario) == scenario


# ── formats ──────────────────────────────────────────────────────────────────


def test_yaml_scenario_loads_the_same_as_json(tmp_path):
    scenario = fixture("scenario_valid")
    yaml_path = tmp_path / "scenario.yaml"
    yaml_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")

    assert load_scenario(yaml_path) == load_scenario(FIXTURES / "scenario_valid.json")


def test_yml_suffix_is_accepted(tmp_path):
    yml_path = tmp_path / "scenario.yml"
    yml_path.write_text(yaml.safe_dump(fixture("scenario_valid")), encoding="utf-8")

    assert load_scenario(yml_path)["scenario_id"] == "fixture_minimal_001"


def test_unsupported_suffix_is_rejected(tmp_path):
    path = tmp_path / "scenario.toml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported scenario format"):
        load_scenario(path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scenario(tmp_path / "absent.json")


# ── schema versioning ────────────────────────────────────────────────────────


def test_scenario_without_schema_version_is_rejected():
    scenario = fixture("scenario_valid")
    del scenario["schema_version"]

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "schema_version" in error_fields(caught)


def test_scenario_for_another_schema_version_is_rejected():
    scenario = fixture("scenario_valid")
    scenario["schema_version"] = "9.9"

    with pytest.raises(ContractError):
        validate_scenario(scenario)


def test_scenario_contract_follows_the_package_schema_version():
    annotation = Scenario.model_fields["schema_version"].annotation

    assert get_args(annotation) == (SCHEMA_VERSION,)


# ── grammar rules ────────────────────────────────────────────────────────────


def test_duplicate_entity_ids_are_rejected():
    scenario = fixture("scenario_valid")
    scenario["entities"][1]["entity_id"] = scenario["entities"][0]["entity_id"]

    with pytest.raises(ContractError, match="duplicate entity_id"):
        validate_scenario(scenario)


def test_scenario_needs_at_least_one_entity():
    scenario = fixture("scenario_valid")
    scenario["entities"] = []

    with pytest.raises(ContractError):
        validate_scenario(scenario)


def test_misspelt_key_is_rejected_instead_of_ignored():
    scenario = fixture("scenario_valid")
    scenario["runtime"]["random_sead"] = scenario["runtime"].pop("random_seed")

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert error_fields(caught) == {"runtime.random_seed", "runtime.random_sead"}


def test_scenario_with_optional_spec_blocks_passes():
    scenario = fixture("scenario_valid")
    scenario["data_provenance"] = {
        "sources": [
            {"source_id": "s1", "source_type": "manual_input", "confidence": 0.9}
        ]
    }
    scenario["assumption_registry"] = {
        "assumptions": [
            {
                "assumption_id": "a1",
                "description": "enemy holds position",
                "category": "enemy_behavior",
                "value": "static",
                "confidence": 0.6,
                "criticality": "high",
            }
        ],
        "critical_assumptions": ["a1"],
    }

    assert validate_scenario(scenario) == scenario


# ── world contract ───────────────────────────────────────────────────────────


def test_reference_world_contract_passes():
    world_contract = load_scenario(REFERENCE_SCENARIO)["world_contract"]

    assert validate_world_contract(world_contract) == world_contract


def test_grid_without_bounds_is_rejected():
    world_contract = fixture("scenario_valid")["world_contract"]
    del world_contract["space_model"]["width"]

    with pytest.raises(ContractError, match="width and height"):
        validate_world_contract(world_contract)


def test_unknown_distance_model_is_rejected():
    world_contract = fixture("scenario_valid")["world_contract"]
    world_contract["space_model"]["distance_model"] = "taxicab"

    with pytest.raises(ContractError):
        validate_world_contract(world_contract)


def test_world_contract_requires_its_core_elements():
    with pytest.raises(ContractError) as caught:
        validate_world_contract({"world_id": "w"})

    assert error_fields(caught) == {
        "world_scope",
        "purpose",
        "space_model",
        "time_model",
        "assumption_registry",
        "evaluation_targets",
    }


# ── assumption registry and data provenance ──────────────────────────────────


def test_assumption_criticality_must_be_low_medium_or_high():
    registry = {
        "assumptions": [
            {
                "assumption_id": "a1",
                "description": "",
                "category": "supply",
                "value": 3,
                "confidence": 0.5,
                "criticality": "extreme",
            }
        ]
    }

    with pytest.raises(ContractError):
        validate_assumption_registry(registry)


def test_assumption_confidence_must_be_a_probability():
    registry = {
        "assumptions": [
            {
                "assumption_id": "a1",
                "description": "",
                "category": "supply",
                "value": 3,
                "confidence": 1.5,
                "criticality": "low",
            }
        ]
    }

    with pytest.raises(ContractError):
        validate_assumption_registry(registry)


def test_provenance_source_needs_an_id_and_a_known_type():
    with pytest.raises(ContractError) as caught:
        validate_data_provenance(
            {"sources": [{"source_type": "rumour", "confidence": 0.5}]}
        )

    assert error_fields(caught) == {"sources.0.source_id", "sources.0.source_type"}


def test_empty_provenance_is_valid():
    assert validate_data_provenance({}) == {}
