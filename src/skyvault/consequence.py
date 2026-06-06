from dataclasses import dataclass, field
from typing import Any


@dataclass
class Consequence:
    """
    Consequence = result of resolving an action.

    This is the early form of:

    Action Attempt
    → Validation
    → Resolution
    → Consequence
    → World State Mutation
    → Event Memory
    """

    action_id: str
    accepted: bool
    reason: str
    direct_effects: list[dict[str, Any]] = field(default_factory=list)
    evaluation_impact: dict[str, Any] = field(default_factory=dict)