"""Job = one task the world service received (Formal Spec section 10).

Important:
A request names what to run by name — a scenario as "<scenario_id>/<version>"
under data/scenarios, a batch under data/batches — never by file path, so
an outside system can choose among what SKYVAULT has but never make it read
anything else. The job record follows the request through its lifecycle.
"""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, check
from .governance import GovernanceRecord, Priority
from .provenance import DataProvenance

JobKind = Literal[
    "scenario_run",
    "batch",
    "failure_exploration",
    "replay",
    "persistent_world",
    "branch_compare",
]
Lifecycle = Literal[
    "created",
    "initialized",
    "running",
    "paused",
    "completed",
    "failed",
    "archived",
    "replayed",
    "deleted",
]
NAME = r"^[A-Za-z0-9_.+-]+(/[A-Za-z0-9_.+-]+)?$"


class EntityChange(ContractModel):
    """
    What a request changes on one unit; capabilities and state are merged.
    position moves it (Phase 15: AEROGRID repositions a sensor); the
    scenario contract still checks it is inside the space.
    """

    name: NonEmptyStr | None = None
    position: list[int] | str | None = None
    entity_type: NonEmptyStr | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class JobRequest(ContractModel):
    """
    What a system asks the service to do (task_intake).

    Important:
    runtime overrides the scenario's runtime block (max_ticks, random_seed,
    policy, participants); replay names the job whose run to replay;
    branches are a branch_compare's named action sets (Phase 12), each
    {branch_id, actions, entity_changes}. entity_changes replaces named
    units' capabilities, state, name or type ({entity_id: {field: ...}});
    data_provenance records where those changes came from (Phase 12: what
    EIDEN-01 and STAR GUARD submit).
    """

    kind: JobKind
    source_system: NonEmptyStr = "user"
    priority: Priority | None = None
    required_result_package: bool = True
    scenario: str | None = Field(default=None, pattern=NAME)
    batch: str | None = Field(default=None, pattern=NAME)
    profile: str | None = Field(default=None, pattern=NAME)
    runtime: dict[str, Any] = Field(default_factory=dict)
    repeat_count: int | None = Field(default=None, ge=1)
    replay: NonEmptyStr | None = None
    branches: list[dict[str, Any]] | None = None
    entity_changes: dict[str, EntityChange] | None = None
    data_provenance: DataProvenance | None = None

    @model_validator(mode="after")
    def _names_what_it_needs(self) -> "JobRequest":
        needs = {
            "scenario_run": "scenario",
            "failure_exploration": "scenario",
            "persistent_world": "scenario",
            "batch": "batch",
            "replay": "replay",
            "branch_compare": "branches",
        }[self.kind]
        if self.kind == "branch_compare" and self.scenario is None:
            raise ValueError("a branch_compare job needs scenario")
        if getattr(self, needs) is None:
            raise ValueError(f"a {self.kind} job needs {needs}")
        return self


class WorldInstance(ContractModel):
    world_id: NonEmptyStr
    scenario_id: NonEmptyStr
    lifecycle_state: Lifecycle


class Job(ContractModel):
    """A job as the service keeps it."""

    job_id: NonEmptyStr
    request: JobRequest
    priority: Priority
    lifecycle_state: Lifecycle
    world_instance: WorldInstance | None = None
    governance: GovernanceRecord | None = None
    estimated_cost: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: NonEmptyStr
    updated_at: NonEmptyStr


def validate_job_request(data: dict[str, Any]) -> dict[str, Any]:
    """A job request, or ContractError listing every violation."""
    return check(JobRequest, "job_request", data)


def validate_job(data: dict[str, Any]) -> dict[str, Any]:
    """A job record, or ContractError listing every violation."""
    return check(Job, "job", data)
