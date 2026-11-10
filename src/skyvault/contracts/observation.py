"""Observation contracts = who sees what (Formal Spec section 5).

Important:
An observer profile says how one outside system looks at the world: which
view it gets, how late and how detailed. An observation is what it gets at
one moment — never the world itself. What it cannot see is only admitted
to exist (hidden_state); nothing about it is given away.
"""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, Location, NonEmptyStr, Probability, check

VIEWS = ("local", "aggregate", "mission", "threat", "coverage")
EnemyDetail = Literal["exact", "banded", "hidden"]
SourceQuality = Literal["low", "medium", "high"]


class ObserverProfile(ContractModel):
    """
    How one system observes (data/observers/).

    Important:
    delay_ticks: the observation at tick t shows tick t - delay_ticks.
    stale_after_ticks: how long a contact lost from sight is remembered.
    default_sensor_range: for units without a sensor_range capability.
    local_radius: the area around the deciding unit in the local view.
    enemy_detail: how much of an enemy's health is shown.
    """

    observer_id: NonEmptyStr
    description: str = ""
    view: Literal["local", "aggregate", "mission", "threat", "coverage"]
    delay_ticks: int = Field(default=0, ge=0)
    stale_after_ticks: int = Field(default=0, ge=0)
    default_sensor_range: float = Field(default=5.0, ge=0.0)
    local_radius: int = Field(default=0, ge=0)
    enemy_detail: EnemyDetail = "exact"
    source_quality: SourceQuality = "medium"


class Viewpoint(ContractModel):
    faction: NonEmptyStr
    actor_id: NonEmptyStr | None = None


class KnownEntity(ContractModel):
    """
    One unit as the observer knows it.

    Important:
    Own units (self, ally) are exact and carry their state and capabilities
    (state since Phase 6: energy, ammunition, morale...). An enemy
    is visible, destroyed (a wreck in sight) or stale (lost from sight: where
    and how it was at last_seen, age ticks ago); hp or hp_band follow the
    profile's enemy_detail, and its state and capabilities are never given.
    """

    entity_id: NonEmptyStr
    faction: NonEmptyStr
    relation: Literal["self", "ally", "enemy"]
    status: Literal["active", "destroyed", "visible", "stale"]
    position: Location | None
    hp: float | None
    hp_band: Literal["intact", "damaged", "critical"] | None
    confidence: Probability
    last_seen: int | None = Field(default=None, ge=0)
    age: int | None = Field(default=None, ge=0)
    capabilities: dict[str, Any] | None = None
    state: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _stale_has_age(self) -> "KnownEntity":
        if (self.status == "stale") != (self.age is not None):
            raise ValueError("age is given exactly when status is stale")
        if self.relation != "enemy" and self.status not in ("active", "destroyed"):
            raise ValueError("own units are active or destroyed")
        if (self.relation == "enemy") == (self.capabilities is not None):
            raise ValueError("capabilities are given for own units only")
        if self.relation == "enemy" and self.state is not None:
            raise ValueError("state is given for own units only")
        return self


class VisibleWorldState(ContractModel):
    local_area: dict[str, Any] | None
    known_entities: list[KnownEntity]
    known_risks: list[dict[str, Any]]
    resources_visible: dict[str, Any]
    summary: dict[str, Any]


class HiddenState(ContractModel):
    """Only that something is out of sight, and why: never what or how much."""

    exists: bool
    reason: NonEmptyStr | None

    @model_validator(mode="after")
    def _reason_when_hidden(self) -> "HiddenState":
        if self.exists != (self.reason is not None):
            raise ValueError("reason is given exactly when hidden state exists")
        return self


class Uncertainty(ContractModel):
    confidence_level: Probability
    stale_after: int = Field(ge=0)
    source_quality: SourceQuality
    delay_ticks: int = Field(ge=0)
    observed_at: int = Field(ge=0)


class DecisionContext(ContractModel):
    mission_goal: Any
    constraints: list[str]
    available_actions: list[NonEmptyStr]


class Observation(ContractModel):
    """What one observer gets at one tick (Formal Spec section 5)."""

    observer_id: NonEmptyStr
    time: int = Field(ge=0)
    view: Literal["local", "aggregate", "mission", "threat", "coverage"]
    viewpoint: Viewpoint
    visible_world_state: VisibleWorldState
    hidden_state: HiddenState
    uncertainty: Uncertainty
    decision_context: DecisionContext

    @model_validator(mode="after")
    def _delay_consistent(self) -> "Observation":
        expected = max(0, self.time - self.uncertainty.delay_ticks)
        if self.uncertainty.observed_at != expected:
            raise ValueError("observed_at must be time - delay_ticks (at least 0)")
        return self


def validate_observer_profile(data: dict[str, Any]) -> dict[str, Any]:
    """An observer profile, or ContractError listing every violation."""
    return check(ObserverProfile, "observer_profile", data)


def validate_observation(data: dict[str, Any]) -> dict[str, Any]:
    """An observation, or ContractError listing every violation."""
    return check(Observation, "observation", data)
