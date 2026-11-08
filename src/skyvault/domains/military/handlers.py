"""Military action handlers: terrain, cover, suppression, ammunition, morale.

Important:
Like the core handlers they only read the world and return a Consequence;
apply_consequence makes the change. The ATTACK and MISS events keep the
core's data keys (damage, hp_before, hp_after, distance), so the timeline
and every other exporter read them unchanged.
"""

from typing import Any

from ...action import Action, location_to_json
from ...actions import ActionContext, ActionHandler
from ...actions.handlers import SupplyHandler, WaitHandler
from ...actions.validation import ActionValidation
from ...consequence import ChainReaction, Consequence, DirectEffect, EvaluationImpact
from ...world_state import WorldState
from .terrain import cell_of, military_rules, path_cost, terrain_at

ACTION_TYPES = ("move", "attack", "supply", "wait", "rally")


def enemy_cells(world: WorldState, faction: str | None) -> set[Any]:
    """Cells held by living units of any other faction."""
    return {
        unit.position
        for unit in world.active_entities()
        if unit.faction != faction and unit.position is not None
    }


def is_suppressed(world: WorldState, unit: Any) -> bool:
    return int(unit.state.get("suppression", 0)) >= int(
        military_rules(world)["morale"]["suppress_threshold"]
    )


class MilitaryMoveHandler:
    """
    move: go to target.location along a path whose terrain cost fits move_range.

    The destination must be passable and free; enemy-held cells can be
    neither entered nor crossed.
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
        if terrain_at(world, destination)["move_cost"] is None:
            return ActionValidation.reject("Move target is impassable")
        if world.is_occupied(destination):
            return ActionValidation.reject("Move target occupied")
        actor = world.get_entity(action.actor_id)
        if actor.position is None:
            return ActionValidation.reject("Actor has no position")
        budget = int(actor.capabilities.get("move_range", 1))
        cost = path_cost(
            world,
            actor.position,
            destination,
            budget,
            enemy_cells(world, actor.faction),
        )
        if cost is None:
            return ActionValidation.reject(
                f"Move target out of reach: move_range={budget}"
            )
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        origin, destination = cell_of(actor), action.target.location
        if destination is None:  # refused by validate; kept for the type checker
            raise ValueError("move without a destination")
        cost = path_cost(
            world,
            origin,
            destination,
            int(actor.capabilities.get("move_range", 1)),
            enemy_cells(world, actor.faction),
        )
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
                    affected_locations=[
                        location_to_json(origin),
                        location_to_json(destination),
                    ],
                    evaluation_relevance={"affects_cost": True},
                    data={
                        "from": location_to_json(origin),
                        "to": location_to_json(destination),
                        "cost": cost,
                        "terrain": terrain_at(world, destination)["name"],
                    },
                    tags=["movement", "world_state_mutation"],
                )
            ],
            evaluation_impact=EvaluationImpact(cost_delta=1),
        )


class MilitaryAttackHandler:
    """
    attack: fire at target.entity_id with the actor's weapon.

    Allowed with the target in weapon range and ammunition for a shot. The
    chance to hit is accuracy × (1 − cover of the target's cell), halved
    when the shooter is suppressed. A hit takes damage off hp, adds the
    weapon's suppression and costs the target morale; a miss still adds
    half the suppression. Every shot spends ammunition, recorded as an
    ENTITY_STATE_CHANGED of the shooter after the shot.
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
        weapon_range = int(actor.capabilities.get("attack_range", 1))
        distance = world.space.distance(actor.position, target.position)
        if distance > weapon_range:
            return ActionValidation.reject(
                f"Target out of range: distance={int(distance)}, range={weapon_range}"
            )
        if float(actor.state.get("ammo", 0)) < int(
            actor.capabilities.get("ammo_per_shot", 1)
        ):
            return ActionValidation.reject("Out of ammunition")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        target = world.get_entity(str(action.target.entity_id))
        morale = military_rules(world)["morale"]
        cover = float(terrain_at(world, target.position)["cover"])
        accuracy = float(actor.capabilities.get("accuracy", 1.0))
        suppressed = is_suppressed(world, actor)
        chance = round(accuracy * (1 - cover) * (0.5 if suppressed else 1.0), 4)
        distance = world.space.distance(actor.position, target.position)
        locations = [location_to_json(target.position)]
        weapon_suppression = int(actor.capabilities.get("suppression", 0))
        was_suppressed = is_suppressed(world, target)
        hit = context.rng.random() <= chance

        added = weapon_suppression if hit else weapon_suppression // 2
        new_suppression = min(100, int(target.state.get("suppression", 0)) + added)
        morale_loss = int(morale["morale_loss_when_hit"]) if hit else 0
        if not was_suppressed and new_suppression >= int(morale["suppress_threshold"]):
            morale_loss += int(morale["morale_loss_when_suppressed"])
        state: dict[str, Any] = {
            "suppression": new_suppression,
            "morale": max(0, int(target.state.get("morale", 0)) - morale_loss),
        }
        data: dict[str, Any] = {
            "accuracy": accuracy,
            "chance": chance,
            "cover": cover,
            "shooter_suppressed": suppressed,
            "distance": distance,
            "suppression_added": added,
        }
        chain_reactions = []
        if hit:
            damage = int(actor.capabilities.get("attack_damage", 0))
            hp_before = int(target.state.get("hp", 0))
            hp_after = hp_before - damage
            state.update(hp=hp_after, last_damage_taken=damage)
            data.update(damage=damage, hp_before=hp_before, hp_after=hp_after)
            if hp_after <= 0:
                state["status"] = "destroyed"
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

        ammo_before = float(actor.state.get("ammo", 0))
        ammo_after = ammo_before - int(actor.capabilities.get("ammo_per_shot", 1))
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Attack resolved" if hit else "Attack missed",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="ATTACK" if hit else "MISS",
                    entity_id=target.entity_id,
                    changes={"state": state},
                    target_entity_id=target.entity_id,
                    affected_entities=[actor.entity_id, target.entity_id],
                    affected_locations=locations,
                    evaluation_relevance={
                        "affects_success": hit,
                        "affects_cost": True,
                        "affects_risk": True,
                    },
                    data=data,
                    tags=["attack", "hit" if hit else "miss", "suppression"],
                ),
                DirectEffect(
                    group="entity",
                    event_type="ENTITY_STATE_CHANGED",
                    entity_id=actor.entity_id,
                    changes={"state": {"ammo": ammo_after, "last_action": "attack"}},
                    affected_entities=[actor.entity_id],
                    evaluation_relevance={"affects_cost": True},
                    data={
                        "changes": {"ammo": [ammo_before, ammo_after]},
                        "reason": "shot fired",
                    },
                    tags=["ammunition"],
                ),
            ],
            chain_reactions=chain_reactions,
            evaluation_impact=EvaluationImpact(
                tactical_value_delta=int(data.get("damage", 0))
            ),
        )


class RallyHandler:
    """
    rally: the start-of-tick recovery the pack issues for a shaken unit.

    Suppression falls by suppression_decay and morale rises by rally, up to
    the starting morale. Refused when there is nothing to recover.
    """

    action_type = "rally"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        unit = world.get_entity(action.actor_id)
        start = int(military_rules(world)["morale"]["start"])
        if int(unit.state.get("suppression", 0)) <= 0 and (
            int(unit.state.get("morale", start)) >= start
        ):
            return ActionValidation.reject("Nothing to recover")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        unit = world.get_entity(action.actor_id)
        morale = military_rules(world)["morale"]
        before = {
            "suppression": int(unit.state.get("suppression", 0)),
            "morale": int(unit.state.get("morale", morale["start"])),
        }
        after = {
            "suppression": max(
                0, before["suppression"] - int(morale["suppression_decay"])
            ),
            "morale": min(
                int(morale["start"]), before["morale"] + int(morale["rally"])
            ),
        }
        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Rally resolved",
            effects=[
                DirectEffect(
                    group="entity",
                    event_type="ENTITY_STATE_CHANGED",
                    entity_id=unit.entity_id,
                    changes={"state": after},
                    affected_entities=[unit.entity_id],
                    data={
                        "changes": {key: [before[key], after[key]] for key in after},
                        "reason": "rally",
                    },
                    tags=["morale", "recovery"],
                )
            ],
        )


def military_handlers() -> dict[str, ActionHandler]:
    """The pack's handlers by action type; supply and wait are the core's."""
    return {
        "move": MilitaryMoveHandler(),
        "attack": MilitaryAttackHandler(),
        "supply": SupplyHandler(),
        "wait": WaitHandler(),
        "rally": RallyHandler(),
    }
