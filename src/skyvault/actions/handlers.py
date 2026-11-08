"""Action handlers = what each action type needs, and what it would change.

Important:
Every handler only reads the world. validate() answers whether the action may
happen; resolve() describes what it would change as a Consequence. Neither
records an event or touches an entity: resolver.apply_consequence() does that,
and a test walks this file to make sure nothing here does.
"""

from typing import Any, Protocol

from ..action import Action, location_to_json
from ..consequence import ChainReaction, Consequence, DirectEffect, EvaluationImpact
from ..world_state import WorldState
from .resolver import ActionContext
from .validation import ActionValidation


class ActionHandler(Protocol):
    """One action type: when it is allowed, and what it does."""

    action_type: str

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation: ...

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence: ...


def _capability(entity: Any, name: str, default: float) -> float:
    return float(entity.capabilities.get(name, default))


class MoveHandler:
    """
    move: step to target.location.

    Allowed when the location is inside the space, nobody alive stands there,
    and it is within move_range (default 1) of the actor.
    """

    action_type = "move"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        destination = action.target.location
        if destination is None:
            return ActionValidation.reject("Move action missing target_position")
        if not world.space.is_inside(destination):
            return ActionValidation.reject("Move target outside world boundary")
        if world.is_occupied(destination):
            return ActionValidation.reject("Move target occupied")

        actor = world.get_entity(action.actor_id)
        if actor.position is not None:
            move_range = int(_capability(actor, "move_range", 1))
            distance = world.space.distance(actor.position, destination)
            if distance > move_range:
                return ActionValidation.reject(
                    f"Move target out of range: distance={distance}, range={move_range}"
                )
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        origin = actor.position
        destination = action.target.location

        locations = [location_to_json(origin)] if origin is not None else []
        locations.append(location_to_json(destination))

        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Move resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="MOVE",
                    entity_id=actor.entity_id,
                    changes={"position": destination, "state": {"last_action": "move"}},
                    affected_entities=[actor.entity_id],
                    affected_locations=locations,
                    evaluation_relevance={"affects_cost": True},
                    data={
                        "from": location_to_json(origin),
                        "to": location_to_json(destination),
                    },
                    tags=["movement", "world_state_mutation"],
                )
            ],
            evaluation_impact=EvaluationImpact(cost_delta=1),
        )


class AttackHandler:
    """
    attack: strike target.entity_id.

    Allowed when both sides have a position and the target is within
    attack_range (default 1). The hit roll draws from context.rng: above
    accuracy is a miss, which records MISS and changes nothing. A hit takes
    attack_damage off hp; at hp 0 or below the target is destroyed, recorded
    as an ENTITY_DESTROYED chain reaction of the hit.
    """

    action_type = "attack"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if action.target.entity_id is None:
            return ActionValidation.reject("Attack action missing target_entity_id")

        actor = world.get_entity(action.actor_id)
        target = world.get_entity(action.target.entity_id)

        if actor.position is None or target.position is None:
            return ActionValidation.reject("Actor or target has no position")

        attack_range = int(_capability(actor, "attack_range", 1))
        distance = world.space.distance(actor.position, target.position)
        if distance > attack_range:
            return ActionValidation.reject(
                f"Target out of range: distance={distance}, range={attack_range}"
            )
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(str(action.target.entity_id))
        distance = world.space.distance(actor.position, target.position)
        accuracy = _capability(actor, "accuracy", 1.0)
        damage = int(_capability(actor, "attack_damage", 0))
        locations = [location_to_json(target.position)]

        if context.rng.random() > accuracy:
            return Consequence(
                action_id=action.action_id,
                accepted=True,
                reason="Attack missed",
                effects=[
                    DirectEffect(
                        group="entity",
                        event_type="MISS",
                        entity_id=target.entity_id,
                        target_entity_id=target.entity_id,
                        affected_entities=[actor.entity_id, target.entity_id],
                        affected_locations=locations,
                        evaluation_relevance={"affects_cost": True},
                        data={"accuracy": accuracy, "distance": distance},
                        tags=["attack", "miss"],
                    )
                ],
            )

        hp_before = int(target.state.get("hp", 0))
        hp_after = hp_before - damage
        state: dict[str, Any] = {"hp": hp_after, "last_damage_taken": damage}
        destroyed = hp_after <= 0
        if destroyed:
            state["status"] = "destroyed"

        chain_reactions = []
        if destroyed:
            chain_reactions.append(
                ChainReaction(
                    cause_index=0,
                    effect="ENTITY_DESTROYED",
                    target_entity_id=target.entity_id,
                    affected_entities=[target.entity_id],
                    affected_locations=locations,
                    evaluation_relevance={
                        "affects_success": True,
                        "affects_cost": True,
                        "affects_risk": True,
                    },
                    data={
                        "destroyed_entity": target.entity_id,
                        "faction": target.faction,
                    },
                    tags=["entity_lifecycle", "failure", "state_change"],
                )
            )

        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Attack resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="ATTACK",
                    entity_id=target.entity_id,
                    changes={"state": state},
                    target_entity_id=target.entity_id,
                    affected_entities=[target.entity_id],
                    affected_locations=locations,
                    evaluation_relevance={
                        "affects_success": True,
                        "affects_cost": True,
                    },
                    data={
                        "damage": damage,
                        "hp_before": hp_before,
                        "hp_after": hp_after,
                        "distance": distance,
                    },
                    tags=["attack", "world_state_mutation", "state_change"],
                )
            ],
            chain_reactions=chain_reactions,
            evaluation_impact=EvaluationImpact(tactical_value_delta=damage),
        )


CORE_HANDLERS: dict[str, ActionHandler] = {
    handler.action_type: handler for handler in (MoveHandler(), AttackHandler())
}

# The action types the military line keeps from the start (development plan)
MILITARY_ACTION_TYPES = ("move", "attack", "observe", "supply", "repair")


def handlers_for(action_types: tuple[str, ...]) -> dict[str, ActionHandler]:
    """The core handlers for these action types; unknown names are skipped."""
    return {name: CORE_HANDLERS[name] for name in action_types if name in CORE_HANDLERS}
