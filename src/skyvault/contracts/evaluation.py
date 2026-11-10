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


class EvaluationResult(ContractModel):
    """
    Evaluation Result = Formal Spec section 8.3.

    Important:
    The first eight fields are the run-end summary the engine records in
    SCENARIO_END. Schema 0.4 makes the section 8.3 verdict required, as ADR
    004 promised, and adds what the verdict was reached under (profile_id,
    perspective), the overall score, and the anti-gaming summary that shows
    whether a high score was earned by gaming.

    scores holds every axis that had data, each in [0, 1], higher better.
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
    scores: dict[str, Probability]
    failure_causes: list[str]
    recommended_next_tests: list[str]
    comparison: Comparison
    anti_gaming: AntiGamingSummary


def validate_evaluation_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an evaluation result. Raises ContractError when it breaks."""
    return check(EvaluationResult, "evaluation_result", data)
