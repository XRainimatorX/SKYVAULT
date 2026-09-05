"""Actor policy = how an entity picks its action for the current tick."""

import random

from .action import Action, new_action_id
from .entity import Entity, Position
from .world_state import WorldState


class TacticalReferencePolicy:
    """
    Temporary tactical actor policy.

    This file is allowed to contain threat_score / target_score style logic.

    Important:
    This is NOT SKYVAULT core.

    It exists only to make the first tactical reference slice runnable.
    Future TAC ANGEL or other actor policies can replace this.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def decide_action(self, world: WorldState, actor: Entity) -> Action | None:
        """
        Choose what this actor attempts this tick, or None to stand still.

        Important:
        This only ever proposes. Validation and the world mutation happen in
        the engine, so a policy can never change the world by deciding.
        """
        if not actor.is_active():
            return None

        enemies = [
            entity
            for entity in world.active_entities()
            if entity.faction is not None and entity.faction != actor.faction
        ]

        if not enemies:
            return None

        target = self.choose_target(world, actor, enemies)

        if actor.position is None or target.position is None:
            return None

        distance = world.space.distance(actor.position, target.position)
        attack_range = int(actor.capabilities.get("attack_range", 1))

        if distance <= attack_range:
            return Action(
                action_id=new_action_id(),
                actor_id=actor.entity_id,
                action_type="attack",
                target_entity_id=target.entity_id,
                intent="tactical_reference_attack_selected_target",
            )

        next_position = self.next_step_toward(world, actor, target)

        if next_position is None:
            return None

        return Action(
            action_id=new_action_id(),
            actor_id=actor.entity_id,
            action_type="move",
            target_position=next_position,
            intent="tactical_reference_move_toward_selected_target",
        )

    def choose_target(
        self,
        world: WorldState,
        actor: Entity,
        enemies: list[Entity],
    ) -> Entity:
        """
        Old threat_score / target_score logic belongs here temporarily.

        It is useful for testing SKYVAULT functionality,
        but it must not be treated as SKYVAULT core logic.
        """

        scored_targets: list[tuple[Entity, float]] = []

        for enemy in enemies:
            score = self.threat_score(actor, enemy)
            scored_targets.append((enemy, score))

        max_score = max(score for _, score in scored_targets)

        best_targets = [enemy for enemy, score in scored_targets if score == max_score]

        return self.rng.choice(best_targets)

    def threat_score(self, actor: Entity, enemy: Entity) -> float:
        """
        Temporary reference scoring model.

        Similar idea to the original prototype:
        - low enemy hp = easier target
        - high damage enemy = more dangerous
        - role affects priority
        """

        enemy_hp = int(enemy.state.get("hp", 0))
        enemy_damage = int(enemy.capabilities.get("attack_damage", 0))
        enemy_role = enemy.tags[0] if enemy.tags else "ASSAULT"

        role_score = {
            "ASSAULT": 20,
            "SUPPORT": 30,
            "COMMAND": 50,
        }.get(enemy_role, 20)

        actor_role = actor.tags[0] if actor.tags else "ASSAULT"

        weight_matrix = {
            "ASSAULT": [0.4, 0.3, 0.3],
            "SUPPORT": [0.2, 0.5, 0.3],
            "COMMAND": [0.2, 0.2, 0.6],
        }

        weights = weight_matrix.get(actor_role, weight_matrix["ASSAULT"])

        hp_vulnerability = max(0, 120 - enemy_hp)
        damage_threat = enemy_damage

        score = (
            weights[0] * hp_vulnerability
            + weights[1] * damage_threat
            + weights[2] * role_score
        )

        return score

    def next_step_toward(
        self,
        world: WorldState,
        actor: Entity,
        target: Entity,
    ) -> Position | None:
        """
        The adjacent square that gets this actor closest to the target.

        Important:
        Returns None when either side has no position, or when no free
        neighbouring square is an improvement. Ties are broken with the
        engine's seeded rng so the choice repeats across runs.
        """
        if actor.position is None or target.position is None:
            return None

        # Bind the narrowed positions so the type stays known inside the loop
        actor_position = actor.position
        target_position = target.position

        ax, ay = actor_position
        current_distance = world.space.distance(actor_position, target_position)

        candidates: list[Position] = []

        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue

                candidate = (ax + dx, ay + dy)

                if not world.space.is_inside(candidate):
                    continue

                if world.is_occupied(candidate):
                    continue

                if world.space.distance(candidate, target_position) < current_distance:
                    candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(key=lambda pos: world.space.distance(pos, target_position))

        best_distance = world.space.distance(candidates[0], target_position)

        best_candidates = [
            pos
            for pos in candidates
            if world.space.distance(pos, target_position) == best_distance
        ]

        return self.rng.choice(best_candidates)
