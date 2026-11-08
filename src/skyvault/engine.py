"""Engine = the tick loop that turns a scenario into a result package."""

import random
from typing import Any

from .action import location_to_json
from .actions import MILITARY_ACTION_TYPES, ActionContext, ActionResolver, handlers_for
from .contracts import (
    validate_action,
    validate_evaluation_profile,
    validate_result_package,
)
from .evaluation import evaluate_run
from .evaluator import build_evaluation_summary
from .runtime.snapshots import SnapshotStore
from .runtime.world import create_world
from .scenario_loader import default_evaluation_profile, scenario_perspective
from .tactical_reference_policy import TacticalReferencePolicy
from .world_state import WorldState

ENGINE_SYSTEM_ID = "skyvault_tactical_reference_engine"

# Keep a world snapshot every this many ticks, so a rebuild can start late
SNAPSHOT_INTERVAL = 5


class SkyVaultTacticalReferenceEngine:
    """
    First executable SKYVAULT-style tactical reference slice.

    This is not the final SKYVAULT engine.

    It exists to prove:

    Scenario
    → World State
    → Actor Policy
    → Action
    → Validation
    → Consequence
    → World State Mutation
    → Event Memory
    → Evaluation Result
    """

    def __init__(
        self,
        scenario: dict[str, Any],
        evaluation_profile: dict[str, Any] | None = None,
    ):
        self.scenario = scenario
        self.evaluation_profile = self.resolve_profile(evaluation_profile)

        runtime = scenario["runtime"]
        random_seed = runtime.get("random_seed")

        self.rng = random.Random(random_seed)
        self.world = self.build_world(scenario)
        self.policy = TacticalReferencePolicy(self.rng)
        self.snapshots = SnapshotStore(SNAPSHOT_INTERVAL)

        assumptions = scenario["world_contract"].get("assumption_registry", {})

        self.actor_system_id = assumptions.get(
            "actor_policy",
            type(self.policy).__name__,
        )

        # Every action goes through the resolver; the military line keeps
        # move, attack, observe, supply and repair (development plan Phase 3)
        self.resolver = ActionResolver(
            handlers_for(MILITARY_ACTION_TYPES),
            ActionContext(rng=self.rng, system_id=self.actor_system_id),
        )

    def resolve_profile(self, profile: dict[str, Any] | None) -> dict[str, Any]:
        """
        The evaluation profile this run is judged by.

        Important:
        None means data/evaluation_profiles/balanced.json. A profile without a
        perspective is judged from the scenario's perspective. Either way the
        profile is checked against its contract before the run starts, so a
        broken profile fails fast instead of after a whole simulation.
        """
        if profile is None:
            return default_evaluation_profile(self.scenario)

        resolved = validate_evaluation_profile(profile)
        if resolved["perspective"] is None:
            resolved["perspective"] = scenario_perspective(self.scenario)
        return resolved

    def build_world(self, scenario: dict[str, Any]) -> WorldState:
        """
        Build the time-zero world the scenario describes.

        Important:
        The world itself comes from runtime.create_world(), which supports any
        space and clock. This engine is the tactical reference: its policy
        steps between grid cells one tick at a time, so it refuses any other
        space or clock here instead of misbehaving later.

        An entity may omit position, in which case it is built with None.
        Anything that measures distance has to handle that.
        """
        world_contract = scenario["world_contract"]
        space_type = world_contract["space_model"]["type"]
        time_type = world_contract["time_model"]["type"]

        if space_type != "grid" or time_type != "tick":
            raise ValueError(
                "the tactical reference engine needs a grid space and a tick "
                f"clock, got {space_type!r} space and {time_type!r} time"
            )

        return create_world(scenario)

    def run(self) -> dict[str, Any]:
        """
        Run the scenario to completion and return the result package.

        Important:
        The initial world state is captured before the first tick, so the
        package carries both where the run started and where it ended. Every
        derived output is built from the package, never from the scenario file.
        """
        max_ticks = int(self.scenario["runtime"].get("max_ticks", 10))
        termination_reason = "duration_limit_reached"

        initial_world_state = self.world.snapshot()
        self.snapshots.record(self.world.tick, initial_world_state)

        for _ in range(max_ticks):
            self.world.advance_time()

            if len(self.world.active_factions()) <= 1:
                termination_reason = "termination_condition_met"
                break

            actors = list(self.world.active_entities())

            for actor in actors:
                if not actor.is_active():
                    continue

                action = self.policy.decide_action(self.world, actor)

                if action is None:
                    self.world.record_event(
                        event_type="NO_ACTION",
                        actor_id=actor.entity_id,
                        system_id=self.actor_system_id,
                        target_entity_id=None,
                        source_action_id=None,
                        before_state=actor.snapshot(),
                        after_state=actor.snapshot(),
                        affected_entities=[actor.entity_id],
                        data={"reason": "policy_returned_no_action"},
                        tags=["no_action"],
                    )
                    continue

                # A malformed action is a broken policy, not a rejected move:
                # it raises here and is never recorded or resolved.
                validate_action(action.to_dict())

                target_entity_id = action.target.entity_id
                action_entities = [actor.entity_id]

                if target_entity_id is not None:
                    action_entities.append(target_entity_id)

                self.world.record_event(
                    event_type="ACTION_SELECTED",
                    actor_id=actor.entity_id,
                    system_id=self.actor_system_id,
                    target_entity_id=target_entity_id,
                    source_action_id=action.action_id,
                    before_state=actor.snapshot(),
                    after_state=actor.snapshot(),
                    affected_entities=action_entities,
                    data={
                        "action_type": action.action_type,
                        "intent": action.intent,
                        "target_position": location_to_json(action.target.location),
                    },
                    tags=["action_selection"],
                )

                # Validation, resolution, world mutation and the resulting
                # events all happen inside the resolver
                consequence = self.resolver.execute(self.world, action)

                if not consequence.accepted:
                    self.world.record_event(
                        event_type="ACTION_REJECTED",
                        actor_id=action.actor_id,
                        system_id=self.actor_system_id,
                        target_entity_id=target_entity_id,
                        source_action_id=action.action_id,
                        before_state={},
                        after_state={},
                        affected_entities=action_entities,
                        data={
                            "reason": consequence.reason,
                            "action_type": action.action_type,
                        },
                        tags=["action_rejected"],
                    )

                if len(self.world.active_factions()) <= 1:
                    termination_reason = "termination_condition_met"
                    break

            # Snapshots are taken at the end of a tick, after all its events
            self.snapshots.record(self.world.tick, self.world.snapshot())

            if termination_reason == "termination_condition_met":
                break

        total_events = len(self.world.event_memory) + 1

        evaluation = self.evaluate(termination_reason, total_events)

        self.world.record_event(
            event_type="SCENARIO_END",
            actor_id=None,
            system_id=ENGINE_SYSTEM_ID,
            target_entity_id=None,
            source_action_id=None,
            before_state={},
            after_state=self.world.snapshot(),
            affected_entities=sorted(self.world.entities),
            evaluation_relevance={"affects_success": True},
            data=evaluation,
            tags=["scenario_end"],
        )

        event_memory = [event.to_dict() for event in self.world.event_memory]
        final_world_state = self.world.snapshot()

        # The multi-axis verdict is derived from what was recorded, after the
        # run; SCENARIO_END keeps the run-end summary it was given above
        evaluated = evaluate_run(
            initial_world_state,
            event_memory,
            final_world_state,
            evaluation,
            self.evaluation_profile,
            max_ticks,
            self.scenario["evaluation"].get("failure_thresholds", []),
        )

        # The package is checked against its contract before it leaves the
        # engine; every derived output is built from it alone.
        return validate_result_package(
            {
                "scenario_id": self.scenario["scenario_id"],
                "scenario_version": self.scenario["scenario_version"],
                "initial_world_state": initial_world_state,
                "final_world_state": final_world_state,
                "event_memory": event_memory,
                **evaluated,
            }
        )

    def evaluate(self, termination_reason: str, event_count: int) -> dict[str, Any]:
        """
        Summarise how the run ended.

        Important:
        event_count is passed in rather than read from event memory, because
        this summary is built before SCENARIO_END is recorded and has to count
        that event too.
        """
        return build_evaluation_summary(self.world, termination_reason, event_count)
