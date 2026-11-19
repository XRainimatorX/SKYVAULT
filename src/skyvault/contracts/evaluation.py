"""Evaluation Result contract = the verdict a finished run reports."""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check


class OverallJudgement(ContractModel):
    """The single-line verdict of Formal Spec section 8.3."""

    status: Literal["pass", "fail", "risky", "needs_more_test"]
    confidence: Probability


class Comparison(ContractModel):
    """Which other runs this one beat or lost to. Empty for a single run."""

    better_than: list[str] = Field(default_factory=list)
    worse_than: list[str] = Field(default_factory=list)


class AntiGamingSummary(ContractModel):
    """Whether the score was earned by a behaviour the profile forbids."""

    gaming_detected: bool
    flagged_behaviors: list[str]
    penalty_total: NonNegative


class Scores(ContractModel):
    """
    Formal Spec 8.3 scores, field by field: each in [0, 1], higher better,
    or null when the run could not judge it (the score breakdown says why).
    """

    physical_possibility: Probability | None
    engineering_feasibility: Probability | None
    tactical_usefulness: Probability | None
    strategic_value: Probability | None
    governance_stability: Probability | None
    crisis_resilience: Probability | None
    resource_efficiency: Probability | None
    risk_control: Probability | None
    system_robustness: Probability | None
    failure_resistance: Probability | None
    recovery_ability: Probability | None


class EvaluationResult(ContractModel):
    """
    Evaluation Result = Formal Spec section 8.3.

    Important:
    The first eight fields are the run-end summary the engine records in
    SCENARIO_END. Schema 0.4 makes the section 8.3 verdict required, as ADR
    004 promised, and adds what the verdict was reached under (profile_id,
    perspective), the overall score, and the anti-gaming summary that shows
    whether a high score was earned by gaming.

    scores are the eleven of section 8.3, null where the run could not
    judge them. additional_axes are the other section 8.2 axes (time cost,
    resource cost, risk growth, commercial demonstrability, imperial core
    value) and the development plan's mission success, logistics burden and
    stability impact, null likewise.
    """

    termination_reason: NonEmptyStr
    event_count: int = Field(ge=0)
    active_entities: int = Field(ge=0)
    destroyed_entities: int = Field(ge=0)
    active_factions: list[str]
    winner_or_result: NonEmptyStr
    key_findings: list[str]
    failure_points: list[str]

    scenario_id: NonEmptyStr
    profile_id: NonEmptyStr
    perspective: NonEmptyStr
    overall_judgement: OverallJudgement
    overall_score: Probability
    scores: Scores
    additional_axes: dict[str, Probability | None]
    failure_causes: list[str]
    recommended_next_tests: list[str]
    comparison: Comparison
    anti_gaming: AntiGamingSummary


def validate_evaluation_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an evaluation result. Raises ContractError when it breaks."""
    return check(EvaluationResult, "evaluation_result", data)
