from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


def new_event_id() -> str:
    return f"event_{uuid4().hex[:10]}"


@dataclass
class Event:
    """
    Event = something that actually happened inside the world.

    Action is an attempt.
    Event is a recorded fact.
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
    affected_locations: list[list[int]] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    causal_links: dict[str, list[str]] = field(default_factory=lambda: {"caused_by": [], "caused_events": []})
    evaluation_relevance: dict[str, bool] = field(default_factory=lambda: {"affects_success": False, "affects_cost": False, "affects_risk": False})
    data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "time": self.time,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "target_entity_id": self.target_entity_id,
            "source_action_id": self.source_action_id,
            "affected_entities": self.affected_entities,
            "affected_locations": self.affected_locations,
            "affected_resources": self.affected_resources,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "causal_links": self.causal_links,
            "evaluation_relevance": self.evaluation_relevance,
            "data": self.data,
            "tags": self.tags,
        }