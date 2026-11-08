"""World state = the space, the entities in it, and the events recorded so far."""

from dataclasses import dataclass, field
from typing import Any

from .contracts import validate_event
from .entity import Entity, Location
from .event_memory import (
    Event,
    build_causal_links,
    build_evaluation_relevance,
)
from .runtime.clock import Clock, TickClock
from .runtime.ids import RunIds
from .runtime.registry import EntityRegistry
from .runtime.resources import ResourceState
from .runtime.rules import RuleSet
from .runtime.space import Space


@dataclass
class WorldState:
    """
    WorldState = current world condition.

    Important:
    Build it with runtime.world.create_world(), which reads space, clock,
    resources and rules from the world contract. tick is the world's current
    time in its own unit, whatever kind of clock advances it; the name stays
    tick because every event and snapshot already records time under it.

    Every change to the world goes through a method that records an event:
    mutate_entity() and change_resource(). An action's changes reach them
    only through actions.resolver.apply_consequence().
    """

    world_id: str
    scenario_id: str
    tick: int
    space: Space
    entities: EntityRegistry
    assumptions: dict[str, Any] = field(default_factory=dict)
    event_memory: list[Event] = field(default_factory=list)
    resources: ResourceState = field(default_factory=ResourceState)
    rules: RuleSet = field(default_factory=RuleSet)
    clock: Clock = field(default_factory=TickClock)
    ids: RunIds = field(default_factory=RunIds)

    def get_entity(self, entity_id: str) -> Entity:
        """
        The entity with this id.

        Important:
        Raises KeyError rather than returning None, so a bad id fails loudly
        instead of turning into a silent no-op further down.
        """
        return self.entities.require(entity_id)

    def active_entities(self) -> list[Entity]:
        """Every entity still alive. Destroyed entities stay in self.entities."""
        return self.entities.active()

    def active_factions(self) -> set[str]:
        """The factions that still have at least one living entity."""
        return {
            entity.faction
            for entity in self.active_entities()
            if entity.faction is not None
        }

    def advance_time(self) -> int:
        """
        Move the world's clock forward once and return the new time.

        Important:
        The clock decides how far: one tick, one phase, or straight to the next
        scheduled happening. world.tick always mirrors clock.now afterwards.
        """
        self.tick = self.clock.advance()
        return self.tick

    def change_resource(
        self,
        resource_id: str,
        delta: float,
        actor_id: str | None = None,
        system_id: str | None = None,
        source_action_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        """
        Change a world-level resource and record it as RESOURCE_CHANGED.

        Important:
        before_state and after_state hold {resource_id, amount}, and
        affected.resources names the resource, so event sourcing can rebuild
        the stock and readers can find every change to it. A change that would
        go below zero raises before anything is recorded.
        """
        before, after = self.resources.change(resource_id, delta)

        return self.record_event(
            event_type="RESOURCE_CHANGED",
            actor_id=actor_id,
            system_id=system_id,
            target_entity_id=None,
            source_action_id=source_action_id,
            before_state={"resource_id": resource_id, "amount": before},
            after_state={"resource_id": resource_id, "amount": after},
            affected_resources=[resource_id],
            evaluation_relevance={"affects_cost": True},
            data={"delta": delta, **(data or {})},
            tags=["resource_change", "world_state_mutation"],
        )

    def mutate_entity(
        self,
        entity_id: str,
        changes: dict[str, Any],
        event_type: str,
        actor_id: str | None = None,
        system_id: str | None = None,
        source_action_id: str | None = None,
        target_entity_id: str | None = None,
        affected_entities: list[str] | None = None,
        affected_locations: list[Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        evaluation_relevance: dict[str, bool] | None = None,
    ) -> Event:
        """
        Change one entity and record the change as one event.

        Important:
        changes may hold "position" (the new location, None to take the
        entity off the map) and "state" (keys to set). Empty changes records
        the event and changes nothing. Any other key raises before anything
        happens.

        before_state and after_state are full entity snapshots, so event
        sourcing replays every entity event the same way.
        """
        unknown = set(changes) - {"position", "state"}
        if unknown:
            raise ValueError(f"unknown entity change keys: {sorted(unknown)}")

        entity = self.get_entity(entity_id)
        before = entity.snapshot()

        if "position" in changes:
            entity.position = changes["position"]
        entity.state.update(changes.get("state", {}))

        return self.record_event(
            event_type=event_type,
            actor_id=actor_id,
            system_id=system_id,
            target_entity_id=target_entity_id,
            source_action_id=source_action_id,
            before_state=before,
            after_state=entity.snapshot(),
            affected_entities=affected_entities,
            affected_locations=affected_locations,
            evaluation_relevance=evaluation_relevance,
            data=data,
            tags=tags,
        )

    def record_transition(
        self,
        event_type: str,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        actor_id: str | None = None,
        system_id: str | None = None,
        source_action_id: str | None = None,
        target_entity_id: str | None = None,
        affected_entities: list[str] | None = None,
        affected_locations: list[Any] | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        evaluation_relevance: dict[str, bool] | None = None,
    ) -> Event:
        """
        Record an event for a transition that already happened. Changes nothing.

        Important:
        A chain reaction uses this: the hit that took hp to zero is recorded by
        mutate_entity(), and the destruction it caused is recorded here with the
        same before and after.
        """
        return self.record_event(
            event_type=event_type,
            actor_id=actor_id,
            system_id=system_id,
            target_entity_id=target_entity_id,
            source_action_id=source_action_id,
            before_state=before_state,
            after_state=after_state,
            affected_entities=affected_entities,
            affected_locations=affected_locations,
            evaluation_relevance=evaluation_relevance,
            data=data,
            tags=tags,
        )

    def update_entity_state(
        self,
        entity_id: str,
        changes: dict[str, Any],
        actor_id: str | None = None,
        system_id: str | None = None,
        source_action_id: str | None = None,
    ) -> Event:
        """
        Merge changes into an entity's state and record ENTITY_STATE_CHANGED.

        Important:
        A state change that belongs to no action (a scripted world event, a
        test). Changes an action causes go through its Consequence instead.
        """
        return self.mutate_entity(
            entity_id,
            {"state": dict(changes)},
            event_type="ENTITY_STATE_CHANGED",
            actor_id=actor_id,
            system_id=system_id,
            source_action_id=source_action_id,
            target_entity_id=entity_id,
            affected_entities=[entity_id],
            data={"changes": dict(changes)},
            tags=["state_change", "world_state_mutation"],
        )

    def is_occupied(self, position: Location) -> bool:
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
            event_id=self.ids.event(),
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
            "resources": self.resources.snapshot(),
        }
