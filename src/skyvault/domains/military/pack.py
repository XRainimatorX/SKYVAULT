"""MILITARY = the military domain pack as the engine sees it."""

import random
from typing import Any

from ...action import Action, ActionTarget
from ...actions import ActionHandler
from ...policies import Policy
from ...world_state import WorldState
from .handlers import ACTION_TYPES, military_handlers
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


MILITARY = MilitaryPack()
