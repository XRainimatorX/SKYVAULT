"""Result Package contract = everything one run hands back."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check
from .entity import EntityRecord
from .evaluation import EvaluationResult
from .event import EventRecord
from .reproducibility import ReproducibilityMetadata


class WorldSnapshot(ContractModel):
    """
    The whole world at one moment, as WorldState.snapshot() writes it.

    Important:
    resources is part of the snapshot so event sourcing can check a rebuilt
    world against a recorded one, stock for stock.
    """

    world_id: NonEmptyStr
    scenario_id: NonEmptyStr
    tick: int = Field(ge=0)
    space: dict[str, Any]
    entities: dict[str, EntityRecord]
    assumptions: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, NonNegative]


class ScoreEntry(ContractModel):
    """One evaluation axis: its score, the raw number behind it, and why."""

    score: Probability
    raw: float
    unit: str
    weight: NonNegative
    applicable: bool
    description: str
    explanation: str


class AntiGamingCheck(ContractModel):
    """One anti-gaming check as it ran."""

    metric: NonEmptyStr
    reason: str
    value: float
    threshold: NonNegative
    triggered: bool
    behavior: NonEmptyStr
    forbidden: bool
    penalty: Probability


class AntiGamingReport(ContractModel):
    """Formal Spec section 16, plus what each check found."""

    scenario_id: NonEmptyStr
    profile_id: NonEmptyStr
    primary_metric: NonEmptyStr
    secondary_metrics: list[str]
    anti_gaming_metrics: list[dict[str, str]]
    forbidden_optimization_behaviors: list[str]
    tradeoff_report_required: bool
    checks: list[AntiGamingCheck]
    triggered_behaviors: list[str]
    flagged_behaviors: list[str]
    gaming_detected: bool
    penalty_total: NonNegative


class TradeoffItem(ContractModel):
    """Two axes that pull against each other, and how this run balanced them."""

    gain: NonEmptyStr
    gain_score: Probability
    cost: NonEmptyStr
    cost_score: Probability
    assessment: NonEmptyStr


class RankedAxis(ContractModel):
    metric: NonEmptyStr
    score: Probability


class TradeoffJudgement(ContractModel):
    status: Literal["pass", "fail", "risky", "needs_more_test"]
    confidence: Probability
    overall_score: Probability


class TradeoffAntiGaming(ContractModel):
    gaming_detected: bool
    flagged_behaviors: list[str]
    triggered_behaviors: list[str]


class TradeoffReport(ContractModel):
    """What the plan gained and what it paid for it (development plan Phase 7)."""

    scenario_id: NonEmptyStr
    profile_id: NonEmptyStr
    perspective: NonEmptyStr
    required: bool
    judgement: TradeoffJudgement
    tradeoffs: list[TradeoffItem]
    strongest: list[RankedAxis]
    weakest: list[RankedAxis]
    anti_gaming: TradeoffAntiGaming


class ResultPackage(ContractModel):
    """
    Result Package = one finished run.

    Important:
    evaluation_result is mandatory; a run without a verdict is not a result.
    The field was called evaluation before Phase 1 and was renamed to match the
    development plan's acceptance criterion and Formal Spec section 8.3. See
    ADR 004.

    The four derived outputs (timeline, replay, entity history, causal chain)
    are built from this package alone, so initial_world_state is required too.

    reproducibility stays optional until Phase 8 fills it.

    Schema 0.4 adds the Phase 7 outputs: score_breakdown, anti_gaming_report
    and tradeoff_report. The development plan requires the trade-off report
    in every result package, so all three are mandatory.
    """

    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    initial_world_state: WorldSnapshot
    final_world_state: WorldSnapshot
    event_memory: list[EventRecord]
    evaluation_result: EvaluationResult
    score_breakdown: dict[str, ScoreEntry]
    anti_gaming_report: AntiGamingReport
    tradeoff_report: TradeoffReport
    reproducibility: ReproducibilityMetadata | None = None

    @model_validator(mode="after")
    def _event_count_matches_event_memory(self) -> "ResultPackage":
        counted = self.evaluation_result.event_count
        recorded = len(self.event_memory)
        if counted != recorded:
            raise ValueError(
                f"evaluation_result.event_count is {counted} "
                f"but event_memory holds {recorded} events"
            )
        return self


def validate_result_package(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a result package. Raises ContractError when it breaks."""
    return check(ResultPackage, "result_package", data)
