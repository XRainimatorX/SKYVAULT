"""A stand-in for TAC ANGEL: an outside policy that sees only its observation.

    python3 scripts/run_tactical_reference.py \
        --scenario data/scenarios/military_squad_001/v0.1.json \
        --policy-module examples/tac_angel_policy.py --policy tac_angel_example

TAC ANGEL itself is an outside system; this file only shows the interface.
It names an observer profile (data/observers/tac_angel.json), so the engine
never hands it the world: decide_from_observation gets the local view of
one unit — its side, the enemies in sight or recently lost — and answers
with an order. The engine issues the action id. Its system_id is written
on every event its decisions cause. Registering a factory makes it
available by name to scenarios (runtime.policy.name) and to the scripts'
--policy flag.
"""

import random
from typing import Any

from skyvault.policies import register_policy


class TacAngelExamplePolicy:
    """Fire at the nearest enemy in range, otherwise step toward the nearest known."""

    system_id = "TAC_ANGEL"
    observer_profile = "TAC_ANGEL"

    def __init__(self, rng: random.Random):
        self.rng = rng

    def decide_from_observation(
        self, observation: dict[str, Any]
    ) -> dict[str, Any] | None:
        known = observation["visible_world_state"]["known_entities"]
        me = next(e for e in known if e["relation"] == "self")
        enemies = [
            e for e in known if e["relation"] == "enemy" and e["status"] != "destroyed"
        ]
        if not enemies or me["position"] is None:
            return None
        # In sight beats remembered; then the nearest, then the surest
        x, y = me["position"]

        def distance(e: dict[str, Any]) -> int:
            return max(abs(e["position"][0] - x), abs(e["position"][1] - y))

        nearest = min(
            enemies,
            key=lambda e: (
                e["status"] != "visible",
                distance(e),
                -e["confidence"],
                e["entity_id"],
            ),
        )
        reach = int(me["capabilities"].get("attack_range", 1))
        if nearest["status"] == "visible" and distance(nearest) <= reach:
            return {
                "action_type": "attack",
                "target": {"entity_id": nearest["entity_id"]},
                "intent": "tac_angel_engage",
            }
        tx, ty = nearest["position"]
        step = [x + (tx > x) - (tx < x), y + (ty > y) - (ty < y)]
        return {
            "action_type": "move",
            "target": {"location": step},
            "intent": "tac_angel_close_in",
        }


register_policy("tac_angel_example", lambda rng, params: TacAngelExamplePolicy(rng))
