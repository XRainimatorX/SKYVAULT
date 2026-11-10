"""JSON Schema export = the contracts in a form other systems read without Python."""

from typing import Any

from .action import ActionRecord
from .assumption import AssumptionRegistry
from .base import SCHEMA_VERSION, ContractModel
from .batch import BatchResult, BatchSpec, ConflictPackage
from .consequence import ConsequenceRecord
from .edition import Edition
from .entity import EntityRecord
from .equipment import EquipmentProfile, EquipmentTestResult
from .evaluation import EvaluationResult
from .evaluation_profile import EvaluationProfile
from .event import EventRecord
from .external import AuthorityHandoff, ExternalSubmission
from .failure import FailureMap
from .governance import ResourceComputeGovernance
from .job import Job
from .observation import Observation, ObserverProfile
from .order import Order
from .provenance import DataProvenance
from .reproducibility import ReproducibilityMetadata
from .result_package import ResultPackage
from .scenario import Scenario
from .world import WorldContract

# The eleven contracts of the development plan's Phase 1, plus the evaluation
# profile Phase 7 adds, the failure map Phase 9 adds and the three batch contracts
# Phase 10 adds, the observer profile and observation Phase 5 adds, the order
# Phase 6 adds, the governance policy and job Phase 11 adds and the external
# submission and authority handoff Phase 12 adds and the equipment profile and
# test result Phase 16 adds and the edition Phase 19 adds, by file name.
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
    "observer_profile": ObserverProfile,
    "observation": Observation,
    "order": Order,
    "resource_compute_governance": ResourceComputeGovernance,
    "job": Job,
    "external_submission": ExternalSubmission,
    "authority_handoff": AuthorityHandoff,
    "equipment_profile": EquipmentProfile,
    "equipment_test_result": EquipmentTestResult,
    "edition": Edition,
}


def build_json_schemas() -> dict[str, dict[str, Any]]:
    """
    Every contract as a JSON Schema document, keyed by contract name.

    Important:
    This only builds the schemas. Writing them to src/skyvault/schemas/ is the
    job of scripts/dev/export_schemas.py, and a test checks the committed files
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
