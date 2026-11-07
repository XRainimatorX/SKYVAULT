"""Evaluation Result contract = the verdict a finished run reports."""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, Probability, check


class OverallJudgement(ContractModel):
    """The single-line verdict of Formal Spec section 8.3."""

    status: Literal["pass", "fail", "risky", "needs_more_test"]
    confidence: Probability


class Comparison(ContractModel):
    """Which other runs this one beat or lost to."""

    better_than: list[str] = Field(default_factory=list)
    worse_than: list[str] = Field(default_factory=list)


class EvaluationResult(ContractModel):
    """
    Evaluation Result = Formal Spec section 8.3.

    Important:
    The required fields are the win/lose summary evaluator.py produces today.
    The optional ones are the multi-axis verdict of section 8.3; Phase 7
    (Evaluation Engine) is where they get filled. Until then a run reports who
    survived and how many events it took, nothing more.
    """

    termination_reason: NonEmptyStr
    event_count: int = Field(ge=0)
    active_entities: int = Field(ge=0)
    destroyed_entities: int = Field(ge=0)
    active_factions: list[str]
    winner_or_result: NonEmptyStr
    key_findings: list[str]
    failure_points: list[str]

    scenario_id: str | None = None
    overall_judgement: OverallJudgement | None = None
    scores: dict[str, float] | None = None
    failure_causes: list[str] | None = None
    recommended_next_tests: list[str] | None = None
    comparison: Comparison | None = None


def validate_evaluation_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an evaluation result. Raises ContractError when it breaks."""
    return check(EvaluationResult, "evaluation_result", data)
