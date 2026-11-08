"""Action resolver = the one road from an action to a changed world."""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..action import Action
from ..consequence import ChainReaction, Consequence, DirectEffect
from ..contracts import validate_consequence
from ..event_memory import Event
from ..world_state import WorldState
from .validation import action_cost, check_resources

if TYPE_CHECKING:
    from .handlers import ActionHandler


@dataclass
class ActionContext:
    """
    What a handler may use besides the world.

    rng is the run's only random source for decisions and outcomes; drawing
    from it keeps the run reproducible. system_id is recorded on every event
    as source.system_id.

    fault_rng decides injected faults (rule_set.faults). It is separate so
    that injecting a fault never shifts the draws the battle itself makes;
    without faults it is never drawn from.
    """

    rng: random.Random
    system_id: str | None = None
    fault_rng: random.Random | None = None


class ActionResolver:
    """
    Action Attempt → Validation → Resolution → Consequence → World Mutation →
    Event Memory, for the action types it was given handlers for.

    Important:
    The handlers only read the world. This class applies what they return,
    through apply_consequence(), and nothing else changes the world on an
    action's behalf.
    """

    def __init__(
        self, handlers: Mapping[str, "ActionHandler"], context: ActionContext
    ) -> None:
        self.handlers = dict(handlers)
        self.context = context

    def execute(self, world: WorldState, action: Action) -> Consequence:
        """
        Validate, resolve and apply one action. Returns its Consequence.

        Important:
        A refusal at any step returns a rejected Consequence and leaves the
        world and event memory untouched. The world's charge for the action
        (validation.action_cost) is applied before the handler's own effects,
        one RESOURCE_CHANGED per resource.
        """
        handler = self.handlers.get(action.action_type)
        if handler is None:
            return Consequence.rejected(
                action.action_id, f"Unsupported action type: {action.action_type}"
            )

        actor = world.get_entity(action.actor_id)
        if not actor.is_active():
            return Consequence.rejected(action.action_id, "Actor is not active")

        if self._order_lost(world, actor.faction):
            return Consequence.rejected(
                action.action_id, "Communication failure: order not received"
            )

        validation = handler.validate(world, action, self.context)
        if not validation.valid:
            return Consequence.rejected(action.action_id, validation.reason)

        cost = action_cost(world, action)
        affordable = check_resources(world, cost)
        if not affordable.valid:
            return Consequence.rejected(action.action_id, affordable.reason)

        consequence = handler.resolve(world, action, self.context)
        charges = [
            DirectEffect(
                group="resource",
                event_type="RESOURCE_CHANGED",
                resource_id=resource_id,
                delta=-amount,
            )
            for resource_id, amount in sorted(cost.items())
            if amount > 0
        ]
        if charges:
            consequence.effects[:0] = charges
            for reaction in consequence.chain_reactions:
                reaction.cause_index += len(charges)

        validate_consequence(consequence.to_dict())
        apply_consequence(world, consequence, action, self.context.system_id)
        return consequence

    def _order_lost(self, world: WorldState, faction: str | None) -> bool:
        """
        Whether an injected communication fault swallows this actor's order.

        Important:
        rule_set.faults.drop_actions = {faction, rate} makes each action of
        that faction fail with probability rate, before validation. Failure
        exploration sets it; ordinary scenarios never do, and then nothing is
        drawn from fault_rng at all.
        """
        faults = world.rules.get("faults", {})
        drop = faults.get("drop_actions") if isinstance(faults, dict) else None
        if not drop or drop.get("faction") != faction:
            return False
        rng = self.context.fault_rng or random.Random("faults")
        self.context.fault_rng = rng
        return rng.random() < float(drop.get("rate", 0.0))


def apply_consequence(
    world: WorldState,
    consequence: Consequence,
    action: Action,
    system_id: str | None = None,
) -> list[Event]:
    """
    Carry out an accepted consequence: one event per effect, each chain
    reaction right after the effect that set it off.

    Important:
    This is the only place an action's changes reach the world. Every event it
    records carries the action's id as source.action_id, the actor as
    source.actor_id and system_id as source.system_id.

    A rejected consequence raises: there is nothing to apply, and applying it
    anyway would mean a caller skipped validation. A state effect raises too,
    because the world's environment is not modelled yet.
    """
    if not consequence.accepted:
        raise ValueError(
            f"cannot apply rejected consequence of {consequence.action_id!r}"
        )
    if consequence.action_id != action.action_id:
        raise ValueError("consequence does not belong to this action")

    reactions_by_cause: dict[int, list[ChainReaction]] = {}
    for reaction in consequence.chain_reactions:
        reactions_by_cause.setdefault(reaction.cause_index, []).append(reaction)

    events: list[Event] = []
    for index, effect in enumerate(consequence.effects):
        event = _apply_effect(world, effect, action, system_id)
        events.append(event)

        for reaction in reactions_by_cause.get(index, []):
            chained = world.record_transition(
                event_type=reaction.effect,
                before_state=event.before_state,
                after_state=event.after_state,
                actor_id=action.actor_id,
                system_id=system_id,
                source_action_id=action.action_id,
                target_entity_id=reaction.target_entity_id,
                affected_entities=reaction.affected_entities,
                affected_locations=reaction.affected_locations,
                data=reaction.data,
                tags=reaction.tags,
                evaluation_relevance=reaction.evaluation_relevance,
            )
            reaction.event_id = chained.event_id
            events.append(chained)

    return events


def _apply_effect(
    world: WorldState,
    effect: DirectEffect,
    action: Action,
    system_id: str | None,
) -> Event:
    """One effect, as the world method that records it."""
    if effect.group == "resource":
        if effect.resource_id is None:
            raise ValueError("a resource effect needs resource_id")
        return world.change_resource(
            effect.resource_id,
            effect.delta,
            actor_id=action.actor_id,
            system_id=system_id,
            source_action_id=action.action_id,
            data=effect.data,
        )

    if effect.group == "entity":
        if effect.entity_id is None:
            raise ValueError("an entity effect needs entity_id")
        return world.mutate_entity(
            effect.entity_id,
            effect.changes,
            event_type=effect.event_type,
            actor_id=action.actor_id,
            system_id=system_id,
            source_action_id=action.action_id,
            target_entity_id=effect.target_entity_id,
            affected_entities=effect.affected_entities,
            affected_locations=effect.affected_locations,
            data=effect.data,
            tags=effect.tags,
            evaluation_relevance=effect.evaluation_relevance,
        )

    raise NotImplementedError(
        "state effects change the world environment, which is not modelled yet"
    )
