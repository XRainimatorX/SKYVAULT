"""MILITARY = the military domain pack as the engine sees it."""

import random
from typing import Any

from ...action import Action, ActionTarget
from ...actions import ActionHandler
from ...policies import Policy
from ...world_state import WorldState
from .dataset import sensor_contacts
from .handlers import ACTION_TYPES, military_handlers
from .mission import mission_outcome
from .policy import MilitaryBaselinePolicy
from .terrain import military_rules


class MilitaryPack:
    """Handlers, the baseline policy, and the start-of-tick rally."""

    name = "military"
    action_types = ACTION_TYPES

    def handlers(self) -> dict[str, ActionHandler]:
        return military_handlers()

    def default_policy(self, scenario: dict[str, Any], rng: random.Random) -> Policy:
        return MilitaryBaselinePolicy(rng, scenario, scenario["runtime"]["random_seed"])

    def upkeep(self, world: WorldState) -> list[Action]:
        """
        A rally for every living unit with suppression to shed or morale to
        regain, in registry order.
        """
        start = int(military_rules(world)["morale"]["start"])
        return [
            Action(
                action_id=world.ids.action(),
                actor_id=unit.entity_id,
                action_type="rally",
                target=ActionTarget(entity_id=unit.entity_id),
                intent="recover",
                expected_effect="suppression down, morale up",
            )
            for unit in world.active_entities()
            if int(unit.state.get("suppression", 0)) > 0
            or int(unit.state.get("morale", start)) < start
        ]

    def mission_outcome(
        self, package: dict[str, Any], scenario: dict[str, Any]
    ) -> dict[str, Any]:
        """Each faction's mission judged after the run (mission.py)."""
        return mission_outcome(package, scenario)

    def concealment(self, scenario: dict[str, Any], cell: Any) -> float:
        """How much the ground at cell hides a unit (0 without a map)."""
        terrain = scenario["world_contract"]["environment_state"].get("terrain")
        if terrain is None or not isinstance(cell, (list, tuple)):
            return 0.0
        x, y = cell
        name = terrain["legend"][terrain["rows"][y][x]]
        table = scenario["world_contract"]["rule_set"]["military"]["terrain"]
        return float(table[name]["concealment"])

    def mission_goal(self, scenario: dict[str, Any], faction: str) -> dict[str, Any]:
        """The faction's mission as the scenario states it (empty when none)."""
        factions = scenario["world_contract"]["rule_set"]["military"]["factions"]
        return dict(factions.get(faction, {}).get("mission", {}))

    def observe(
        self, actor: dict[str, Any], units: dict[str, Any], scenario: dict[str, Any]
    ) -> dict[str, Any]:
        """What actor's sensor shows of units (entity snapshots)."""
        seen, allies = sensor_contacts(actor, units, scenario)
        return {
            "observation_model": "military_sensor",
            "seen_enemies": seen,
            "allies": allies,
        }


MILITARY = MilitaryPack()
