from dataclasses import dataclass, field
from typing import Any

from skyvault.entity import Entity, Position
from skyvault.event_memory import Event, new_event_id


@dataclass
class SpaceModel:
    """
    Minimal space model.

    This is currently a simple grid because we are starting from the tactical side.
    Later this can evolve into city network, road graph, airspace, facility map, etc.
    """

    width: int
    height: int
    distance_model: str = "chebyshev"

    def is_inside(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height

    def distance(self, a: Position, b: Position) -> int:
        ax, ay = a
        bx, by = b

        if self.distance_model == "manhattan":
            return abs(ax - bx) + abs(ay - by)

        if self.distance_model == "euclidean_floor":
            return int(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)

        return max(abs(ax - bx), abs(ay - by))


@dataclass
class WorldState:
    """
    WorldState = current world condition.

    This is the first true SKYVAULT-shaped object in this slice.
    """

    world_id: str
    scenario_id: str
    tick: int
    space: SpaceModel
    entities: dict[str, Entity]
    assumptions: dict[str, Any] = field(default_factory=dict)
    event_memory: list[Event] = field(default_factory=list)

    def get_entity(self, entity_id: str) -> Entity:
        if entity_id not in self.entities:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        return self.entities[entity_id]

    def active_entities(self) -> list[Entity]:
        return [entity for entity in self.entities.values() if entity.is_active()]

    def active_factions(self) -> set[str]:
        return {
            entity.faction
            for entity in self.active_entities()
            if entity.faction is not None
        }

    def is_occupied(self, position: Position) -> bool:
        for entity in self.active_entities():
            if entity.position == position:
                return True
        return False

    def record_event(
        self,
        event_type: str,
        actor_id: str | None,
        target_entity_id: str | None,
        source_action_id: str | None,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Event:
        event = Event(
            event_id=new_event_id(),
            time=self.tick,
            event_type=event_type,
            actor_id=actor_id,
            target_entity_id=target_entity_id,
            source_action_id=source_action_id,
            before_state=before_state,
            after_state=after_state,
            data=data or {},
            tags=tags or [],
        )

        self.event_memory.append(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "scenario_id": self.scenario_id,
            "tick": self.tick,
            "space": {
                "width": self.space.width,
                "height": self.space.height,
                "distance_model": self.space.distance_model,
            },
            "entities": {
                entity_id: entity.snapshot()
                for entity_id, entity in self.entities.items()
            },
            "assumptions": self.assumptions,
        }