"""Action handlers = what each action type needs, and what it would change.

Important:
Every handler only reads the world. validate() answers whether the action may
happen; resolve() describes what it would change as a Consequence. Neither
records an event or touches an entity: resolver.apply_consequence() does that,
and a test walks this file to make sure nothing here does.
"""

from typing import Any, Protocol

from ..action import Action, location_to_json
from ..consequence import (
    ChainReaction,
    Consequence,
    DirectEffect,
    EvaluationImpact,
    SecondaryEffects,
)
from ..world_state import WorldState
from .resolver import ActionContext
from .validation import ActionValidation, action_cost


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


def _number(value: float) -> float | int:
    """A distance or range as a message shows it: 2, not 2.0."""
    return int(value) if float(value).is_integer() else value


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
                    f"Move target out of range: distance={_number(distance)}, "
                    f"range={move_range}"
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
                f"Target out of range: distance={_number(distance)}, "
                f"range={attack_range}"
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


def _within(
    world: WorldState, a: Any, b: Any, limit: float, what: str
) -> ActionValidation:
    """Refuse unless both have a position and are at most limit apart."""
    if a.position is None or b.position is None:
        return ActionValidation.reject("Actor or target has no position")
    distance = world.space.distance(a.position, b.position)
    if distance > limit:
        return ActionValidation.reject(
            f"{what} out of range: distance={_number(distance)}, "
            f"range={_number(limit)}"
        )
    return ActionValidation.ok()


def _record_only(
    action: Action,
    reason: str,
    event_type: str,
    entity_id: str,
    **event: Any,
) -> Consequence:
    """An accepted action whose one event changes nothing."""
    return Consequence(
        action_id=action.action_id,
        accepted=True,
        reason=reason,
        effects=[
            DirectEffect(
                group="entity", event_type=event_type, entity_id=entity_id, **event
            )
        ],
    )


class ObserveHandler:
    """
    observe: look at target.entity_id.

    Allowed within observe_range (default 1). Changes nothing; the OBSERVE
    event carries a copy of the target's state as it was seen.
    """

    action_type = "observe"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if action.target.entity_id is None:
            return ActionValidation.reject("Observe action missing target_entity_id")
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(action.target.entity_id)
        limit = _capability(actor, "observe_range", 1)
        return _within(world, actor, target, limit, "Observe target")

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(str(action.target.entity_id))
        return _record_only(
            action,
            "Observation resolved",
            "OBSERVE",
            target.entity_id,
            target_entity_id=target.entity_id,
            affected_entities=[actor.entity_id, target.entity_id],
            affected_locations=[location_to_json(target.position)],
            data={
                "observed_entity": target.entity_id,
                "distance": world.space.distance(actor.position, target.position),
                "observed_state": dict(target.state),
            },
            tags=["observation"],
        )


class ScanHandler:
    """
    scan: sweep the area around the actor.

    Allowed when the actor has a position. Changes nothing; the SCAN event
    lists every other living entity within scan_range (default 1).
    """

    action_type = "scan"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if world.get_entity(action.actor_id).position is None:
            return ActionValidation.reject("Actor has no position")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        scan_range = _capability(actor, "scan_range", 1)
        detected = sorted(
            entity.entity_id
            for entity in world.active_entities()
            if entity.entity_id != actor.entity_id
            and entity.position is not None
            and world.space.distance(actor.position, entity.position) <= scan_range
        )
        return _record_only(
            action,
            "Scan resolved",
            "SCAN",
            actor.entity_id,
            affected_entities=[actor.entity_id, *detected],
            affected_locations=[location_to_json(actor.position)],
            data={"detected": detected, "scan_range": scan_range},
            tags=["observation", "scan"],
        )


class WaitHandler:
    """wait: do nothing this turn. Always allowed; the WAIT event changes nothing."""

    action_type = "wait"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        return _record_only(
            action,
            "Wait resolved",
            "WAIT",
            action.actor_id,
            affected_entities=[action.actor_id],
            tags=["wait"],
        )


class RepairHandler:
    """
    repair: restore hp to target.entity_id, or to the actor when no target.

    Allowed when the actor has repair_amount > 0, the target is alive, has hp,
    is not already at max_hp, and (if it is someone else) is within
    repair_range (default 1). hp rises by repair_amount, capped at max_hp.
    """

    action_type = "repair"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if _capability(actor, "repair_amount", 0) <= 0:
            return ActionValidation.reject("Actor cannot repair")

        target = world.get_entity(action.target.entity_id or actor.entity_id)
        if not target.is_active():
            return ActionValidation.reject("Repair target is not active")
        if "hp" not in target.state:
            return ActionValidation.reject("Repair target has no hp")
        if "max_hp" in target.state and target.state["hp"] >= target.state["max_hp"]:
            return ActionValidation.reject("Repair target already at full health")
        if target is not actor:
            limit = _capability(actor, "repair_range", 1)
            return _within(world, actor, target, limit, "Repair target")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(action.target.entity_id or actor.entity_id)
        hp_before = target.state["hp"]
        hp_after = hp_before + int(_capability(actor, "repair_amount", 0))
        if "max_hp" in target.state:
            hp_after = min(hp_after, target.state["max_hp"])

        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Repair resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="REPAIR",
                    entity_id=target.entity_id,
                    changes={
                        "state": {"hp": hp_after, "last_repaired_by": actor.entity_id}
                    },
                    target_entity_id=target.entity_id,
                    affected_entities=[target.entity_id],
                    data={
                        "hp_before": hp_before,
                        "hp_after": hp_after,
                        "repaired_by": actor.entity_id,
                    },
                    tags=["repair", "world_state_mutation", "state_change"],
                )
            ],
        )


class SupplyHandler:
    """
    supply: deliver resources to target.entity_id.

    What is delivered is what the world charges for the action
    (validation.action_cost): the world's stock goes down by it, before this
    effect, and the target's state goes up by it. Allowed when that is not
    empty, the target is alive and within supply_range (default 1).
    """

    action_type = "supply"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if action.target.entity_id is None:
            return ActionValidation.reject("Supply action missing target_entity_id")
        if not action_cost(world, action):
            return ActionValidation.reject("Supply action carries no resources")
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(action.target.entity_id)
        if not target.is_active():
            return ActionValidation.reject("Supply target is not active")
        limit = _capability(actor, "supply_range", 1)
        return _within(world, actor, target, limit, "Supply target")

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        target = world.get_entity(str(action.target.entity_id))
        cargo = action_cost(world, action)
        stocked = {
            resource_id: float(target.state.get(resource_id, 0)) + amount
            for resource_id, amount in sorted(cargo.items())
        }
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Supply resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="SUPPLY",
                    entity_id=target.entity_id,
                    changes={"state": stocked},
                    target_entity_id=target.entity_id,
                    affected_entities=[action.actor_id, target.entity_id],
                    data={"delivered": cargo},
                    tags=["supply", "world_state_mutation", "state_change"],
                )
            ],
            secondary_effects=SecondaryEffects(
                logistical_changes=[
                    {"entity_id": target.entity_id, "delivered": dict(cargo)}
                ]
            ),
        )


class DeployHandler:
    """
    deploy: bring a reserve unit (target.entity_id) onto target.location.

    Allowed when the unit is in reserve and on the actor's side, and the
    location is inside the space, free, and within deploy_range (default 1)
    of the actor. The unit takes the location and becomes active.
    """

    action_type = "deploy"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if action.target.entity_id is None:
            return ActionValidation.reject("Deploy action missing target_entity_id")
        destination = action.target.location
        if destination is None:
            return ActionValidation.reject("Deploy action missing target location")

        actor = world.get_entity(action.actor_id)
        unit = world.get_entity(action.target.entity_id)
        if unit.state.get("status") != "reserve":
            return ActionValidation.reject("Deploy target is not in reserve")
        if unit.faction != actor.faction:
            return ActionValidation.reject("Deploy target belongs to another faction")
        if not world.space.is_inside(destination):
            return ActionValidation.reject("Deploy location outside world boundary")
        if world.is_occupied(destination):
            return ActionValidation.reject("Deploy location occupied")
        if actor.position is None:
            return ActionValidation.reject("Actor has no position")

        deploy_range = _capability(actor, "deploy_range", 1)
        distance = world.space.distance(actor.position, destination)
        if distance > deploy_range:
            return ActionValidation.reject(
                f"Deploy location out of range: distance={_number(distance)}, "
                f"range={_number(deploy_range)}"
            )
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        unit = world.get_entity(str(action.target.entity_id))
        destination = action.target.location
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Deploy resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="DEPLOY",
                    entity_id=unit.entity_id,
                    changes={"position": destination, "state": {"status": "active"}},
                    target_entity_id=unit.entity_id,
                    affected_entities=[action.actor_id, unit.entity_id],
                    affected_locations=[location_to_json(destination)],
                    data={"to": location_to_json(destination)},
                    tags=["deployment", "world_state_mutation"],
                )
            ],
        )


class WithdrawHandler:
    """
    withdraw: take target.entity_id, or the actor, off the field.

    Allowed when the unit is alive and on the actor's side. It loses its
    position and its status becomes withdrawn; it stays in the registry.
    """

    action_type = "withdraw"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        unit = world.get_entity(action.target.entity_id or actor.entity_id)
        if not unit.is_active():
            return ActionValidation.reject("Withdraw target is not active")
        if unit.faction != actor.faction:
            return ActionValidation.reject("Withdraw target belongs to another faction")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        unit = world.get_entity(action.target.entity_id or action.actor_id)
        origin = location_to_json(unit.position)
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Withdraw resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="WITHDRAW",
                    entity_id=unit.entity_id,
                    changes={"position": None, "state": {"status": "withdrawn"}},
                    target_entity_id=unit.entity_id,
                    affected_entities=[unit.entity_id],
                    affected_locations=[origin] if origin is not None else [],
                    data={"from": origin},
                    tags=["withdrawal", "world_state_mutation"],
                )
            ],
        )


class CommunicateHandler:
    """
    communicate: send a message to target.entity_id.

    Allowed when the target is alive and, if the actor has comm_range, within
    it. The message is metadata["message"], or the intent when there is none;
    the target's state records it and who sent it.
    """

    action_type = "communicate"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        if action.target.entity_id is None:
            return ActionValidation.reject(
                "Communicate action missing target_entity_id"
            )
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(action.target.entity_id)
        if not target.is_active():
            return ActionValidation.reject("Communicate target is not active")
        if "comm_range" in actor.capabilities:
            limit = _capability(actor, "comm_range", 0)
            return _within(world, actor, target, limit, "Communicate target")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        target = world.get_entity(str(action.target.entity_id))
        message = str(action.metadata.get("message", action.intent))
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Communicate resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="COMMUNICATE",
                    entity_id=target.entity_id,
                    changes={
                        "state": {
                            "last_message": message,
                            "last_message_from": action.actor_id,
                        }
                    },
                    target_entity_id=target.entity_id,
                    affected_entities=[action.actor_id, target.entity_id],
                    data={"message": message},
                    tags=["communication", "state_change"],
                )
            ],
        )


CORE_HANDLERS: dict[str, ActionHandler] = {
    handler.action_type: handler
    for handler in (
        MoveHandler(),
        AttackHandler(),
        ObserveHandler(),
        WaitHandler(),
        RepairHandler(),
        SupplyHandler(),
        DeployHandler(),
        WithdrawHandler(),
        ScanHandler(),
        CommunicateHandler(),
    )
}

# The action types the military line keeps from the start (development plan)
MILITARY_ACTION_TYPES = ("move", "attack", "observe", "supply", "repair")


def handlers_for(action_types: tuple[str, ...]) -> dict[str, ActionHandler]:
    """The core handlers for these action types; unknown names are skipped."""
    return {name: CORE_HANDLERS[name] for name in action_types if name in CORE_HANDLERS}
