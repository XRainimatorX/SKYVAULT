"""Evaluation Profile contract = how a run is judged, separate from the run."""

from typing import Any

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check

# The evaluation axes Phase 7 implements; profiles may only weight these
METRIC_NAMES = (
    "mission_success",
    "tactical_value",
    "strategic_value",
    "resource_cost",
    "time_cost",
    "risk_growth",
    "failure_resistance",
    "recovery_ability",
    "system_robustness",
    "logistics_burden",
    "stability_impact",
)

# Each anti-gaming check and the optimisation behaviour it detects
ANTI_GAMING_BEHAVIORS = {
    "inaction_penalty": "maximize_score_by_inaction",
    "stability_penalty": "sacrifice_long_term_stability_for_short_term_success",
    "risk_spike_penalty": "extreme_high_risk_optimization",
    "hidden_risk_penalty": "ignore_hidden_risk_to_improve_visible_score",
    "long_term_cost_penalty": "sacrifice_strategic_value_for_short_term_tactical_value",
}


class Thresholds(ContractModel):
    """Overall score at or above pass passes; below fail fails."""

    passing: Probability = Field(alias="pass")
    fail: Probability

    @model_validator(mode="after")
    def _fail_not_above_pass(self) -> "Thresholds":
        if self.fail > self.passing:
            raise ValueError("thresholds.fail cannot be above thresholds.pass")
        return self


class AntiGamingMetric(ContractModel):
    """One anti-gaming check, Formal Spec section 16, with its trigger and cost."""

    metric: NonEmptyStr
    reason: str
    threshold: NonNegative
    penalty: Probability

    @model_validator(mode="after")
    def _known_check(self) -> "AntiGamingMetric":
        if self.metric not in ANTI_GAMING_BEHAVIORS:
            raise ValueError(f"unknown anti-gaming metric {self.metric!r}")
        return self


class EvaluationProfile(ContractModel):
    """
    Evaluation Profile = which axes count, how much, and what counts as gaming.

    Important:
    The same run can be judged under different profiles; the profile never
    changes what happened, only the verdict. perspective is the faction whose
    plan is judged; null means "decide from the scenario".

    The section 16 fields keep their spec names. A triggered check only costs
    score, and only counts as gaming, when its behaviour is listed in
    forbidden_optimization_behaviors.
    """

    profile_id: NonEmptyStr
    description: str = ""
    perspective: NonEmptyStr | None
    primary_metric: NonEmptyStr
    secondary_metrics: list[NonEmptyStr]
    weights: dict[NonEmptyStr, NonNegative]
    thresholds: Thresholds
    anti_gaming_metrics: list[AntiGamingMetric]
    forbidden_optimization_behaviors: list[NonEmptyStr]
    tradeoff_report_required: bool

    @model_validator(mode="after")
    def _names_are_known(self) -> "EvaluationProfile":
        named = [self.primary_metric, *self.secondary_metrics, *self.weights]
        unknown = sorted({name for name in named if name not in METRIC_NAMES})
        if unknown:
            raise ValueError(f"unknown metrics {unknown}")
        if not any(weight > 0 for weight in self.weights.values()):
            raise ValueError("at least one metric needs a positive weight")
        behaviors = set(ANTI_GAMING_BEHAVIORS.values())
        strange = sorted(set(self.forbidden_optimization_behaviors) - behaviors)
        if strange:
            raise ValueError(f"unknown optimisation behaviours {strange}")
        return self


def validate_evaluation_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an evaluation profile. Raises ContractError when it breaks."""
    return check(EvaluationProfile, "evaluation_profile", data)
