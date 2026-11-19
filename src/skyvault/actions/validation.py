"""Action validation = may this action happen, and can the world afford it."""

from dataclasses import dataclass
from typing import Any

from ..action import Action
from ..world_state import WorldState


@dataclass(frozen=True)
class ActionValidation:
    """
    The world's answer to "may this action happen?".

    Important:
    A refusal is an answer, not an error. The resolver turns it into a
    rejected Consequence and the run records it and carries on. Errors are for
    broken code: an action that breaks its contract, an unknown entity id.
    """

    valid: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "ActionValidation":
        return cls(valid=True)

    @classmethod
    def reject(cls, reason: str) -> "ActionValidation":
        return cls(valid=False, reason=reason)


def action_cost(world: WorldState, action: Action) -> dict[str, float]:
    """
    What the world charges for this action.

    Important:
    world_contract.rule_set.action_costs[action_type] wins when the world
    defines it: a scenario sets the price, not the actor. Otherwise the actor's
    own required_resources is charged.
    """
    costs: Any = world.rules.get("action_costs", {})
    if isinstance(costs, dict) and action.action_type in costs:
        return {key: float(value) for key, value in costs[action.action_type].items()}
    return {key: float(value) for key, value in action.required_resources.items()}


def check_resources(world: WorldState, cost: dict[str, float]) -> ActionValidation:
    """Refuse when any resource the cost names is missing or short."""
    for resource_id, needed in sorted(cost.items()):
        have = (
            world.resources.amount(resource_id)
            if resource_id in world.resources
            else 0.0
        )
        if have < needed:
            return ActionValidation.reject(
                f"Insufficient {resource_id}: have {have}, need {needed}"
            )
    return ActionValidation.ok()
