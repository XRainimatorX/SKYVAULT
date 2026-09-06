"""Entity = anything that exists in the world and can be acted on."""

from dataclasses import dataclass, field
from typing import Any

Position = tuple[int, int]


@dataclass
class Entity:
    """
    Entity = something that exists inside the SKYVAULT world.

    This replaces the old groundunit / humanbody / groundweapon bundle.

    Tactical data such as hp, ap, weapon damage, range, and accuracy are now
    stored as state and capabilities.
    """

    entity_id: str
    name: str
    entity_type: str
    faction: str | None
    position: Position | None
    state: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def is_active(self) -> bool:
        """
        True while this entity still counts as alive.

        Important:
        A destroyed entity is never removed from the world, only marked. Event
        memory keeps referring to it, so it has to stay addressable by id.
        """
        return self.state.get("status", "active") == "active"

    def snapshot(self) -> dict[str, Any]:
        """
        Snapshot = this entity as plain JSON-safe data.

        Important:
        state, capabilities and tags are copied rather than shared, so a
        snapshot recorded into an event never changes afterwards.
        """
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "faction": self.faction,
            "position": list(self.position) if self.position else None,
            "state": dict(self.state),
            "capabilities": dict(self.capabilities),
            "tags": list(self.tags),
        }
