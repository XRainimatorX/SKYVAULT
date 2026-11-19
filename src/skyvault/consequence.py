"""Consequence = what an accepted action will change in the world."""

from dataclasses import dataclass, field
from typing import Any, Literal

EffectGroup = Literal["entity", "resource", "state"]

# Contract key for each effect group, in Formal Spec section 6 order
GROUP_KEYS: dict[str, str] = {
    "state": "state_changes",
    "resource": "resource_changes",
    "entity": "entity_changes",
}


@dataclass
class DirectEffect:
    """
    One change the consequence makes, and the event that records it.

    Important:
    group says what changes:

    entity     changes may hold "position" and "state" (keys to set). Empty
               changes is allowed: the event is recorded, nothing changes
               (a miss, an observation, a wait).
    resource   resource_id changes by delta.
    state      the world's environment. Not modelled yet; applying one raises.

    The remaining fields are the event this effect is recorded as. Effects are
    applied in list order, so their order is the order of the events.
    """

    group: EffectGroup
    event_type: str
    entity_id: str | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    resource_id: str | None = None
    delta: float = 0.0
    target_entity_id: str | None = None
    affected_entities: list[str] = field(default_factory=list)
    affected_locations: list[Any] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    evaluation_relevance: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """The effect as the consequence contract lists it."""
        if self.group == "resource":
            return {
                "resource_id": self.resource_id,
                "delta": self.delta,
                "event_type": self.event_type,
            }
        return {
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "changes": _json_safe(self.changes),
        }


@dataclass
class ChainReaction:
    """
    A further event one effect sets off, recorded right after it.

    Important:
    It changes nothing by itself. Its event carries the same before and after
    as the effect at cause_index, because it describes the same transition
    from another angle: the hit that took hp to zero is also the destruction.

    event_id is None until the consequence is applied.
    """

    cause_index: int
    effect: str
    target_entity_id: str | None = None
    affected_entities: list[str] = field(default_factory=list)
    affected_locations: list[Any] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    evaluation_relevance: dict[str, bool] = field(default_factory=dict)
    event_id: str | None = None


@dataclass
class SecondaryEffects:
    """
    Wider effects of an action, Formal Spec section 6.

    Important:
    These are descriptive records only. No risk, stability or public order
    model exists yet (Phase 7 and 9), so nothing here changes the world.
    """

    risk_changes: list[dict[str, Any]] = field(default_factory=list)
    stability_changes: list[dict[str, Any]] = field(default_factory=list)
    public_order_changes: list[dict[str, Any]] = field(default_factory=list)
    logistical_changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvaluationImpact:
    """How an action moves the verdict. Recorded now, scored from Phase 7."""

    cost_delta: float = 0
    risk_delta: float = 0
    stability_delta: float = 0
    tactical_value_delta: float = 0
    strategic_value_delta: float = 0


@dataclass
class Consequence:
    """
    Consequence = what resolving an action will do to the world.

    Important:
    This is a plan, not a record. A resolver builds it by reading the world;
    actions.resolver.apply_consequence() is the only thing that carries it
    out, one event per effect and per chain reaction.

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
    effects: list[DirectEffect] = field(default_factory=list)
    secondary_effects: SecondaryEffects = field(default_factory=SecondaryEffects)
    chain_reactions: list[ChainReaction] = field(default_factory=list)
    evaluation_impact: EvaluationImpact = field(default_factory=EvaluationImpact)

    @classmethod
    def rejected(cls, action_id: str, reason: str) -> "Consequence":
        """A refusal: nothing will change."""
        return cls(action_id=action_id, accepted=False, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        """The consequence in its contract shape, effects grouped in order."""
        direct_effects: dict[str, list[dict[str, Any]]] = {
            key: [] for key in GROUP_KEYS.values()
        }
        for effect in self.effects:
            direct_effects[GROUP_KEYS[effect.group]].append(effect.to_dict())

        secondary = self.secondary_effects
        impact = self.evaluation_impact

        return {
            "action_id": self.action_id,
            "accepted": self.accepted,
            "reason": self.reason,
            "direct_effects": direct_effects,
            "secondary_effects": {
                "risk_changes": list(secondary.risk_changes),
                "stability_changes": list(secondary.stability_changes),
                "public_order_changes": list(secondary.public_order_changes),
                "logistical_changes": list(secondary.logistical_changes),
            },
            "chain_reactions": [
                {
                    "event_id": reaction.event_id,
                    "cause": self._cause_label(reaction),
                    "effect": reaction.effect,
                }
                for reaction in self.chain_reactions
            ],
            "evaluation_impact": {
                "cost_delta": impact.cost_delta,
                "risk_delta": impact.risk_delta,
                "stability_delta": impact.stability_delta,
                "tactical_value_delta": impact.tactical_value_delta,
                "strategic_value_delta": impact.strategic_value_delta,
            },
        }

    def _cause_label(self, reaction: ChainReaction) -> str:
        """ "<event type>:<entity or resource>" of the effect that set it off."""
        cause = self.effects[reaction.cause_index]
        subject = cause.entity_id or cause.resource_id or "world"
        return f"{cause.event_type}:{subject}"


def _json_safe(value: Any) -> Any:
    """Tuples become lists, recursively, so the result is JSON-shaped."""
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value
