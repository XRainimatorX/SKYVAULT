"""CITY = the city domain pack as the engine sees it (development plan Phase 14)."""

import random
from typing import Any

from ...action import Action, ActionTarget
from ...actions import ActionHandler
from ...world_state import WorldState
from .handlers import ACTION_TYPES, MOBILE, city_handlers, districts, rules_of
from .policy import CityAdministrationPolicy
from .score import governance_stability, population_order

ACTORS = MOBILE + ("city_office",)


class CityPack:
    """
    A city on a road network, run to its time limit.

    Important:
    The city has one faction, so it does not end when one faction is left
    (ends_with_last_faction False); it ends early only when every district
    is in riot (finished → "governance_collapsed").
    """

    name = "city"
    action_types = ACTION_TYPES
    spaces = ("network", "graph")
    ends_with_last_faction = False

    def handlers(self) -> dict[str, ActionHandler]:
        return city_handlers()

    def default_policy(
        self, scenario: dict[str, Any], rng: random.Random
    ) -> CityAdministrationPolicy:
        return CityAdministrationPolicy()

    def acts(self, entity: Any) -> bool:
        """Only actors decide, and only when not on the road."""
        return entity.entity_type in ACTORS and entity.position is not None

    def upkeep(self, world: WorldState) -> list[Action]:
        """The grid, then arrivals, then every district's tick."""

        def action(
            actor_id: str, action_type: str, target: str | None = None
        ) -> Action:
            return Action(
                action_id=world.ids.action(),
                actor_id=actor_id,
                action_type=action_type,
                target=ActionTarget(entity_id=target),
                intent=f"city_{action_type}",
                expected_effect=f"city:{action_type}",
            )

        grid = next(
            (e for e in world.entities.values() if e.entity_type == "power_plant"),
            None,
        )
        actions = []
        if grid is not None:
            actions.append(action(grid.entity_id, "power_update"))
        actions += [
            action(e.entity_id, "arrive", e.entity_id)
            for e in world.entities.values()
            if e.entity_type in MOBILE and e.state.get("arrives_at") == world.tick
        ]
        actions += [
            action(d.entity_id, "district_update", d.entity_id)
            for d in districts(world)
        ]
        return actions

    def finished(self, world: WorldState) -> str | None:
        """ "governance_collapsed" once every district is in riot; else None."""
        every = districts(world)
        if every and all(d.state["order_state"] == "riot" for d in every):
            return "governance_collapsed"
        return None

    def outcome_label(self, world: WorldState) -> str | None:
        """
        How the city ended, by population-weighted public order:

        governance_collapsed   every district in riot
        order_restored         ends at or above the stable threshold, having
                               started below it
        order_held             started and ends at or above it
        order_not_restored     ends below it
        """
        if self.finished(world):
            return "governance_collapsed"
        stable = float(rules_of(world)["order"]["stable"])
        end = population_order({d.entity_id: d.state for d in districts(world)})
        if end < stable:
            return "order_not_restored"
        start = population_order(_start_states(world))
        return "order_held" if start >= stable else "order_restored"

    def governance_outcome(
        self, package: dict[str, Any], scenario: dict[str, Any]
    ) -> dict[str, Any]:
        """The governance stability score of a finished run (score.py)."""
        return governance_stability(package, scenario)

    def mission_goal(self, scenario: dict[str, Any], faction: str) -> dict[str, Any]:
        """What the city administration is asked to do."""
        return {"type": "restore_order", "purpose": scenario.get("purpose", "")}


def _start_states(world: WorldState) -> dict[str, dict[str, Any]]:
    """Each district as it was before its first update (its current state if none)."""
    start: dict[str, dict[str, Any]] = {}
    for event in world.event_memory:
        if "district_update" in event.tags and event.target_entity_id not in start:
            start[str(event.target_entity_id)] = event.before_state["state"]
    for district in districts(world):
        start.setdefault(district.entity_id, district.state)
    return start


CITY = CityPack()
