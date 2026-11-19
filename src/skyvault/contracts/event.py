"""Event contract = how one recorded fact is written into event memory."""

from typing import Any

from pydantic import Field, field_validator

from .base import ContractModel, Location, NonEmptyStr, check

EVENT_TYPES = frozenset(
    {
        "ACTION_SELECTED",
        "ACTION_REJECTED",
        "MOVE",
        "ATTACK",
        "MISS",
        "ENTITY_DESTROYED",
        "NO_ACTION",
        "SCENARIO_END",
        "RESOURCE_CHANGED",
        "ENTITY_STATE_CHANGED",
        "OBSERVE",
        "WAIT",
        "REPAIR",
        "SUPPLY",
        "DEPLOY",
        "WITHDRAW",
        "SCAN",
        "COMMUNICATE",
    }
)


class EventSource(ContractModel):
    """Who caused the event: the actor, the system that decided, the action."""

    actor_id: str | None
    system_id: str | None
    action_id: str | None


class EventAffected(ContractModel):
    """What the event touched."""

    entities: list[str] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CausalLinks(ContractModel):
    """Which recorded events led to this one, and which followed it."""

    caused_by: list[str] = Field(default_factory=list)
    caused_events: list[str] = Field(default_factory=list)


class EvaluationRelevance(ContractModel):
    """Whether this event matters to the scenario verdict."""

    affects_success: bool = False
    affects_cost: bool = False
    affects_risk: bool = False


class EventRecord(ContractModel):
    """
    Event = something that actually happened inside the world.

    Important:
    This is the nested shape of Formal Spec section 7.2. target_entity_id and
    data are additions recorded in ADR 002 and kept by ADR 003.

    before_state and after_state have no default. An event without them cannot
    be replayed, so leaving either out is a contract violation.
    """

    event_id: NonEmptyStr
    time: int = Field(ge=0)
    event_type: str
    source: EventSource
    target_entity_id: str | None
    affected: EventAffected
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    causal_links: CausalLinks
    evaluation_relevance: EvaluationRelevance
    data: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {value!r}")
        return value


def validate_event(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one event. Raises ContractError when it breaks the contract."""
    return check(EventRecord, "event", data)
