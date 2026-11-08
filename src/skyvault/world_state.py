"""World state = the space, the entities in it, and the events recorded so far."""

from dataclasses import dataclass, field
from typing import Any

from .contracts import validate_event
from .entity import Entity, Position
from .event_memory import (
    Event,
    build_causal_links,
    build_evaluation_relevance,
    new_event_id,
)
from .runtime.space import Space


@dataclass
class WorldState:
    """
    WorldState = current world condition.

    This is the first true SKYVAULT-shaped object in this slice.
    """

    world_id: str
    scenario_id: str
    tick: int
    space: Space
    entities: dict[str, Entity]
    assumptions: dict[str, Any] = field(default_factory=dict)
    event_memory: list[Event] = field(default_factory=list)

    def get_entity(self, entity_id: str) -> Entity:
        """
        The entity with this id.

        Important:
        Raises KeyError rather than returning None, so a bad id fails loudly
        instead of turning into a silent no-op further down.
        """
        if entity_id not in self.entities:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        return self.entities[entity_id]

    def active_entities(self) -> list[Entity]:
        """Every entity still alive. Destroyed entities stay in self.entities."""
        return [entity for entity in self.entities.values() if entity.is_active()]

    def active_factions(self) -> set[str]:
        """The factions that still have at least one living entity."""
        return {
            entity.faction
            for entity in self.active_entities()
            if entity.faction is not None
        }

    def is_occupied(self, position: Position) -> bool:
        """True when a living entity stands on this position."""
        return any(entity.position == position for entity in self.active_entities())

    def record_event(
        self,
        event_type: str,
        actor_id: str | None,
        target_entity_id: str | None,
        source_action_id: str | None,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        system_id: str | None = None,
        affected_entities: list[str] | None = None,
        affected_locations: list[Any] | None = None,
        affected_resources: list[str] | None = None,
        affected_risks: list[str] | None = None,
        causal_links: dict[str, list[str]] | None = None,
        evaluation_relevance: dict[str, bool] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Event:
        """
        record_event = append one finished fact to event memory.

        Important:
        Callers only pass what they actually know.

        Everything they leave out is filled with its empty structure here, so
        event memory never holds a half-shaped event.

        The finished event is checked against the event contract before it is
        appended. A malformed event raises ContractError and never reaches
        event memory.
        """
        event = Event(
            event_id=new_event_id(),
            time=self.tick,
            event_type=event_type,
            actor_id=actor_id,
            system_id=system_id,
            target_entity_id=target_entity_id,
            source_action_id=source_action_id,
            before_state=before_state,
            after_state=after_state,
            affected_entities=list(affected_entities or []),
            affected_locations=list(affected_locations or []),
            affected_resources=list(affected_resources or []),
            affected_risks=list(affected_risks or []),
            causal_links=build_causal_links(causal_links),
            evaluation_relevance=build_evaluation_relevance(evaluation_relevance),
            data=data or {},
            tags=tags or [],
        )

        validate_event(event.to_dict())
        self.link_causal_predecessor(event)
        self.event_memory.append(event)

        return event

    def link_causal_predecessor(self, event: Event) -> None:
        """
        Important:
        This is bookkeeping, not causal inference.

        Two events are linked only when the engine already resolved both of them
        from the same action, so nothing is guessed here.
        """
        if event.source_action_id is None:
            return

        for earlier in reversed(self.event_memory):
            if earlier.source_action_id != event.source_action_id:
                continue

            event.causal_links["caused_by"].append(earlier.event_id)
            earlier.causal_links["caused_events"].append(event.event_id)

            return

    def snapshot(self) -> dict[str, Any]:
        """
        Snapshot = the whole world as plain JSON-safe data.

        Important:
        This is a copy, not a view. Later mutations to the world never reach a
        snapshot that was already taken, which is what lets the result package
        keep an initial and a final state that stay distinct.
        """
        return {
            "world_id": self.world_id,
            "scenario_id": self.scenario_id,
            "tick": self.tick,
            "space": self.space.describe(),
            "entities": {
                entity_id: entity.snapshot()
                for entity_id, entity in self.entities.items()
            },
            "assumptions": self.assumptions,
        }
