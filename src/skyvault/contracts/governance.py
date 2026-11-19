"""Resource & Compute Governance = how much a run may spend, and what it spent.

Important:
Formal Spec section 15: a background world service cannot burn compute
without limit. The policy says how much a run, a batch, a queue and a
persistent world may use and when a run is stopped on its own. Every run
records what it used under which policy (development plan Phase 11:
"每個 run 必須有 resource_compute_governance metadata").
"""

from typing import Any, Literal

from pydantic import Field

from .base import Authority, ContractModel, NonEmptyStr, check

# Formal Spec 15.3 priority levels
Priority = Literal["low", "medium", "high", "urgent"]
StopReason = Literal[
    "budget_exceeded",
    "infinite_loop_detected",
    "no_new_state_change",
    "failure_threshold_reached",
    "max_runtime_exceeded",
    "resource_cap_reached",
    "cancelled",
    "terminated",
]
STOP_REASONS = StopReason.__args__  # type: ignore[attr-defined]
PRIORITIES = Priority.__args__  # type: ignore[attr-defined]


class ComputeBudget(ContractModel):
    max_decisions: int | None = Field(default=None, ge=1)
    max_events: int | None = Field(default=None, ge=1)


class PersistentWorldCap(ContractModel):
    max_ticks: int | None = Field(default=None, ge=1)
    max_events: int | None = Field(default=None, ge=1)
    max_checkpoints: int | None = Field(default=None, ge=1)


class AutoStop(ContractModel):
    """
    When a run stops on its own. no_new_state_change_ticks: that many ticks in
    a row with units and resources unchanged. infinite_loop_repeats: the same
    state reached that many times, not in a row. failure_loss_ratio: the
    judged side has lost at least that share of its units. null switches a
    condition off.
    """

    no_new_state_change_ticks: int | None = Field(default=10, ge=1)
    infinite_loop_repeats: int | None = Field(default=3, ge=2)
    failure_loss_ratio: float | None = Field(default=None, gt=0.0, le=1.0)


class ResourceComputeGovernance(ContractModel):
    """A governance policy (data/service/)."""

    policy_id: NonEmptyStr
    description: str = ""
    run_priority: Priority = "medium"
    compute_budget: ComputeBudget = Field(default_factory=ComputeBudget)
    max_scenario_duration: int | None = Field(default=None, ge=1)
    max_runtime_seconds: float | None = Field(default=None, gt=0.0)
    max_parallel_runs: int = Field(default=1, ge=1)
    max_batch_count: int | None = Field(default=None, ge=1)
    max_queue_length: int | None = Field(default=None, ge=1)
    queue_policy: Literal["priority_then_fifo", "fifo"] = "priority_then_fifo"
    persistent_world_resource_cap: PersistentWorldCap = Field(
        default_factory=PersistentWorldCap
    )
    auto_stop: AutoStop = Field(default_factory=AutoStop)
    partial_result_export: bool = True
    # who decides a handoff (Phase 19: an edition names its own); unset means
    # the interface's default authorities
    decision_authorities: list[Authority] | None = Field(default=None, min_length=1)


class Usage(ContractModel):
    """
    What was used. A batch or an exploration counts runs and events; ticks
    and decisions are counted for single runs only (null otherwise).
    """

    runs: int = Field(default=1, ge=1)
    ticks: int | None = Field(ge=0)
    decisions: int | None = Field(ge=0)
    events: int = Field(ge=0)
    runtime_seconds: float = Field(ge=0.0)


class RecordBudget(ContractModel):
    """Formal Spec 15.3 compute_budget, as one run was held to it."""

    max_runtime: float | None
    max_parallel_runs: int | None
    max_batch_count: int | None
    estimated_cost: dict[str, Any] | None
    max_decisions: int | None = None
    max_events: int | None = None
    max_scenario_duration: int | None = None


class RecordPriority(ContractModel):
    """Formal Spec 15.3 priority: the level and why."""

    level: Priority
    reason: str


class RecordQueuePolicy(ContractModel):
    """Formal Spec 15.3 queue_policy."""

    allow_defer: bool
    allow_partial_result: bool
    order: Literal["priority_then_fifo", "fifo"] | None = None


class GovernanceRecord(ContractModel):
    """
    resource_compute_governance = Formal Spec section 15.3, as one run used it.

    Important:
    scenario_id, compute_budget, priority, auto_stop_conditions and
    queue_policy are the section's own. policy_id, usage, stopped,
    stop_reason, partial and duration_clamped_from record what happened: a
    run nobody governed records policy_id "ungoverned" and nothing to hold
    it; a stopped run is partial (its result covers what had happened by
    then); duration_clamped_from is the max_ticks a job asked for when the
    policy cut it to max_scenario_duration.
    """

    scenario_id: NonEmptyStr
    compute_budget: RecordBudget
    priority: RecordPriority
    auto_stop_conditions: list[StopReason]
    queue_policy: RecordQueuePolicy
    policy_id: NonEmptyStr
    usage: Usage
    stopped: bool
    stop_reason: StopReason | None
    partial: bool
    duration_clamped_from: int | None = None


def ungoverned_record(usage: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    """The governance record of a run no policy governed (a script run)."""
    return {
        "scenario_id": scenario_id,
        "compute_budget": {
            "max_runtime": None,
            "max_parallel_runs": None,
            "max_batch_count": None,
            "estimated_cost": None,
        },
        "priority": {"level": "medium", "reason": "no policy governed this run"},
        "auto_stop_conditions": [],
        "queue_policy": {"allow_defer": False, "allow_partial_result": False},
        "policy_id": "ungoverned",
        "usage": usage,
        "stopped": False,
        "stop_reason": None,
        "partial": False,
        "duration_clamped_from": None,
    }


def validate_governance(data: dict[str, Any]) -> dict[str, Any]:
    """A governance policy, or ContractError listing every violation."""
    return check(ResourceComputeGovernance, "resource_compute_governance", data)


def validate_governance_record(data: dict[str, Any]) -> dict[str, Any]:
    """One run's governance record, or ContractError."""
    return check(GovernanceRecord, "governance_record", data)
