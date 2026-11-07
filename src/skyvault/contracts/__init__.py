"""
Contracts = the formal shapes every piece of SKYVAULT data must keep.

Each contract is a Pydantic model plus one pure validate_<name>() function.
A validator returns the data as plain JSON-safe dicts when it passes and raises
ContractError, listing every violation, when it does not.

Important:
This package imports nothing else from skyvault. Contracts sit below every
other module, so any module may depend on them and they depend on none.
"""

from .action import ActionRecord, validate_action
from .assumption import AssumptionRegistry, validate_assumption_registry
from .base import SCHEMA_VERSION
from .consequence import ConsequenceRecord, validate_consequence
from .entity import EntityRecord, validate_entity
from .errors import ContractError
from .evaluation import EvaluationResult, validate_evaluation_result
from .event import EVENT_TYPES, EventRecord, validate_event
from .json_schema import CONTRACTS, build_json_schemas
from .provenance import DataProvenance, validate_data_provenance
from .reproducibility import ReproducibilityMetadata, validate_reproducibility
from .result_package import ResultPackage, validate_result_package
from .scenario import Scenario, validate_scenario
from .world import WorldContract, validate_world_contract

__all__ = [
    "SCHEMA_VERSION",
    "CONTRACTS",
    "ContractError",
    "EVENT_TYPES",
    "ActionRecord",
    "AssumptionRegistry",
    "ConsequenceRecord",
    "DataProvenance",
    "EntityRecord",
    "EvaluationResult",
    "EventRecord",
    "ReproducibilityMetadata",
    "ResultPackage",
    "Scenario",
    "WorldContract",
    "build_json_schemas",
    "validate_action",
    "validate_assumption_registry",
    "validate_consequence",
    "validate_data_provenance",
    "validate_entity",
    "validate_evaluation_result",
    "validate_event",
    "validate_reproducibility",
    "validate_result_package",
    "validate_scenario",
    "validate_world_contract",
]
