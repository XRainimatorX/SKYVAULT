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
from .batch import (
    BatchResult,
    BatchSpec,
    ConflictPackage,
    validate_batch_result,
    validate_batch_spec,
    validate_conflict_package,
)
from .consequence import ConsequenceRecord, validate_consequence
from .entity import EntityRecord, validate_entity
from .errors import ContractError
from .evaluation import EvaluationResult, validate_evaluation_result
from .evaluation_profile import (
    ANTI_GAMING_BEHAVIORS,
    METRIC_NAMES,
    EvaluationProfile,
    validate_evaluation_profile,
)
from .event import EVENT_TYPES, EventRecord, validate_event
from .external import (
    SYSTEMS,
    TRIGGERS,
    AuthorityHandoff,
    ExternalSubmission,
    validate_authority_handoff,
    validate_external_submission,
)
from .failure import (
    FAILURE_VARIABLE_NAMES,
    FailureExplorationSpec,
    FailureMap,
    validate_failure_exploration,
    validate_failure_map,
)
from .governance import (
    PRIORITIES,
    STOP_REASONS,
    GovernanceRecord,
    ResourceComputeGovernance,
    ungoverned_record,
    validate_governance,
    validate_governance_record,
)
from .job import Job, JobRequest, validate_job, validate_job_request
from .json_schema import CONTRACTS, build_json_schemas
from .observation import (
    VIEWS,
    Observation,
    ObserverProfile,
    validate_observation,
    validate_observer_profile,
)
from .order import Order, validate_order
from .provenance import DataProvenance, validate_data_provenance
from .reproducibility import ReproducibilityMetadata, validate_reproducibility
from .result_package import ResultPackage, validate_result_package
from .scenario import Scenario, validate_scenario
from .world import WorldContract, validate_world_contract

__all__ = [
    "SCHEMA_VERSION",
    "ANTI_GAMING_BEHAVIORS",
    "CONTRACTS",
    "METRIC_NAMES",
    "PRIORITIES",
    "STOP_REASONS",
    "SYSTEMS",
    "TRIGGERS",
    "VIEWS",
    "ContractError",
    "EVENT_TYPES",
    "FAILURE_VARIABLE_NAMES",
    "ActionRecord",
    "AuthorityHandoff",
    "AssumptionRegistry",
    "BatchResult",
    "BatchSpec",
    "ConflictPackage",
    "ConsequenceRecord",
    "DataProvenance",
    "EntityRecord",
    "EvaluationProfile",
    "EvaluationResult",
    "ExternalSubmission",
    "EventRecord",
    "FailureExplorationSpec",
    "FailureMap",
    "GovernanceRecord",
    "Job",
    "JobRequest",
    "Observation",
    "ObserverProfile",
    "Order",
    "ReproducibilityMetadata",
    "ResourceComputeGovernance",
    "ResultPackage",
    "Scenario",
    "WorldContract",
    "build_json_schemas",
    "ungoverned_record",
    "validate_action",
    "validate_assumption_registry",
    "validate_authority_handoff",
    "validate_batch_result",
    "validate_batch_spec",
    "validate_conflict_package",
    "validate_consequence",
    "validate_data_provenance",
    "validate_entity",
    "validate_evaluation_profile",
    "validate_evaluation_result",
    "validate_event",
    "validate_external_submission",
    "validate_failure_exploration",
    "validate_failure_map",
    "validate_governance",
    "validate_governance_record",
    "validate_job",
    "validate_job_request",
    "validate_observation",
    "validate_observer_profile",
    "validate_order",
    "validate_reproducibility",
    "validate_result_package",
    "validate_scenario",
    "validate_world_contract",
]
