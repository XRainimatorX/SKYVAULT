"""HADES's rules of engagement and the patrol baseline, as one policy.

Important:
Interceptors follow rule_set.airspace.hades — the behaviour HADES submits:

engage_at        fire only at tracks within this share of the range (0–1)
priority         nearest_to_asset (the track closest to any asset) or
                 first_tracked (the oldest track)
salvo            shots per engagement (at most the ammunition left)
hold_fire_below  do not fire at a track seen with less confidence than this

Only tracks identified as threats and cleared (past the reaction delay)
are candidates; ties break by track id. Drones fly their route, one step
of their speed at a time. The policy draws nothing at random.

Registered as "hades_rules": runtime.policy {name: "hades_rules", params:
{...}} runs a scenario under the behaviour HADES submitted, each param
overriding the scenario's rule of the same name.
"""

from typing import Any

from ...action import Action, ActionTarget
from ...policies import register_policy
from .model import distance, step_toward

RULES = ("engage_at", "priority", "salvo", "hold_fire_below")


class AirDefencePolicy:
    """Decides for interceptors (HADES's rules) and drones (their patrol)."""

    system_id = "hades_rules_of_engagement"

    def __init__(self, behavior: dict[str, Any] | None = None) -> None:
        behavior = dict(behavior or {})
        unknown = sorted(set(behavior) - set(RULES))
        if unknown:
            raise ValueError(f"unknown rules of engagement {unknown}")
        if behavior.get("priority", "nearest_to_asset") not in (
            "nearest_to_asset",
            "first_tracked",
        ):
            raise ValueError(f"unknown engagement priority {behavior['priority']!r}")
        if not 0 <= float(behavior.get("engage_at", 1.0)) <= 1:
            raise ValueError("engage_at is a share of the interceptor's range (0–1)")
        if int(behavior.get("salvo", 1)) < 1:
            raise ValueError("a salvo is at least one shot")
        self.behavior = behavior

    def decide_action(self, world: Any, actor: Any) -> Action | None:
        if actor.entity_type == "interceptor":
            return self.interceptor(world, actor)
        if actor.entity_type == "drone":
            return self.drone(world, actor)
        return None

    def interceptor(self, world: Any, actor: Any) -> Action | None:
        rules = {**world.rules.require("airspace")["hades"], **self.behavior}
        if int(actor.state["ammo"]) <= 0 or world.tick < int(actor.state["ready_at"]):
            return None
        command = next(e for e in world.entities.values() if e.entity_type == "command")
        reach = float(actor.capabilities["range"]) * float(rules["engage_at"])
        candidates = [
            t
            for t in command.state["tracks"].values()
            if t["identified"] == "threat"
            and world.tick >= int(t["engageable_from"])
            and float(t["confidence"]) >= float(rules["hold_fire_below"])
            and distance(actor.position, t["position"]) <= reach
        ]
        if not candidates:
            return None
        assets = [
            e.position
            for e in world.entities.values()
            if e.entity_type == "asset" and e.is_active()
        ]
        if rules["priority"] == "first_tracked" or not assets:
            chosen = min(candidates, key=lambda t: (int(t["opened"]), t["track_id"]))
        else:
            chosen = min(
                candidates,
                key=lambda t: (
                    min(distance(t["position"], a) for a in assets),
                    t["track_id"],
                ),
            )
        return Action(
            action_id=world.ids.action(),
            actor_id=actor.entity_id,
            action_type="engage",
            target=ActionTarget(
                entity_id=chosen["target"],
                location=(int(chosen["position"][0]), int(chosen["position"][1])),
            ),
            intent=f"engage_{rules['priority']}",
            expected_effect="hades:intercept",
            metadata={"track": chosen["track_id"], "shots": int(rules["salvo"])},
        )

    def drone(self, world: Any, actor: Any) -> Action | None:
        route = actor.capabilities["route"]
        leg = int(actor.state.get("leg", 0)) % len(route)
        if list(actor.position) == list(route[leg]):
            leg = (leg + 1) % len(route)
        goal = route[leg]
        step = step_toward(actor.position, goal, int(actor.capabilities["speed"]))
        if step == list(actor.position):
            return None
        return Action(
            action_id=world.ids.action(),
            actor_id=actor.entity_id,
            action_type="move",
            target=ActionTarget(location=(step[0], step[1])),
            intent="patrol",
            expected_effect="skyfox:patrol",
        )


register_policy("hades_rules", lambda rng, params: AirDefencePolicy(params))
