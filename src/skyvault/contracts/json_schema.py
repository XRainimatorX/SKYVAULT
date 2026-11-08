"""JSON Schema export = the contracts in a form other systems read without Python."""

from typing import Any

from .action import ActionRecord
from .assumption import AssumptionRegistry
from .base import SCHEMA_VERSION, ContractModel
from .batch import BatchResult, BatchSpec, ConflictPackage
from .consequence import ConsequenceRecord
from .entity import EntityRecord
from .evaluation import EvaluationResult
from .evaluation_profile import EvaluationProfile
from .event import EventRecord
from .failure import FailureMap
from .provenance import DataProvenance
from .reproducibility import ReproducibilityMetadata
from .result_package import ResultPackage
from .scenario import Scenario
from .world import WorldContract

# The eleven contracts of the development plan's Phase 1, plus the evaluation
# profile Phase 7 adds, the failure map Phase 9 adds and the three batch contracts
# Phase 10 adds, by their file names.
CONTRACTS: dict[str, type[ContractModel]] = {
    "world_contract": WorldContract,
    "scenario": Scenario,
    "entity": EntityRecord,
    "action": ActionRecord,
    "consequence": ConsequenceRecord,
    "event": EventRecord,
    "evaluation_result": EvaluationResult,
    "result_package": ResultPackage,
    "assumption_registry": AssumptionRegistry,
    "data_provenance": DataProvenance,
    "reproducibility": ReproducibilityMetadata,
    "evaluation_profile": EvaluationProfile,
    "failure_map": FailureMap,
    "batch_spec": BatchSpec,
    "batch_result": BatchResult,
    "conflict_package": ConflictPackage,
}


def build_json_schemas() -> dict[str, dict[str, Any]]:
    """
    Every contract as a JSON Schema document, keyed by contract name.

    Important:
    This only builds the schemas. Writing them to src/skyvault/schemas/ is the
    job of scripts/export_schemas.py, and a test checks the committed files
    still match what this returns.
    """
    return {
        name: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"skyvault/{SCHEMA_VERSION}/{name}.schema.json",
            **model.model_json_schema(),
        }
        for name, model in CONTRACTS.items()
    }
