"""The military baseline policy: doctrine, perception, morale and command delay.

Important:
Like every policy it only proposes. What a unit knows is what its sensor
sees: an enemy counts as seen when it is within sensor range shrunk by the
concealment of the enemy's cell. Before any enemy is seen, units head for
where the enemy started (the intelligence a briefing would give).

Orders take delay_ticks to arrive and are lost with loss_prob, drawn from a
generator of their own so command friction never shifts the battle's own
draws; with no delay and no loss the policy behaves exactly as if there
were no command layer at all.
"""

import random
from typing import Any

from ...action import Action, ActionTarget
from ...entity import Entity
from ...world_state import WorldState
from .handlers import enemy_cells, is_suppressed
from .terrain import cell_of, military_rules, reachable, terrain_at

SYSTEM_ID = "military_baseline"


class MilitaryBaselinePolicy:
    """The pack's default policy; each faction follows its own doctrine."""

    system_id = SYSTEM_ID

    def __init__(
        self, rng: random.Random, scenario: dict[str, Any], seed: int | None = None
    ):
        self.rng = rng
        rules = scenario["world_contract"]["rule_set"]["military"]
        self.factions: dict[str, Any] = rules["factions"]
        self.order = [entity["entity_id"] for entity in scenario["entities"]]
        self.enemy_start: dict[str, list[tuple[int, int]]] = {}
        for faction in self.factions:
            self.enemy_start[faction] = [
                (int(e["position"][0]), int(e["position"][1]))
                for e in scenario["entities"]
                if e["faction"] != faction and e.get("position") is not None
            ]
        self.command_rng = random.Random(None if seed is None else f"command:{seed}")
        self.pending: dict[tuple[int, str], Action] = {}

    # ── the command layer ───────────────────────────────────────────────────

    def decide_action(self, world: WorldState, actor: Entity) -> Action | None:
        """
        The order that reaches actor this tick.

        Important:
        A fresh decision is made every tick and sent down the chain; what
        arrives is the decision made delay_ticks ago, unless it was lost.
        The loss roll is skipped entirely when loss_prob is zero.
        """
        if not actor.is_active():
            return None
        command = self.factions[str(actor.faction)]["command"]
        decision = self.decide(world, actor)
        if decision is not None:
            lost = command["loss_prob"] > 0 and (
                self.command_rng.random() < command["loss_prob"]
            )
            if not lost:
                self.pending[(world.tick + command["delay_ticks"], actor.entity_id)] = (
                    decision
                )
        return self.pending.pop((world.tick, actor.entity_id), None)

    # ── the decision ────────────────────────────────────────────────────────

    def decide(self, world: WorldState, actor: Entity) -> Action | None:
        """What actor would do now, given what it sees, its morale and doctrine."""
        morale = military_rules(world)["morale"]
        side = self.factions[str(actor.faction)]
        suppression = int(actor.state.get("suppression", 0))

        if suppression >= int(morale["panic_threshold"]):
            return self.action(world, actor, "wait", intent="pinned_down")

        seen = self.seen_enemies(world, actor)
        if int(actor.state.get("morale", morale["start"])) < int(
            morale["retreat_threshold"]
        ):
            return self.retreat(world, actor, seen)

        if "LOGISTICS" in actor.tags:
            supply = self.resupply(world, actor)
            if supply is not None:
                return supply

        target = self.target_in_range(world, actor, seen)
        doctrine = side["doctrine"]
        bounding = doctrine == "overwatch" and (
            (self.order.index(actor.entity_id) + world.tick) % 2 == 0
        )
        if target is not None and not bounding:
            return self.action(
                world, actor, "attack", entity_id=target.entity_id, intent="engage"
            )
        if is_suppressed(world, actor):
            return self.take_cover(world, actor, intent="suppressed_take_cover")
        if doctrine == "defensive" and seen:
            return self.take_cover(world, actor, intent="defend_from_cover")
        if doctrine == "overwatch" and not bounding:
            if target is not None:
                return self.action(
                    world,
                    actor,
                    "attack",
                    entity_id=target.entity_id,
                    intent="overwatch",
                )
            return self.take_cover(world, actor, intent="overwatch_hold")
        goal = self.goal(world, actor, side, seen)
        if goal is None:
            return self.take_cover(world, actor, intent="hold_position")
        return self.advance(world, actor, goal)

    def seen_enemies(self, world: WorldState, actor: Entity) -> list[Entity]:
        """Enemies within sensor range × (1 − concealment of their cell)."""
        if actor.position is None:
            return []
        sensor = float(actor.capabilities.get("sensor_range", 5))
        return [
            enemy
            for enemy in world.active_entities()
            if enemy.faction != actor.faction
            and enemy.position is not None
            and world.space.distance(actor.position, enemy.position)
            <= sensor * (1 - float(terrain_at(world, enemy.position)["concealment"]))
        ]

    def target_in_range(
        self, world: WorldState, actor: Entity, seen: list[Entity]
    ) -> Entity | None:
        """The weakest seen enemy in weapon range, if there is ammunition."""
        if float(actor.state.get("ammo", 0)) < int(
            actor.capabilities.get("ammo_per_shot", 1)
        ):
            return None
        weapon_range = int(actor.capabilities.get("attack_range", 1))
        in_range = [
            enemy
            for enemy in seen
            if actor.position is not None
            and world.space.distance(actor.position, enemy.position) <= weapon_range
        ]
        if not in_range:
            return None
        weakest = min(int(enemy.state.get("hp", 0)) for enemy in in_range)
        candidates = [e for e in in_range if int(e.state.get("hp", 0)) == weakest]
        return self.rng.choice(candidates) if len(candidates) > 1 else candidates[0]

    def goal(
        self,
        world: WorldState,
        actor: Entity,
        side: dict[str, Any],
        seen: list[Entity],
    ) -> tuple[int, int] | None:
        """Where to head: the nearest seen enemy, else the mission's place."""
        mission = side["mission"]
        objective = [(int(c[0]), int(c[1])) for c in mission.get("objective", [])]
        if mission["type"] in ("hold", "delay"):
            if not objective or self.near(world, actor, objective, 1):
                return None
            return self.nearest(world, actor, objective)
        if seen:
            return self.nearest(world, actor, [e.position for e in seen])
        if mission["type"] == "seize" and objective:
            return self.nearest(world, actor, objective)
        return self.nearest(world, actor, self.enemy_start[str(actor.faction)])

    def advance(
        self, world: WorldState, actor: Entity, goal: tuple[int, int]
    ) -> Action:
        """Move to the reachable cell closest to goal; cover breaks ties."""
        options = self.options(world, actor)
        best = min(
            world.space.distance(cell, goal) - float(terrain_at(world, cell)["cover"])
            for cell in options
        )
        here = world.space.distance(actor.position, goal)
        if here - float(terrain_at(world, actor.position)["cover"]) <= best:
            return self.action(world, actor, "wait", intent="in_position")
        choices = [
            cell
            for cell in options
            if world.space.distance(cell, goal)
            - float(terrain_at(world, cell)["cover"])
            == best
        ]
        cell = self.rng.choice(choices) if len(choices) > 1 else choices[0]
        return self.action(world, actor, "move", location=cell, intent="advance")

    def take_cover(self, world: WorldState, actor: Entity, intent: str) -> Action:
        """Move to the best cover within one step's reach, or stay put."""
        here = float(terrain_at(world, actor.position)["cover"])
        options = [
            cell
            for cell in self.options(world, actor)
            if world.space.distance(cell, actor.position) <= 1
        ]
        best = max((float(terrain_at(world, c)["cover"]) for c in options), default=0)
        if best <= here:
            return self.action(world, actor, "wait", intent=intent)
        choices = [c for c in options if float(terrain_at(world, c)["cover"]) == best]
        cell = self.rng.choice(choices) if len(choices) > 1 else choices[0]
        return self.action(world, actor, "move", location=cell, intent=intent)

    def retreat(self, world: WorldState, actor: Entity, seen: list[Entity]) -> Action:
        """Fall back: the reachable cell farthest from every seen enemy."""
        threats = [e.position for e in seen] or self.enemy_start[str(actor.faction)]
        options = self.options(world, actor)
        if not options:
            return self.action(world, actor, "wait", intent="retreat_blocked")

        def safety(cell: tuple[int, int]) -> float:
            return min(world.space.distance(cell, t) for t in threats)

        here = safety(cell_of(actor))
        best = max(safety(cell) for cell in options)
        if best <= here:
            return self.action(world, actor, "wait", intent="retreat_blocked")
        choices = [cell for cell in options if safety(cell) == best]
        cell = self.rng.choice(choices) if len(choices) > 1 else choices[0]
        return self.action(world, actor, "move", location=cell, intent="retreat")

    def resupply(self, world: WorldState, actor: Entity) -> Action | None:
        """Supply the lowest-ammunition friend in range that is running low."""
        logistics = military_rules(world)["logistics"]
        if (
            world.resources.amount("ammo") if "ammo" in world.resources else 0.0
        ) < float(logistics["resupply_amount"]):
            return None
        limit = int(actor.capabilities.get("supply_range", 1))
        low = [
            friend
            for friend in world.active_entities()
            if friend.faction == actor.faction
            and friend.entity_id != actor.entity_id
            and friend.position is not None
            and world.space.distance(actor.position, friend.position) <= limit
            and float(friend.state.get("ammo", 0))
            < float(logistics["low_ammo_share"])
            * float(friend.capabilities.get("max_ammo", 0))
        ]
        if not low:
            return None
        neediest = min(low, key=lambda f: (float(f.state.get("ammo", 0)), f.entity_id))
        return self.action(
            world, actor, "supply", entity_id=neediest.entity_id, intent="resupply"
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    def options(self, world: WorldState, actor: Entity) -> list[tuple[int, int]]:
        """Free cells actor can reach this tick, in a fixed order."""
        budget = int(actor.capabilities.get("move_range", 1))
        cells = reachable(
            world, cell_of(actor), budget, enemy_cells(world, actor.faction)
        )
        return sorted(
            cell
            for cell in cells
            if cell != actor.position and not world.is_occupied(cell)
        )

    def nearest(
        self, world: WorldState, actor: Entity, cells: list[Any]
    ) -> tuple[int, int]:
        return min(
            ((int(c[0]), int(c[1])) for c in cells),
            key=lambda c: (world.space.distance(actor.position, c), c),
        )

    def near(
        self, world: WorldState, actor: Entity, cells: list[tuple[int, int]], limit: int
    ) -> bool:
        return any(world.space.distance(actor.position, c) <= limit for c in cells)

    def action(
        self,
        world: WorldState,
        actor: Entity,
        action_type: str,
        entity_id: str | None = None,
        location: tuple[int, int] | None = None,
        intent: str = "",
    ) -> Action:
        return Action(
            action_id=world.ids.action(),
            actor_id=actor.entity_id,
            action_type=action_type,
            target=ActionTarget(entity_id=entity_id, location=location),
            intent=intent,
            expected_effect=f"military_baseline:{intent}",
        )
