from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


def new_event_id() -> str:
    return f"event_{uuid4().hex[:10]}"


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
    Every event carries the full Phase 4 shape.
    A field with nothing to report keeps its empty structure instead of
    disappearing, so timeline, replay, entity history and causal chain can read
    every event the same way.
    """

    event_id: str
    time: int
    event_type: str
    actor_id: str | None
    target_entity_id: str | None
    source_action_id: str | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    affected_entities: list[str] = field(default_factory=list)
    affected_locations: list[Any] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
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
            "actor_id": self.actor_id,
            "target_entity_id": self.target_entity_id,
            "source_action_id": self.source_action_id,
            "affected_entities": list(self.affected_entities),
            "affected_locations": list(self.affected_locations),
            "affected_resources": list(self.affected_resources),
            "before_state": dict(self.before_state),
            "after_state": dict(self.after_state),
            "causal_links": build_causal_links(self.causal_links),
            "evaluation_relevance": build_evaluation_relevance(
                self.evaluation_relevance,
            ),
            "data": dict(self.data),
            "tags": list(self.tags),
        }
