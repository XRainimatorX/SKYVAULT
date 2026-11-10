"""Order = what an actor submits: the intent of one Action, before it has an id.

Important:
An actor never builds the Action itself (development plan Phase 6). It
says what it wants done; the run issues the action id, names the actor
and records the deciding system. A scheduled action (Phase 10) is an order
with the tick, actor and system it is for.
"""

from typing import Any

from pydantic import Field

from .base import (
    ContractModel,
    Location,
    NonEmptyStr,
    NonNegative,
    Probability,
    check,
)


class OrderTarget(ContractModel):
    """What an order aims at: name only what applies; the rest is null."""

    entity_id: str | None = None
    location: Location | None = None
    system_id: str | None = None


class Order(ContractModel):
    """One action intent. Fields left out take their contract defaults."""

    action_type: NonEmptyStr
    target: OrderTarget
    intent: str = ""
    required_resources: dict[NonEmptyStr, NonNegative] = Field(default_factory=dict)
    expected_effect: str = ""
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"
    confidence: Probability = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


def validate_order(data: dict[str, Any]) -> dict[str, Any]:
    """An order, or ContractError listing every violation."""
    return check(Order, "order", data)
