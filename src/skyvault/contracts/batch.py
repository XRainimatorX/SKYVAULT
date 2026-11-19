"""Batch contracts = how a batch is asked for, and what it and its branches report."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check
from .scenario import ScheduledAction


class Proposal(ScheduledAction):
    """An order an outside system proposes; conflicting proposals become branches."""

    proposal_id: NonEmptyStr


class ConflictRequest(ContractModel):
    proposals: list[Proposal] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ConflictRequest":
        ids = [proposal.proposal_id for proposal in self.proposals]
        if len(set(ids)) != len(ids):
            raise ValueError("proposal_id must be unique")
        return self


class VersionVariant(ContractModel):
    variant_id: NonEmptyStr
    scenario_version: NonEmptyStr


class Sweep(ContractModel):
    parameter: NonEmptyStr
    values: list[Any] = Field(min_length=1)


class BatchRunPolicy(ContractModel):
    repeat_count: int = Field(ge=1)
    random_seed_policy: Literal["fixed", "controlled_random"]


class BatchSpec(ContractModel):
    """
    A batch request (development plan Phase 10).

    Important:
    Every variant is a version of scenario_id: listed versions, sweep points
    of base_version, and, when conflicts are given, one branch per compatible
    set of proposals plus a baseline with none. profile names a file in
    data/evaluation_profiles; perspective null means the profile's or the
    scenario's. workers above 1 runs in parallel with the same results.
    """

    batch_id: NonEmptyStr
    description: str = ""
    scenario_id: NonEmptyStr
    base_version: NonEmptyStr
    profile: NonEmptyStr
    perspective: NonEmptyStr | None = None
    run_policy: BatchRunPolicy
    workers: int = Field(default=1, ge=1)
    variants: list[VersionVariant] = Field(default_factory=list)
    sweeps: list[Sweep] = Field(default_factory=list)
    conflicts: ConflictRequest | None = None

    @model_validator(mode="after")
    def _something_to_run(self) -> "BatchSpec":
        if not (self.variants or self.sweeps or self.conflicts):
            raise ValueError("a batch needs variants, sweeps or conflicts")
        ids = [variant.variant_id for variant in self.variants]
        if len(set(ids)) != len(ids):
            raise ValueError("variant_id must be unique")
        return self


class RunRecord(ContractModel):
    variant_id: NonEmptyStr
    kind: Literal["version", "sweep", "branch"]
    scenario_version: NonEmptyStr
    seed: int
    outcome: NonEmptyStr
    status: Literal["pass", "fail", "risky", "needs_more_test"]
    score: Probability
    hp_lost: NonNegative
    risk_events: NonNegative
    event_count: int = Field(ge=0)
    output_hash: NonEmptyStr


class VariantStats(ContractModel):
    """
    One variant over all its runs.

    Important:
    win, loss and draw are seen from the perspective faction. cost is own hp
    lost; risk is risk-relevant events against own entities; failure
    frequency is the share of fail verdicts. win_rate_ci is the Wilson 95%
    interval.
    """

    variant_id: NonEmptyStr
    kind: Literal["version", "sweep", "branch"]
    scenario_version: NonEmptyStr
    runs: int = Field(ge=1)
    win_rate: Probability
    win_rate_ci: list[Probability] = Field(min_length=2, max_length=2)
    loss_rate: Probability
    draw_rate: Probability
    failure_frequency: Probability
    mean_score: Probability
    score_stdev: NonNegative
    mean_hp_lost: NonNegative
    mean_risk_events: NonNegative
    mean_event_count: NonNegative
    outcomes: dict[str, int]
    distinct_outputs: int = Field(ge=1)


class BatchResult(ContractModel):
    batch_id: NonEmptyStr
    scenario_id: NonEmptyStr
    base_version: NonEmptyStr
    profile_id: NonEmptyStr
    perspective: NonEmptyStr
    repeat_count: int = Field(ge=1)
    seeds: list[int]
    workers: int = Field(ge=1)
    total_runs: int = Field(ge=1)
    variants: list[VariantStats]
    runs: list[RunRecord]


class ConflictingAction(ContractModel):
    actor_id: NonEmptyStr
    action_id: NonEmptyStr
    system_id: NonEmptyStr
    intent: str
    conflict_with: list[str]


class Conflict(ContractModel):
    conflict_id: NonEmptyStr
    proposals: list[NonEmptyStr] = Field(min_length=2, max_length=2)
    conflict_types: list[
        Literal[
            "resource_conflict",
            "timing_conflict",
            "objective_conflict",
            "risk_conflict",
            "location_conflict",
            "priority_conflict",
        ]
    ] = Field(min_length=1)
    reason: str


class BranchRun(ContractModel):
    branch_id: NonEmptyStr
    action_set: list[str]
    result_summary: NonEmptyStr
    evaluation_delta: dict[str, float]
    metrics: dict[str, float]


class Recommendation(ContractModel):
    required_decision: bool
    decision_reason: str


class ConflictPackage(ContractModel):
    """
    Formal Spec section 13 conflict package.

    Important:
    SKYVAULT never picks a side. Every compatible set of proposals ran as its
    own branch; the package shows what each branch led to, relative to a
    baseline with no proposals, and leaves the decision to NEXUS or the user.
    """

    conflict_id: NonEmptyStr
    scenario_id: NonEmptyStr
    conflicting_actions: list[ConflictingAction]
    conflict_type: list[str]
    conflicts: list[Conflict]
    branch_runs: list[BranchRun]
    baseline: BranchRun
    recommendation_to_nexus: Recommendation


def validate_batch_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a batch request. Raises ContractError when it breaks."""
    return check(BatchSpec, "batch_spec", data)


def validate_batch_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a batch result. Raises ContractError when it breaks."""
    return check(BatchResult, "batch_result", data)


def validate_conflict_package(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a conflict package. Raises ContractError when it breaks."""
    return check(ConflictPackage, "conflict_package", data)
