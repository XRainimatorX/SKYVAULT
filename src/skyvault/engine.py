import random
from typing import Any

from .action import Action
from .consequence import Consequence
from .entity import Entity
from .evaluator import build_evaluation_summary
from .tactical_reference_policy import TacticalReferencePolicy
from .world_state import SpaceModel, WorldState


ENGINE_SYSTEM_ID = "skyvault_tactical_reference_engine"


class SkyVaultTacticalReferenceEngine:
    """
    First executable SKYVAULT-style tactical reference slice.

    This is not the final SKYVAULT engine.

    It exists to prove:

    Scenario
    → World State
    → Actor Policy
    → Action
    → Validation
    → Consequence
    → World State Mutation
    → Event Memory
    → Evaluation Result
    """

    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario

        runtime = scenario["runtime"]
        random_seed = runtime.get("random_seed")

        self.rng = random.Random(random_seed)
        self.world = self.build_world(scenario)
        self.policy = TacticalReferencePolicy(self.rng)

        assumptions = scenario["world_contract"].get("assumption_registry", {})

        self.actor_system_id = assumptions.get(
            "actor_policy",
            type(self.policy).__name__,
        )

    def build_world(self, scenario: dict[str, Any]) -> WorldState:
        world_contract = scenario["world_contract"]
        space_model = world_contract["space_model"]

        space = SpaceModel(
            width=int(space_model["width"]),
            height=int(space_model["height"]),
            distance_model=space_model.get("distance_model", "chebyshev"),
        )

        entities: dict[str, Entity] = {}

        for item in scenario["entities"]:
            position = item.get("position")
            parsed_position = tuple(position) if position is not None else None

            entity = Entity(
                entity_id=item["entity_id"],
                name=item["name"],
                entity_type=item["entity_type"],
                faction=item.get("faction"),
                position=parsed_position,
                state=dict(item.get("state", {})),
                capabilities=dict(item.get("capabilities", {})),
                tags=list(item.get("tags", [])),
            )

            entities[entity.entity_id] = entity

        return WorldState(
            world_id=world_contract["world_id"],
            scenario_id=scenario["scenario_id"],
            tick=0,
            space=space,
            entities=entities,
            assumptions=world_contract.get("assumption_registry", {}),
        )

    def run(self) -> dict[str, Any]:
        max_ticks = int(self.scenario["runtime"].get("max_ticks", 10))
        termination_reason = "duration_limit_reached"

        initial_world_state = self.world.snapshot()

        for tick in range(1, max_ticks + 1):
            self.world.tick = tick

            if len(self.world.active_factions()) <= 1:
                termination_reason = "termination_condition_met"
                break

            actors = list(self.world.active_entities())

            for actor in actors:
                if not actor.is_active():
                    continue

                action = self.policy.decide_action(self.world, actor)

                if action is None:
                    self.world.record_event(
                        event_type="NO_ACTION",
                        actor_id=actor.entity_id,
                        system_id=self.actor_system_id,
                        target_entity_id=None,
                        source_action_id=None,
                        before_state=actor.snapshot(),
                        after_state=actor.snapshot(),
                        affected_entities=[actor.entity_id],
                        data={"reason": "policy_returned_no_action"},
                        tags=["no_action"],
                    )
                    continue

                action_entities = [actor.entity_id]

                if action.target_entity_id is not None:
                    action_entities.append(action.target_entity_id)

                self.world.record_event(
                    event_type="ACTION_SELECTED",
                    actor_id=actor.entity_id,
                    system_id=self.actor_system_id,
                    target_entity_id=action.target_entity_id,
                    source_action_id=action.action_id,
                    before_state=actor.snapshot(),
                    after_state=actor.snapshot(),
                    affected_entities=action_entities,
                    data={
                        "action_type": action.action_type,
                        "intent": action.intent,
                        "target_position": list(action.target_position)
                        if action.target_position
                        else None,
                    },
                    tags=["action_selection"],
                )

                consequence = self.resolve_action(action)

                if not consequence.accepted:
                    self.world.record_event(
                        event_type="ACTION_REJECTED",
                        actor_id=action.actor_id,
                        system_id=self.actor_system_id,
                        target_entity_id=action.target_entity_id,
                        source_action_id=action.action_id,
                        before_state={},
                        after_state={},
                        affected_entities=action_entities,
                        data={
                            "reason": consequence.reason,
                            "action_type": action.action_type,
                        },
                        tags=["action_rejected"],
                    )

                if len(self.world.active_factions()) <= 1:
                    termination_reason = "termination_condition_met"
                    break

            if termination_reason == "termination_condition_met":
                break

        total_events = len(self.world.event_memory) + 1

        evaluation = self.evaluate(termination_reason, total_events)

        self.world.record_event(
            event_type="SCENARIO_END",
            actor_id=None,
            system_id=ENGINE_SYSTEM_ID,
            target_entity_id=None,
            source_action_id=None,
            before_state={},
            after_state=self.world.snapshot(),
            affected_entities=sorted(self.world.entities),
            evaluation_relevance={"affects_success": True},
            data=evaluation,
            tags=["scenario_end"],
        )

        return {
            "scenario_id": self.scenario["scenario_id"],
            "scenario_version": self.scenario["scenario_version"],
            "initial_world_state": initial_world_state,
            "final_world_state": self.world.snapshot(),
            "event_memory": [
                event.to_dict()
                for event in self.world.event_memory
            ],
            "evaluation": evaluation,
        }

    def resolve_action(self, action: Action) -> Consequence:
        if action.action_type == "move":
            return self.resolve_move(action)

        if action.action_type == "attack":
            return self.resolve_attack(action)

        return Consequence(
            action_id=action.action_id,
            accepted=False,
            reason=f"Unsupported action type: {action.action_type}",
        )

    def resolve_move(self, action: Action) -> Consequence:
        actor = self.world.get_entity(action.actor_id)

        if action.target_position is None:
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason="Move action missing target_position",
            )

        if not self.world.space.is_inside(action.target_position):
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason="Move target outside world boundary",
            )

        if self.world.is_occupied(action.target_position):
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason="Move target occupied",
            )

        before = actor.snapshot()
        old_position = actor.position

        actor.position = action.target_position
        actor.state["last_action"] = "move"

        after = actor.snapshot()

        move_locations = []

        if old_position is not None:
            move_locations.append(list(old_position))

        move_locations.append(list(action.target_position))

        self.world.record_event(
            event_type="MOVE",
            actor_id=actor.entity_id,
            system_id=self.actor_system_id,
            target_entity_id=None,
            source_action_id=action.action_id,
            before_state=before,
            after_state=after,
            affected_entities=[actor.entity_id],
            affected_locations=move_locations,
            evaluation_relevance={"affects_cost": True},
            data={
                "from": list(old_position) if old_position else None,
                "to": list(action.target_position),
            },
            tags=["movement", "world_state_mutation"],
        )

        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Move resolved",
            direct_effects=[
                {
                    "type": "position_change",
                    "entity_id": actor.entity_id,
                    "from": old_position,
                    "to": action.target_position,
                }
            ],
            evaluation_impact={"time_cost": 1},
        )

    def resolve_attack(self, action: Action) -> Consequence:
        actor = self.world.get_entity(action.actor_id)

        if action.target_entity_id is None:
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason="Attack action missing target_entity_id",
            )

        target = self.world.get_entity(action.target_entity_id)

        if actor.position is None or target.position is None:
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason="Actor or target has no position",
            )

        attack_range = int(actor.capabilities.get("attack_range", 1))
        distance = self.world.space.distance(actor.position, target.position)

        if distance > attack_range:
            return Consequence(
                action_id=action.action_id,
                accepted=False,
                reason=f"Target out of range: distance={distance}, range={attack_range}",
            )

        accuracy = float(actor.capabilities.get("accuracy", 1.0))
        damage = int(actor.capabilities.get("attack_damage", 0))

        before = target.snapshot()
        target_locations = [list(target.position)]

        if self.rng.random() > accuracy:
            self.world.record_event(
                event_type="MISS",
                actor_id=actor.entity_id,
                system_id=self.actor_system_id,
                target_entity_id=target.entity_id,
                source_action_id=action.action_id,
                before_state=before,
                after_state=target.snapshot(),
                affected_entities=[actor.entity_id, target.entity_id],
                affected_locations=target_locations,
                evaluation_relevance={"affects_cost": True},
                data={
                    "accuracy": accuracy,
                    "distance": distance,
                },
                tags=["attack", "miss"],
            )

            return Consequence(
                action_id=action.action_id,
                accepted=True,
                reason="Attack missed",
                direct_effects=[
                    {
                        "type": "miss",
                        "actor_id": actor.entity_id,
                        "target_entity_id": target.entity_id,
                    }
                ],
            )

        hp_before = int(target.state.get("hp", 0))
        hp_after = hp_before - damage

        target.state["hp"] = hp_after
        target.state["last_damage_taken"] = damage

        if hp_after <= 0:
            target.state["status"] = "destroyed"

        after = target.snapshot()

        self.world.record_event(
            event_type="ATTACK",
            actor_id=actor.entity_id,
            system_id=self.actor_system_id,
            target_entity_id=target.entity_id,
            source_action_id=action.action_id,
            before_state=before,
            after_state=after,
            affected_entities=[target.entity_id],
            affected_locations=target_locations,
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

        direct_effects = [
            {
                "type": "hp_change",
                "entity_id": target.entity_id,
                "from": hp_before,
                "to": hp_after,
            }
        ]

        if target.state.get("status") == "destroyed":
            self.world.record_event(
                event_type="ENTITY_DESTROYED",
                actor_id=actor.entity_id,
                system_id=self.actor_system_id,
                target_entity_id=target.entity_id,
                source_action_id=action.action_id,
                before_state=before,
                after_state=after,
                affected_entities=[target.entity_id],
                affected_locations=target_locations,
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

            direct_effects.append(
                {
                    "type": "status_change",
                    "entity_id": target.entity_id,
                    "to": "destroyed",
                }
            )

        return Consequence(
            action_id=action.action_id,
            accepted=True,
            reason="Attack resolved",
            direct_effects=direct_effects,
            evaluation_impact={"damage_done": damage},
        )

    def evaluate(self, termination_reason: str, event_count: int) -> dict[str, Any]:
        return build_evaluation_summary(self.world, termination_reason, event_count)
