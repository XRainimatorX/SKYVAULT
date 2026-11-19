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
)
from skyvault.scenario_loader import load_scenario, read_scenario

REFERENCE_SCENARIO = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "reference"
    / "scenarios"
    / "tactical_reference_001"
    / "v0.1.json"
)


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def error_fields(caught: pytest.ExceptionInfo) -> set[str]:
    return {error.split(":")[0] for error in caught.value.errors}


# Formal Spec section 3.3: the groups every scenario is written in
SECTION_3_3 = {
    "identity": [
        "scenario_id",
        "scenario_type",
        "domain",
        "purpose",
        "scenario_version",
    ],
    "world_binding": ["world_contract_id", "environment_profile", "rule_profile"],
    "initial_conditions": [
        "entities",
        "resources",
        "risks",
        "constraints",
        "uncertainty",
    ],
    "assumption_registry": [
        "assumptions",
        "critical_assumptions",
        "assumption_confidence",
    ],
    "data_provenance": [
        "sources",
        "timestamps",
        "confidence",
        "modified_by",
        "input_version",
    ],
    "participants": [
        "human_decision_slots",
        "ai_agent_slots",
        "system_slots",
        "equipment_profiles",
    ],
    "allowed_actions": ["action_types", "actor_permissions"],
    "execution_settings": [
        "time_mode",
        "duration_limit",
        "repeat_count",
        "random_seed_policy",
        "deterministic_mode",
    ],
    "failure_exploration": [
        "enabled",
        "failure_variables",
        "stress_levels",
        "branch_comparison",
    ],
    "evaluation": [
        "primary_metrics",
        "secondary_metrics",
        "anti_gaming_metrics",
        "failure_thresholds",
        "comparison_targets",
    ],
    "output": [
        "required_logs",
        "required_reports",
        "replay_required",
        "failure_map_required",
    ],
}


def model_fields(model, path):
    for part in path:
        model = model.model_fields[part].annotation
        for candidate in get_args(model) or (model,):
            if hasattr(candidate, "model_fields"):
                model = candidate
                break
    return set(model.model_fields)


# ── section 3.3, field by field ──────────────────────────────────────────────


@pytest.mark.parametrize("group", list(SECTION_3_3))
def test_every_section_3_3_field_is_in_the_scenario_contract(group):
    assert group in Scenario.model_fields
    assert set(SECTION_3_3[group]) <= model_fields(Scenario, [group])


@pytest.mark.parametrize("group", list(SECTION_3_3))
def test_a_scenario_without_any_section_3_3_group_is_rejected(group):
    scenario = fixture("scenario_valid")
    del scenario[group]

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert group in error_fields(caught)


def test_the_old_flat_layout_is_rejected():
    flat = {
        "schema_version": "0.6",
        "scenario_id": "old",
        "scenario_version": "v0.1",
        "world_contract": {},
        "entities": [],
        "runtime": {"max_ticks": 1, "random_seed": 1},
        "evaluation": {"primary_metrics": []},
    }

    with pytest.raises(ContractError) as caught:
        validate_scenario(flat)

    assert {"identity", "world_binding", "runtime"} <= error_fields(caught)


# ── acceptance criterion 1: a scenario without scenario_id is rejected ──────


def test_loading_a_scenario_without_scenario_id_is_rejected():
    with pytest.raises(ContractError) as caught:
        load_scenario(FIXTURES / "scenario_missing_scenario_id.json")

    assert caught.value.contract == "scenario"
    assert "identity.scenario_id" in error_fields(caught)


def test_contract_error_is_still_a_value_error():
    with pytest.raises(ValueError):
        load_scenario(FIXTURES / "scenario_missing_scenario_id.json")


def test_the_reference_scenario_reads_unchanged_and_compiles():
    raw = json.loads(REFERENCE_SCENARIO.read_text(encoding="utf-8"))

    assert read_scenario(REFERENCE_SCENARIO) == raw
    compiled = load_scenario(REFERENCE_SCENARIO)
    assert compiled["scenario_id"] == raw["identity"]["scenario_id"]
    assert compiled["world_contract"]["world_id"] == (
        raw["world_binding"]["world_contract_id"]
    )


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
    del scenario["identity"]["schema_version"]

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "identity.schema_version" in error_fields(caught)


@pytest.mark.parametrize("version", ["0.6", "9.9"])
def test_scenario_for_another_schema_version_is_rejected(version):
    scenario = fixture("scenario_valid")
    scenario["identity"]["schema_version"] = version

    with pytest.raises(ContractError):
        validate_scenario(scenario)


def test_scenario_contract_follows_the_package_schema_version():
    from skyvault.contracts.scenario import Identity

    annotation = Identity.model_fields["schema_version"].annotation

    assert get_args(annotation) == (SCHEMA_VERSION,)


# ── grammar rules ────────────────────────────────────────────────────────────


def test_duplicate_entity_ids_are_rejected():
    scenario = fixture("scenario_valid")
    entities = scenario["initial_conditions"]["entities"]
    entities[1]["entity_id"] = entities[0]["entity_id"]

    with pytest.raises(ContractError, match="duplicate entity_id"):
        validate_scenario(scenario)


def test_scenario_needs_at_least_one_entity():
    scenario = fixture("scenario_valid")
    scenario["initial_conditions"]["entities"] = []

    with pytest.raises(ContractError):
        validate_scenario(scenario)


def test_misspelt_key_is_rejected_instead_of_ignored():
    scenario = fixture("scenario_valid")
    settings = scenario["execution_settings"]
    settings["random_sead"] = settings.pop("random_seed")

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "execution_settings.random_sead" in error_fields(caught)


def test_a_seeded_run_must_name_its_seed():
    scenario = fixture("scenario_valid")
    scenario["execution_settings"]["random_seed"] = None

    with pytest.raises(ContractError, match="needs random_seed"):
        validate_scenario(scenario)


@pytest.mark.parametrize(
    "slots, expected",
    [
        ({"ai_agent_slots": [{"slot_id": "a"}]}, "neither a policy nor orders"),
        (
            {"human_decision_slots": [{"slot_id": "h", "policy": {"name": "p"}}]},
            "decides by orders",
        ),
        (
            {
                "ai_agent_slots": [
                    {"slot_id": "a", "policy": {"name": "p"}},
                    {"slot_id": "b", "policy": {"name": "q"}},
                ]
            },
            "only one slot may decide by default",
        ),
        (
            {
                "ai_agent_slots": [{"slot_id": "a", "policy": {"name": "p"}}],
                "system_slots": [
                    {
                        "slot_id": "a",
                        "policy": {"name": "q"},
                        "controls": {"factions": ["RED"]},
                    }
                ],
            },
            "slot_id must be unique",
        ),
    ],
)
def test_participant_slots_must_make_sense(slots, expected):
    scenario = fixture("scenario_valid")
    scenario["participants"].update(slots)

    with pytest.raises(ContractError, match=expected):
        validate_scenario(scenario)


def test_an_enabled_failure_exploration_names_variables_and_levels():
    scenario = fixture("scenario_valid")
    scenario["failure_exploration"] = {
        "enabled": True,
        "failure_variables": ["supply_delay"],
    }

    with pytest.raises(ContractError, match="names stress_levels"):
        validate_scenario(scenario)


def test_version_control_must_belong_to_this_scenario():
    scenario = fixture("scenario_valid")
    scenario["scenario_version_control"] = {
        "scenario_id": "another",
        "version": scenario["identity"]["scenario_version"],
        "parent_version": None,
        "changed_from_previous": {},
        "change_reason": "",
    }

    with pytest.raises(ContractError, match="another scenario"):
        validate_scenario(scenario)


def test_scenario_with_filled_spec_blocks_passes():
    scenario = fixture("scenario_valid")
    scenario["data_provenance"] = {
        "sources": [
            {"source_id": "s1", "source_type": "manual_input", "confidence": 0.9}
        ],
        "timestamps": {"s1": "2026-11-19"},
        "confidence": {"s1": 0.9},
        "modified_by": "operator",
        "input_version": "v1",
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
        "assumption_confidence": {"a1": 0.6},
    }

    assert validate_scenario(scenario) == scenario


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
