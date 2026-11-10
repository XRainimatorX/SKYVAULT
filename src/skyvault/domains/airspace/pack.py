"""AIRSPACE = the airspace domain pack as the engine sees it (Phase 15)."""

import random
from typing import Any

from ...action import Action, ActionTarget
from ...actions import ActionHandler
from ...world_state import WorldState
from .failures import airspace_failure_variables
from .handlers import ACTION_TYPES, airspace_handlers, command_of, of_type
from .model import distance
from .policy import AirDefencePolicy


class AirspacePack:
    """
    A 2D airspace run until every threat is dealt with.

    Important:
    Threats wait in reserve before their wave, so THREAT may have no active
    unit at the start: the run does not end on one faction left
    (ends_with_last_faction False). It ends when no threat is in reserve or
    in the air (finished → "threats_resolved") or at its time limit.
    """

    name = "airspace"
    action_types = ACTION_TYPES
    spaces = ("grid",)
    ends_with_last_faction = False
    end_reasons = ("threats_resolved",)

    def handlers(self) -> dict[str, ActionHandler]:
        return airspace_handlers()

    def default_policy(
        self, scenario: dict[str, Any], rng: random.Random
    ) -> AirDefencePolicy:
        return AirDefencePolicy()

    def acts(self, entity: Any, world: Any = None) -> bool:
        """
        Drones decide every tick. An interceptor decides only when it has an
        opportunity: ammunition, ready to fire, and a cleared track taken for
        a threat within its range. Holding fire then is a choice (a recorded
        turn); waiting with nothing to fire at is not a turn at all — so an
        air defence that waits for its targets is not "inaction". The sky,
        sensors and assets never decide.
        """
        if entity.entity_type == "drone":
            return True
        if entity.entity_type != "interceptor" or world is None:
            return False
        if int(entity.state["ammo"]) <= 0 or world.tick < int(entity.state["ready_at"]):
            return False
        reach = float(entity.capabilities["range"])
        return any(
            t["identified"] == "threat"
            and world.tick >= int(t["engageable_from"])
            and distance(entity.position, t["position"]) <= reach
            for t in command_of(world).state["tracks"].values()
        )

    def upkeep(self, world: WorldState) -> list[Action]:
        """Launches, then every threat's flight, then the sensors."""

        def action(
            actor_id: str, action_type: str, target: str | None = None
        ) -> Action:
            return Action(
                action_id=world.ids.action(),
                actor_id=actor_id,
                action_type=action_type,
                target=ActionTarget(entity_id=target or actor_id),
                intent=f"airspace_{action_type}",
                expected_effect=f"airspace:{action_type}",
            )

        threats = of_type(world, "threat")
        node = command_of(world).entity_id
        actions = [
            action(node, "launch", t.entity_id)
            for t in threats
            if t.state["status"] == "reserve"
            and int(t.state["launch_tick"]) == world.tick
        ]
        launching = {a.target.entity_id for a in actions}
        actions += [
            action(t.entity_id, "fly")
            for t in threats
            if t.state["status"] == "active" and t.entity_id not in launching
        ]
        actions.append(action(node, "sense"))
        return actions

    def finished(self, world: WorldState) -> str | None:
        """ "threats_resolved" once no threat waits or flies; else None."""
        if any(
            t.state["status"] in ("reserve", "active") for t in of_type(world, "threat")
        ):
            return None
        return "threats_resolved"

    def outcome_label(self, world: WorldState) -> str | None:
        """
        defended   no threat reached an asset
        breached   at least one did (whether or not the asset survived)
        """
        hit = any(int(a.state["hits"]) > 0 for a in of_type(world, "asset"))
        return "breached" if hit else "defended"

    def failure_variables(self) -> dict[str, Any]:
        """sensor_failure, enemy_reaction_speed and equipment_overheat, here."""
        return airspace_failure_variables()

    def mission_goal(self, scenario: dict[str, Any], faction: str) -> dict[str, Any]:
        """What the defence is asked to do."""
        return {
            "type": "defend",
            "assets": [
                e["entity_id"]
                for e in scenario["entities"]
                if e["entity_type"] == "asset"
            ],
        }

    def airspace_outcome(
        self, package: dict[str, Any], scenario: dict[str, Any]
    ) -> dict[str, Any]:
        """Detection gap, response times and failure points (metrics.py)."""
        from .metrics import airspace_outcome

        return airspace_outcome(package, scenario)


AIRSPACE = AirspacePack()
