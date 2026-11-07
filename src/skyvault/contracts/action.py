"""Action contract = how an actor's intent is submitted to the world."""

from typing import Any

from pydantic import Field

from .base import ContractModel, NonEmptyStr, Position, Probability, check


class ActionRecord(ContractModel):
    """
    Action = what an actor attempts, before the world has agreed to it.

    Important:
    actor_id is mandatory. An action nobody owns cannot be validated, resolved
    or attributed in event memory, so it is rejected at the door.

    The fields after metadata come from Formal Spec section 6.2 and are not
    produced by any actor yet. They are optional until Phase 3 generalises the
    action framework.
    """

    action_id: NonEmptyStr
    actor_id: NonEmptyStr
    action_type: NonEmptyStr
    target_entity_id: str | None = None
    target_position: Position | None = None
    intent: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    required_resources: dict[str, Any] | None = None
    expected_duration: str | None = None
    expected_effect: str | None = None
    risk_profile: dict[str, Any] | None = None
    priority: str | None = None
    confidence: Probability | None = None


def validate_action(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one action. Raises ContractError when it breaks the contract."""
    return check(ActionRecord, "action", data)
