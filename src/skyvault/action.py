"""Action = an intent an actor submits, before the world has agreed to it."""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .entity import Location


def new_action_id() -> str:
    """
    A fresh action id.

    Important:
    This uses uuid4 and is therefore not controlled by the scenario
    random_seed. Behaviour repeats across runs; these ids do not.
    """
    return f"action_{uuid4().hex[:10]}"


def location_to_json(location: Location | None) -> Any:
    """A location as JSON writes it: a grid cell becomes a list, a node id stays."""
    if isinstance(location, tuple):
        return list(location)
    return location


@dataclass
class ActionTarget:
    """
    What an action is aimed at: an entity, a location, or another system.

    Any of the three may be None. A move names a location, an attack names an
    entity, a wait names nothing.
    """

    entity_id: str | None = None
    location: Location | None = None
    system_id: str | None = None


@dataclass
class Action:
    """
    Action = what an actor attempts to do. Formal Spec section 6 calls it an
    Action Attempt.

    Important:
    SKYVAULT core does not decide this.
    The actor policy decides this.

    SKYVAULT only validates and resolves it. Nothing on an Action changes the
    world; the Consequence the world returns does.

    required_resources is what the actor expects to spend. The world charges
    the rule_set's action cost instead when it defines one.

    expected_duration, expected_effect, risk_profile and priority are
    declarations the world records but does not enforce yet.
    """

    action_id: str
    actor_id: str
    action_type: str
    target: ActionTarget = field(default_factory=ActionTarget)
    intent: str = ""
    required_resources: dict[str, float] = field(default_factory=dict)
    expected_duration: str = "1_tick"
    expected_effect: str = ""
    risk_profile: dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """The action in its contract shape, JSON-safe."""
        return {
            "action_id": self.action_id,
            "actor_id": self.actor_id,
            "action_type": self.action_type,
            "target": {
                "entity_id": self.target.entity_id,
                "location": location_to_json(self.target.location),
                "system_id": self.target.system_id,
            },
            "intent": self.intent,
            "required_resources": dict(self.required_resources),
            "expected_duration": self.expected_duration,
            "expected_effect": self.expected_effect,
            "risk_profile": dict(self.risk_profile),
            "priority": self.priority,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


# Formal Spec section 6 names the submitted intent an Action Attempt
ActionAttempt = Action
