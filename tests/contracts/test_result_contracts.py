import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SCHEMA_DIR = SRC_PATH / "skyvault" / "schemas"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import (
    CONTRACTS,
    SCHEMA_VERSION,
    ContractError,
    build_json_schemas,
    validate_evaluation_result,
    validate_reproducibility,
    validate_result_package,
)
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

PLAN_CONTRACTS = {
    "world_contract",
    "scenario",
    "entity",
    "action",
    "consequence",
    "event",
    "evaluation_result",
    "result_package",
    "assumption_registry",
    "data_provenance",
    "reproducibility",
}


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def run_reference_scenario() -> dict:
    return SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO)).run()


def reproducibility_record() -> dict:
    return {
        "run_id": "run_001",
        "scenario_id": "tactical_reference_001",
        "scenario_version": "v0.1",
        "random_seed_policy": "fixed",
        "random_seed": 42,
        "runtime_version": "0.1.0",
        "ruleset_version": "tactical_reference_v0.1",
        "input_hash": "sha256:in",
        "output_hash": "sha256:out",
        "deterministic_replay_available": True,
        "run_metadata": {"started_at": "t0", "ended_at": "t1"},
    }


# ── acceptance criterion 4: a result package must contain evaluation_result ─


def test_result_package_without_evaluation_result_is_rejected():
    with pytest.raises(ContractError) as caught:
        validate_result_package(fixture("result_package_missing_evaluation_result"))

    assert caught.value.contract == "result_package"
    assert any(error.startswith("evaluation_result:") for error in caught.value.errors)


def test_result_package_with_the_old_evaluation_key_is_rejected():
    package = fixture("result_package_valid")
    package["evaluation"] = package.pop("evaluation_result")

    with pytest.raises(ContractError):
        validate_result_package(package)


def test_valid_result_package_passes_and_keeps_its_shape():
    package = fixture("result_package_valid")

    assert validate_result_package(package) == package


def test_engine_result_package_satisfies_the_contract():
    package = run_reference_scenario()

    assert "evaluation_result" in package
    assert "evaluation" not in package
    assert package["evaluation_result"]["winner_or_result"] == "RED_survived"
    assert validate_result_package(copy.deepcopy(package)) == package


def test_event_count_must_match_event_memory():
    package = fixture("result_package_valid")
    package["evaluation_result"]["event_count"] = 99

    with pytest.raises(ContractError, match="event_memory holds 1 events"):
        validate_result_package(package)


def test_result_package_rejects_a_malformed_event():
    package = fixture("result_package_valid")
    del package["event_memory"][0]["before_state"]

    with pytest.raises(ContractError) as caught:
        validate_result_package(package)

    assert "event_memory.0.before_state" in {
        error.split(":")[0] for error in caught.value.errors
    }


# ── evaluation result ────────────────────────────────────────────────────────


def test_evaluation_result_accepts_the_phase_7_fields():
    evaluation = fixture("result_package_valid")["evaluation_result"]
    evaluation["overall_judgement"] = {"status": "risky", "confidence": 0.4}
    evaluation["scores"] = {"tactical_usefulness": 0.7}

    assert validate_evaluation_result(evaluation) == evaluation


def test_evaluation_result_rejects_an_unknown_judgement():
    evaluation = fixture("result_package_valid")["evaluation_result"]
    evaluation["overall_judgement"] = {"status": "maybe", "confidence": 0.4}

    with pytest.raises(ContractError):
        validate_evaluation_result(evaluation)


# ── reproducibility ──────────────────────────────────────────────────────────


def test_complete_reproducibility_record_passes():
    record = reproducibility_record()

    assert validate_reproducibility(record) == record


def test_reproducibility_needs_both_hashes():
    record = reproducibility_record()
    del record["input_hash"]
    del record["output_hash"]

    with pytest.raises(ContractError) as caught:
        validate_reproducibility(record)

    fields = {error.split(":")[0] for error in caught.value.errors}
    assert fields == {"input_hash", "output_hash"}


def test_reproducibility_rejects_an_unknown_seed_policy():
    record = reproducibility_record()
    record["random_seed_policy"] = "whatever"

    with pytest.raises(ContractError):
        validate_reproducibility(record)


def test_result_package_accepts_reproducibility_once_phase_8_fills_it():
    package = fixture("result_package_valid")
    package["reproducibility"] = reproducibility_record()

    assert validate_result_package(package) == package


# ── JSON Schema ──────────────────────────────────────────────────────────────


# Phase 7 adds the evaluation profile to the eleven plan contracts
EXPORTED_CONTRACTS = PLAN_CONTRACTS | {"evaluation_profile"}


def test_the_eleven_plan_contracts_and_the_profile_are_exported():
    assert set(CONTRACTS) == EXPORTED_CONTRACTS
    assert set(build_json_schemas()) == EXPORTED_CONTRACTS


def test_committed_schema_files_match_the_contracts():
    committed = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}

    assert committed == {f"{name}.schema.json" for name in EXPORTED_CONTRACTS}

    for name, schema in build_json_schemas().items():
        with (SCHEMA_DIR / f"{name}.schema.json").open(encoding="utf-8") as file:
            on_disk = json.load(file)

        assert (
            on_disk == schema
        ), f"{name}.schema.json is stale: run python3 scripts/export_schemas.py"


def test_schemas_encode_the_acceptance_criteria():
    schemas = build_json_schemas()

    assert "scenario_id" in schemas["scenario"]["required"]
    assert "actor_id" in schemas["action"]["required"]
    assert {"before_state", "after_state"} <= set(schemas["event"]["required"])
    assert "evaluation_result" in schemas["result_package"]["required"]


def test_every_schema_declares_its_dialect_and_version():
    for name, schema in build_json_schemas().items():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"skyvault/{SCHEMA_VERSION}/{name}.schema.json"
