from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from skyvault.entity import Position


def new_action_id() -> str:
    return f"action_{uuid4().hex[:10]}"


@dataclass
class Action:
    """
    Action = what an actor attempts to do.

    Important:
    SKYVAULT core does not decide this.
    The actor policy decides this.

    SKYVAULT only validates and resolves it.
    """

    action_id: str
    actor_id: str
    action_type: str
    target_entity_id: str | None = None
    target_position: Position | None = None
    intent: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)