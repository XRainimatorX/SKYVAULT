"""Action contract = how an actor's intent is submitted to the world."""

from typing import Any

from pydantic import Field

from .base import ContractModel, Location, NonEmptyStr, NonNegative, Probability, check


class ActionTargetRecord(ContractModel):
    """What the action is aimed at. Any of the three may be null."""

    entity_id: str | None
    location: Location | None
    system_id: str | None


class ActionRecord(ContractModel):
    """
    Action = what an actor attempts, before the world has agreed to it.

    Important:
    actor_id is mandatory. An action nobody owns cannot be validated, resolved
    or attributed in event memory, so it is rejected at the door.

    Schema 0.3 adopts Formal Spec section 6.2 whole: target is nested, and the
    six fields ADR 004 left optional are required. required_resources maps a
    resource id to a non-negative amount. expected_duration, expected_effect,
    risk_profile and priority are declarations, recorded but not enforced.
    """

    action_id: NonEmptyStr
    actor_id: NonEmptyStr
    action_type: NonEmptyStr
    target: ActionTargetRecord
    intent: str
    required_resources: dict[NonEmptyStr, NonNegative]
    expected_duration: str
    expected_effect: str
    risk_profile: dict[str, Any]
    priority: str
    confidence: Probability
    metadata: dict[str, Any] = Field(default_factory=dict)


def validate_action(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one action. Raises ContractError when it breaks the contract."""
    return check(ActionRecord, "action", data)
