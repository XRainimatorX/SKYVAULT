"""A stand-in for TAC ANGEL: an outside policy that replaces the baseline.

    python3 scripts/run_tactical_reference.py \
        --scenario data/scenarios/military_squad_001/v0.1.json \
        --policy-module examples/tac_angel_policy.py --policy tac_angel_example

TAC ANGEL itself is an outside system; this file only shows the interface.
A policy is any object with decide_action(world, actor) -> Action | None.
Its system_id is written on every event its decisions cause. Registering a
factory makes it available by name to scenarios (runtime.policy.name) and
to the scripts' --policy flag.
"""

import random
from typing import Any

from skyvault.action import Action, ActionTarget
from skyvault.policies import register_policy


class TacAngelExamplePolicy:
    """Fire at the nearest enemy in range, otherwise step toward it."""

    system_id = "TAC_ANGEL"

    def __init__(self, rng: random.Random):
        self.rng = rng

    def decide_action(self, world: Any, actor: Any) -> Action | None:
        enemies = [
            unit
            for unit in world.active_entities()
            if unit.faction != actor.faction and unit.position is not None
        ]
        if not enemies or actor.position is None:
            return None
        nearest = min(
            enemies,
            key=lambda e: (
                world.space.distance(actor.position, e.position),
                e.entity_id,
            ),
        )
        distance = world.space.distance(actor.position, nearest.position)
        if distance <= int(actor.capabilities.get("attack_range", 1)):
            return Action(
                world.ids.action(),
                actor.entity_id,
                "attack",
                target=ActionTarget(entity_id=nearest.entity_id),
                intent="tac_angel_engage",
            )
        x, y = actor.position
        tx, ty = nearest.position
        step = (x + (tx > x) - (tx < x), y + (ty > y) - (ty < y))
        return Action(
            world.ids.action(),
            actor.entity_id,
            "move",
            target=ActionTarget(location=step),
            intent="tac_angel_close_in",
        )


register_policy("tac_angel_example", lambda rng, params: TacAngelExamplePolicy(rng))
