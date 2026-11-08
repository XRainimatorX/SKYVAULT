"""Failure exploration contracts = how a stress test is asked for and reported."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, Probability, check

FAILURE_VARIABLE_NAMES = (
    "supply_delay",
    "sensor_failure",
    "communication_failure",
    "weather_degradation",
    "enemy_reaction_speed",
    "equipment_overheat",
    "civilian_pressure",
    "resource_shortage",
)
StressLevel = Literal["mild", "moderate", "severe", "collapse"]
FailureVariableName = Literal[
    "supply_delay",
    "sensor_failure",
    "communication_failure",
    "weather_degradation",
    "enemy_reaction_speed",
    "equipment_overheat",
    "civilian_pressure",
    "resource_shortage",
]


class RunPolicy(ContractModel):
    """How many times each stressed plan runs, and with which seeds."""

    repeat_count: int = Field(ge=1)
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"]
    branch_comparison: bool = False


class FailureExplorationSpec(ContractModel):
    """
    Formal Spec section 14 failure_exploration, as a scenario declares it.

    Important:
    stress_levels lists which of the four fixed levels to run; their strength
    per variable is defined by the failure engine, not by the scenario.
    alternatives names other versions of the same scenario to stress the same
    way. A run survives unless its verdict is fail; a level breaks the plan
    when fewer than survival_threshold of its repeats survive. output keeps
    the section 14 placeholder and is ignored.
    """

    objective: NonEmptyStr = "find_weakness"
    failure_variables: list[FailureVariableName] = Field(min_length=1)
    stress_levels: list[StressLevel] = Field(min_length=1)
    run_policy: RunPolicy
    alternatives: list[NonEmptyStr] = Field(default_factory=list)
    survival_threshold: Probability = 0.5
    output: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _no_repeats(self) -> "FailureExplorationSpec":
        if len(set(self.stress_levels)) != len(self.stress_levels):
            raise ValueError("stress_levels must not repeat")
        if len(set(self.failure_variables)) != len(self.failure_variables):
            raise ValueError("failure_variables must not repeat")
        return self


class LevelResult(ContractModel):
    level: StressLevel
    survival_rate: Probability
    mean_score: Probability
    mean_first_loss_tick: float | None
    most_common_failure: str | None


class VariableResult(ContractModel):
    variable: FailureVariableName
    applicable: bool
    reason: str
    assumption: str
    levels: list[LevelResult]
    breaking_level: StressLevel | None
    sensitivity: float


class Baseline(ContractModel):
    survival_rate: Probability
    mean_score: Probability
    outcomes: dict[str, int]
    fails_without_stress: bool


class BranchResult(ContractModel):
    variables: list[FailureVariableName]
    level: StressLevel
    survival_rate: Probability
    mean_score: Probability


class AlternativeResult(ContractModel):
    scenario_version: NonEmptyStr
    baseline_survival_rate: Probability
    breaking_levels: dict[str, StressLevel | None]
    holds_longer_on: list[str]
    breaks_sooner_on: list[str]
    verdict: Literal["holds_longer", "breaks_sooner", "mixed", "same"]


class FailureMap(ContractModel):
    """
    The failure map a failure exploration produces (development plan Phase 9).

    Important:
    It answers the section 14 questions in fixed places: where the plan fails
    (failure_points), why (failure_causes), how fast (how_fast), which
    variable crushes it and which assumption that attacks (crushing_variable,
    crushing_assumption), and which alternative lasts longer (alternatives).
    """

    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    perspective: NonEmptyStr
    profile_id: NonEmptyStr
    objective: NonEmptyStr
    repeat_count: int = Field(ge=1)
    seeds: list[int]
    survival_threshold: Probability
    baseline: Baseline
    variables: list[VariableResult]
    crushing_variable: FailureVariableName | None
    crushing_assumption: str | None
    failure_points: list[str]
    failure_causes: list[str]
    how_fast: dict[str, float | None]
    branches: list[BranchResult]
    alternatives: list[AlternativeResult]
    best_alternative: str | None


def validate_failure_exploration(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a failure exploration request. Raises ContractError when it breaks."""
    return check(FailureExplorationSpec, "failure_exploration", data)


def validate_failure_map(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a failure map. Raises ContractError when it breaks."""
    return check(FailureMap, "failure_map", data)
