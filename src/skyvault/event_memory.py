"""Event memory = the immutable record of everything the world did."""

from dataclasses import dataclass, field
from typing import Any


def build_causal_links(
    source: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """
    causal_links = which recorded events led to this one, and which followed it.

    Important:
    Missing keys are filled with empty lists, so every event carries the same
    shape even when nothing has been linked to it yet.
    """
    source = source or {}

    return {
        "caused_by": list(source.get("caused_by", [])),
        "caused_events": list(source.get("caused_events", [])),
    }


def build_evaluation_relevance(
    source: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """
    evaluation_relevance = whether this event matters to the scenario verdict.

    Important:
    This only marks relevance. It does not score, weigh or rank anything.
    """
    source = source or {}

    return {
        "affects_success": bool(source.get("affects_success", False)),
        "affects_cost": bool(source.get("affects_cost", False)),
        "affects_risk": bool(source.get("affects_risk", False)),
    }


@dataclass
class Event:
    """
    Event = something that actually happened inside the world.

    Action is an attempt.
    Event is a recorded fact.

    Important:
    The attributes here are flat for the engine's convenience. to_dict() writes
    the nested shape of Formal Spec section 7.2 (source / affected), which is
    what event memory stores and what the event contract checks. See ADR 003.

    A field with nothing to report keeps its empty structure instead of
    disappearing, so timeline, replay, entity history and causal chain can read
    every event the same way.
    """

    event_id: str
    time: int
    event_type: str
    actor_id: str | None
    system_id: str | None
    target_entity_id: str | None
    source_action_id: str | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    affected_entities: list[str] = field(default_factory=list)
    affected_locations: list[Any] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    affected_risks: list[str] = field(default_factory=list)
    causal_links: dict[str, list[str]] = field(default_factory=build_causal_links)
    evaluation_relevance: dict[str, bool] = field(
        default_factory=build_evaluation_relevance,
    )
    data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Important:
        Every mutable container is copied on the way out.

        Derived outputs read event memory. They must never be able to mutate it.
        """
        return {
            "event_id": self.event_id,
            "time": self.time,
            "event_type": self.event_type,
            "source": {
                "actor_id": self.actor_id,
                "system_id": self.system_id,
                "action_id": self.source_action_id,
            },
            "target_entity_id": self.target_entity_id,
            "affected": {
                "entities": list(self.affected_entities),
                # A grid cell becomes a list; a node id stays a string
                "locations": [
                    location if isinstance(location, str) else list(location)
                    for location in self.affected_locations
                ],
                "resources": list(self.affected_resources),
                "risks": list(self.affected_risks),
            },
            "before_state": dict(self.before_state),
            "after_state": dict(self.after_state),
            "causal_links": build_causal_links(self.causal_links),
            "evaluation_relevance": build_evaluation_relevance(
                self.evaluation_relevance,
            ),
            "data": dict(self.data),
            "tags": list(self.tags),
        }
