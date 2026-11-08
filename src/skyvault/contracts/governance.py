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

from .base import ContractModel, NonEmptyStr, check

Priority = Literal["low", "normal", "high", "critical"]
StopReason = Literal[
    "budget_exceeded",
    "infinite_loop_detected",
    "no_new_state_change",
    "failure_threshold_reached",
    "max_runtime_exceeded",
    "resource_cap_reached",
    "cancelled",
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
    run_priority: Priority = "normal"
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


class GovernanceRecord(ContractModel):
    """
    What one run used, under which policy, and whether it was stopped.

    Important:
    A run nobody governed records policy_id "ungoverned" and no limits. A
    stopped run is partial: it ended early and its result covers what had
    happened by then. duration_clamped_from is the max_ticks a job asked for
    when the policy cut it to max_scenario_duration.
    """

    policy_id: NonEmptyStr
    run_priority: Priority = "normal"
    limits: dict[str, Any] | None
    usage: Usage
    estimated_cost: dict[str, Any] | None = None
    stopped: bool
    stop_reason: StopReason | None
    partial: bool
    duration_clamped_from: int | None = None


def ungoverned_record(usage: dict[str, Any]) -> dict[str, Any]:
    """The governance record of a run no policy governed (a script run)."""
    return {
        "policy_id": "ungoverned",
        "run_priority": "normal",
        "limits": None,
        "usage": usage,
        "estimated_cost": None,
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
