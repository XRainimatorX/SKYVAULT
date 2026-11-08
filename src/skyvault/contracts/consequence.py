"""Consequence contract = what resolving an action does to the world."""

from typing import Any

from .base import ContractModel, NonEmptyStr, check


class EntityChangeRecord(ContractModel):
    """One entity change and the event that records it. changes may be empty."""

    entity_id: NonEmptyStr
    event_type: NonEmptyStr
    changes: dict[str, Any]


class ResourceChangeRecord(ContractModel):
    """One change to a world resource stock."""

    resource_id: NonEmptyStr
    delta: float
    event_type: NonEmptyStr


class DirectEffectsRecord(ContractModel):
    """
    Formal Spec section 6.3 direct effects.

    Important:
    state_changes is the world environment. No environment model exists yet,
    so the list is accepted here but applying a non-empty one raises.
    """

    state_changes: list[dict[str, Any]]
    resource_changes: list[ResourceChangeRecord]
    entity_changes: list[EntityChangeRecord]


class SecondaryEffectsRecord(ContractModel):
    """Descriptive wider effects; nothing here changes the world yet."""

    risk_changes: list[dict[str, Any]]
    stability_changes: list[dict[str, Any]]
    public_order_changes: list[dict[str, Any]]
    logistical_changes: list[dict[str, Any]]


class ChainReactionRecord(ContractModel):
    """A further event one effect set off. event_id is null until applied."""

    event_id: str | None
    cause: NonEmptyStr
    effect: NonEmptyStr


class EvaluationImpactRecord(ContractModel):
    """How the action moves the verdict. Scored from Phase 7."""

    cost_delta: float
    risk_delta: float
    stability_delta: float
    tactical_value_delta: float
    strategic_value_delta: float


class ConsequenceRecord(ContractModel):
    """
    Consequence = what resolving one action will do to the world.

    Important:
    Schema 0.3 adopts Formal Spec section 6.3: effects are grouped, and
    secondary effects, chain reactions and the five evaluation deltas are
    required. A rejected consequence carries them all empty.
    """

    action_id: NonEmptyStr
    accepted: bool
    reason: str
    direct_effects: DirectEffectsRecord
    secondary_effects: SecondaryEffectsRecord
    chain_reactions: list[ChainReactionRecord]
    evaluation_impact: EvaluationImpactRecord


def validate_consequence(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one consequence. Raises ContractError when it breaks the contract."""
    return check(ConsequenceRecord, "consequence", data)
