"""The shape of a training transition, validated like a contract.

Important:
The record model belongs to the training pipeline, not to the core
contract pack: it is how SKYVAULT hands data to TAC ANGEL / STARTX, not how
SKYVAULT itself describes a world.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioMeta(_Model):
    scenario_id: str
    scenario_version: str
    domain: str | None
    profile_id: str
    perspective: str
    seed: int | None
    input_hash: str = Field(min_length=64, max_length=64)
    output_hash: str = Field(min_length=64, max_length=64)


class Decision(_Model):
    action_id: str
    action_type: str
    actor_id: str
    faction: str | None
    target_entity_id: str | None
    target_location: Any
    intent: str
    system_id: str | None


class Consequence(_Model):
    accepted: bool
    reason: str | None
    events: list[dict[str, Any]]


class Reward(_Model):
    damage_dealt: float = Field(ge=0)
    damage_taken: float = Field(ge=0)
    target_destroyed: bool
    own_destroyed: bool
    episode_score: float = Field(ge=0, le=1)


class FailureLabels(_Model):
    run_failure_causes: list[str]
    destroyed_later: bool
    mission_failed: bool


class Labels(_Model):
    inaction_gaming_label: bool
    risk_spike_label: bool
    stability_damage_label: bool
    short_term_overfit_label: bool
    hidden_risk_ignored_label: bool
    strategic_misalignment_label: bool


class Transition(_Model):
    """One decision: state, observation, action, consequence, reward, next state."""

    record_type: Literal["transition"] = "transition"
    scenario: ScenarioMeta
    tick: int = Field(ge=0)
    state: dict[str, Any]
    observation: dict[str, Any]
    action: Decision
    consequence: Consequence
    reward: Reward
    next_state: dict[str, Any]
    done: bool
    event_sequence: list[str]
    failure_labels: FailureLabels
    labels: Labels
    violations: list[str]
    success_type: Literal["genuine_success", "false_success", "failure"]


def validate_transition(record: dict[str, Any]) -> dict[str, Any]:
    """The transition as the model normalises it. Raises ValueError."""
    try:
        return Transition.model_validate(record).model_dump(mode="json")
    except ValidationError as error:
        raise ValueError(str(error)) from None
