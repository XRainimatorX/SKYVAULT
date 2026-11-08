"""The city's baseline administration: a rule-based policy for its actors.

Important:
Convoys go where food will run out first; police go where order is worst;
the repair crew goes to the offline substation that leaves the most people
dark; the city office strengthens the weakest administration. Each actor
takes what no other actor of its kind is already heading for. Ties break by
entity id, so the policy itself draws nothing at random.
"""

from typing import Any

from ...action import Action, ActionTarget
from .model import consumption


class CityAdministrationPolicy:
    """Decides for police, convoys, repair crews and the city office."""

    system_id = "city_administration_baseline"

    def decide_action(self, world: Any, actor: Any) -> Action | None:
        kind = actor.entity_type
        if kind == "convoy":
            return self.convoy(world, actor)
        if kind == "police":
            return self.police(world, actor)
        if kind == "repair_crew":
            return self.crew(world, actor)
        if kind == "city_office":
            return self.office(world, actor)
        return None

    def act(
        self,
        world: Any,
        actor: Any,
        action_type: str,
        intent: str,
        entity_id: str | None = None,
        location: Any = None,
    ) -> Action:
        return Action(
            action_id=world.ids.action(),
            actor_id=actor.entity_id,
            action_type=action_type,
            target=ActionTarget(entity_id=entity_id, location=location),
            intent=intent,
            expected_effect=f"city_administration:{intent}",
        )

    def convoy(self, world: Any, actor: Any) -> Action | None:
        """At home: load for the district with the fewest ticks of food left."""
        if actor.position != actor.state["home"]:
            return self.act(
                world, actor, "travel", "return_to_depot", location=actor.state["home"]
            )
        rules = world.rules.require("city")
        taken = {
            c.state.get("destination")
            for c in _of(world, "convoy")
            if c.entity_id != actor.entity_id and c.state.get("leg") == "outbound"
        }
        reachable = [
            d
            for d in _of(world, "district")
            if d.position not in taken
            and world.space.distance(actor.position, d.position) != float("inf")
        ]
        if not reachable:
            return None
        hungriest = min(
            reachable,
            key=lambda d: (
                float(d.state["food"])
                / max(consumption(d.state["population"], rules), 1e-9),
                d.entity_id,
            ),
        )
        return self.act(
            world, actor, "dispatch", "feed_hungriest", entity_id=hungriest.entity_id
        )

    def police(self, world: Any, actor: Any) -> Action | None:
        """Patrol the worst district no other officer is covering; go there first."""
        covered = {
            p.position if p.position is not None else p.state.get("destination")
            for p in _of(world, "police")
            if p.entity_id != actor.entity_id
        }
        open_districts = [
            d for d in _of(world, "district") if d.position not in covered
        ]
        if not open_districts:
            return self.act(world, actor, "patrol", "hold_district")
        worst = min(
            open_districts,
            key=lambda d: (float(d.state["public_order"]), d.entity_id),
        )
        here = world.get_entity(str(actor.position))
        if worst.position == actor.position or float(
            here.state["public_order"]
        ) <= float(worst.state["public_order"]):
            return self.act(world, actor, "patrol", "restore_order")
        return self.act(
            world, actor, "travel", "move_to_unrest", location=worst.position
        )

    def crew(self, world: Any, actor: Any) -> Action | None:
        """
        Finish the offline substation the crew stands at; otherwise go to
        the next one: failed before tripped (a tripped one restored while
        the failure that overloaded it remains would trip again), then the
        one that leaves the most people dark.
        """
        offline = [s for s in _of(world, "substation") if not s.state["online"]]
        if not offline:
            return None
        here = [s for s in offline if s.position == actor.position]
        people = {
            d.entity_id: float(d.state["population"]) for d in _of(world, "district")
        }
        target = (
            here[0]
            if here
            else max(
                offline,
                key=lambda s: (
                    int(s.state["repair_needed"]),
                    sum(people.get(d, 0.0) for d in s.capabilities["serves"]),
                    s.entity_id,
                ),
            )
        )
        if actor.position == target.position:
            return self.act(
                world,
                actor,
                "restore_power",
                "restore_power",
                entity_id=target.entity_id,
            )
        return self.act(
            world, actor, "travel", "go_to_substation", location=target.position
        )

    def office(self, world: Any, actor: Any) -> Action | None:
        """Strengthen the district whose administration is weakest."""
        weakest = min(
            _of(world, "district"),
            key=lambda d: (float(d.state["administration"]), d.entity_id),
        )
        if float(weakest.state["administration"]) >= 1.0:
            return None
        return self.act(
            world,
            actor,
            "administer",
            "strengthen_administration",
            entity_id=weakest.entity_id,
        )


def _of(world: Any, entity_type: str) -> list[Any]:
    return [
        e
        for e in world.entities.values()
        if e.entity_type == entity_type and e.is_active()
    ]
