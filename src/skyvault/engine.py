"""Engine = the tick loop that turns a scenario into a result package."""

import platform
import random
from datetime import datetime, timezone
from typing import Any, cast

from .action import Action, ActionTarget, location_to_json
from .actions import MILITARY_ACTION_TYPES, ActionContext, ActionResolver, handlers_for
from .actors.participants import Participants
from .actors.view import WorldView
from .contracts import (
    validate_action,
    validate_evaluation_profile,
    validate_order,
    validate_result_package,
)
from .domains import DomainPack, load_domain
from .entity import Entity
from .evaluation import evaluate_run
from .evaluator import build_evaluation_summary
from .observation import context_for, load_observer_profile, observe
from .policies import (
    AnyPolicy,
    MultiViewPolicy,
    ObservingPolicy,
    Policy,
    build_policy,
)
from .reproducibility import (
    RUNTIME_VERSION,
    input_hash,
    output_hash,
    ruleset_version,
    seed_policy,
)
from .runtime.snapshots import SnapshotStore
from .runtime.world import create_world
from .scenario_loader import default_evaluation_profile, scenario_perspective
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
        policy: AnyPolicy | None = None,
    ):
        self.scenario = scenario
        self.evaluation_profile = self.resolve_profile(evaluation_profile)

        # A stochastic run draws an unseeded generator on purpose and records
        # no seed; every other policy seeds the run's only random source
        self.seed_policy, self.random_seed, self.replayable = seed_policy(
            scenario["runtime"]
        )
        self.rng = random.Random(self.random_seed)
        self.world = self.build_world(scenario)
        # A scenario that names a domain runs with that pack's handlers,
        # default policy and upkeep; without one nothing below changes
        self.domain: DomainPack | None = (
            load_domain(scenario["domain"]) if scenario.get("domain") else None
        )
        self.policy = policy or self.choose_policy(scenario)
        # Each participant decides for the units it controls; the rest keep
        # the policy above (Formal Spec section 4, step 4)
        self.participants = Participants(
            scenario["runtime"].get("participants", []),
            self.world.entities.values(),
            lambda choice: build_policy(choice["name"], self.rng, choice.get("params")),
        )
        # A policy that names observer profiles decides from observations
        # only; it is never handed the world (development plan Phase 5)
        self.observers: dict[int, list[dict[str, Any]]] = {}
        for candidate in [self.policy] + [
            slot.policy for slot in self.participants.slots()
        ]:
            names = observer_names(candidate)
            if names:
                self.observers[id(candidate)] = [
                    load_observer_profile(name) for name in names
                ]
        self.observed: dict[int, dict[str, Any]] = {}
        # What a world policy reads: the live world, through glass
        self.world_view = WorldView(self.world)
        self.snapshots = SnapshotStore(SNAPSHOT_INTERVAL)
        self.scheduled = {
            (item["tick"], item["actor_id"]): item
            for item in scenario["runtime"].get("scheduled_actions", [])
        }

        assumptions = scenario["world_contract"].get("assumption_registry", {})

        # A policy that names itself (an outside system) is recorded as such
        self.actor_system_id = getattr(self.policy, "system_id", None) or (
            assumptions.get("actor_policy", type(self.policy).__name__)
        )

        # Every action goes through the resolver; the military line keeps
        # move, attack, observe, supply and repair (development plan Phase 3)
        # Injected faults draw from their own generator, so stressing a plan
        # never shifts the draws the battle itself makes
        fault_seed = None if self.random_seed is None else f"faults:{self.random_seed}"
        self.resolver = ActionResolver(
            (
                self.domain.handlers()
                if self.domain
                else handlers_for(MILITARY_ACTION_TYPES)
            ),
            ActionContext(
                rng=self.rng,
                system_id=self.actor_system_id,
                fault_rng=random.Random(fault_seed),
            ),
        )

    def choose_policy(self, scenario: dict[str, Any]) -> AnyPolicy:
        """
        The policy when none was handed in: runtime.policy by registered
        name, else the domain's default, else the tactical reference — by
        name too, so the core never imports it (development plan Phase 6).
        """
        choice = scenario["runtime"].get("policy")
        if choice:
            return build_policy(choice["name"], self.rng, choice.get("params"))
        if self.domain:
            return self.domain.default_policy(scenario, self.rng)
        return build_policy("tactical_reference", self.rng)

    def upkeep(self) -> None:
        """
        The domain's start-of-tick actions (recovery and the like).

        Important:
        They go through the resolver like any action, so the world still
        changes only through consequences and every change is an event with
        the action's id. One the world refuses is simply not applied.
        """
        if self.domain is None:
            return
        for action in self.domain.upkeep(self.world):
            self.resolver.execute(self.world, action, f"{self.domain.name}_upkeep")

    def scheduled_action(self, actor_id: str, scheduled: dict[str, Any]) -> Action:
        """
        The Action an outside system ordered, with an id issued by this run.

        Important:
        Fields the order leaves out take their contract defaults, so an
        order only has to say what it wants done.
        """
        target = scheduled["target"]
        location = target.get("location")
        return Action(
            action_id=self.world.ids.action(),
            actor_id=actor_id,
            action_type=scheduled["action_type"],
            target=ActionTarget(
                entity_id=target.get("entity_id"),
                location=tuple(location) if isinstance(location, list) else location,
                system_id=target.get("system_id"),
            ),
            intent=scheduled.get("intent", ""),
            required_resources=dict(scheduled.get("required_resources", {})),
            expected_effect=scheduled.get("expected_effect", ""),
            risk_profile=dict(scheduled.get("risk_profile", {})),
            priority=scheduled.get("priority", "normal"),
            confidence=float(scheduled.get("confidence", 1.0)),
            metadata=dict(scheduled.get("metadata", {})),
        )

    def decider(self, actor: Any) -> tuple[AnyPolicy, str]:
        """The policy deciding for actor and the system id its decisions carry."""
        slot = self.participants.for_entity(actor.entity_id)
        if slot is None:
            return self.policy, self.actor_system_id
        return slot.policy, slot.system_id

    def decide(self, policy: AnyPolicy, actor: Any) -> Action | None:
        """
        What policy proposes for actor, as an Action this run has named.

        Important:
        A world policy reads the live world through a read-only view: any
        write raises (development plan Phase 6). An observing policy gets
        only its observations, built from the units at the end of every
        earlier tick plus the units as they are now, and answers with an
        order; the order passes its contract and the action id is issued
        here, as for an outside system's order.
        """
        profiles = self.observers.get(id(policy))
        if profiles is None:
            return cast(Policy, policy).decide_action(
                cast(WorldState, self.world_view),
                cast(Entity, self.world_view.view_of(actor)),
            )
        history = dict(self.observed)
        history[self.world.tick] = {
            entity_id: entity.snapshot()
            for entity_id, entity in self.world.entities.items()
        }
        viewpoint = {"faction": actor.faction, "actor_id": actor.entity_id}
        context = context_for(
            self.scenario, actor.faction, self.world.resources.snapshot()
        )
        observations = {
            profile["observer_id"]: observe(
                history, self.world.tick, profile, viewpoint, context
            )
            for profile in profiles
        }
        if getattr(policy, "observer_profiles", None):
            order = cast(MultiViewPolicy, policy).decide_from_observations(observations)
        else:
            order = cast(ObservingPolicy, policy).decide_from_observation(
                next(iter(observations.values()))
            )
        if order is None:
            return None
        return self.scheduled_action(actor.entity_id, validate_order(order))

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
        started_at = utc_now()
        max_ticks = int(self.scenario["runtime"].get("max_ticks", 10))
        termination_reason = "duration_limit_reached"

        initial_world_state = self.world.snapshot()
        self.snapshots.record(self.world.tick, initial_world_state)
        if self.observers:
            self.observed[self.world.tick] = initial_world_state["entities"]

        for _ in range(max_ticks):
            self.world.advance_time()

            if len(self.world.active_factions()) <= 1:
                termination_reason = "termination_condition_met"
                break

            self.upkeep()
            actors = list(self.world.active_entities())

            for actor in actors:
                if not actor.is_active():
                    continue

                # An action an outside system ordered for this tick replaces
                # the policy's decision; its events carry that system's id
                scheduled = self.scheduled.get((self.world.tick, actor.entity_id))
                deciding, decider_id = self.decider(actor)
                system_id = scheduled["system_id"] if scheduled else decider_id
                action = (
                    self.scheduled_action(actor.entity_id, scheduled)
                    if scheduled
                    else self.decide(deciding, actor)
                )

                if action is None:
                    self.world.record_event(
                        event_type="NO_ACTION",
                        actor_id=actor.entity_id,
                        system_id=decider_id,
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
                    system_id=system_id,
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
                consequence = self.resolver.execute(self.world, action, system_id)

                if not consequence.accepted:
                    self.world.record_event(
                        event_type="ACTION_REJECTED",
                        actor_id=action.actor_id,
                        system_id=system_id,
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
            end_of_tick = self.world.snapshot()
            self.snapshots.record(self.world.tick, end_of_tick)
            if self.observers:
                self.observed[self.world.tick] = end_of_tick["entities"]

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

        package = {
            "scenario_id": self.scenario["scenario_id"],
            "scenario_version": self.scenario["scenario_version"],
            "initial_world_state": initial_world_state,
            "final_world_state": final_world_state,
            "event_memory": event_memory,
            **evaluated,
        }
        package["reproducibility"] = self.reproducibility(started_at, utc_now())

        # The package is checked against its contract before it leaves the
        # engine; every derived output is built from it alone. Validation
        # normalises values (a whole-number score becomes 3.0), so the output
        # hash is taken over the validated package, the one callers receive.
        validated = validate_result_package(package)
        validated["reproducibility"]["output_hash"] = output_hash(validated)
        return validated

    def reproducibility(
        self, started_at: datetime, ended_at: datetime
    ) -> dict[str, Any]:
        """
        Formal Spec section 12: what it takes to rerun this run.

        Important:
        output_hash is a placeholder here; run() fills it in from the validated
        package. The block itself records when the run happened, which no rerun
        repeats, so it is never part of the output hash. run_id combines the
        start time and the input, so two runs of the same input stay
        distinguishable in a run registry.
        """
        inputs = input_hash(self.scenario, self.evaluation_profile)
        return {
            "run_id": f"run_{started_at:%Y%m%dT%H%M%S%fZ}_{inputs[:8]}",
            "scenario_id": self.scenario["scenario_id"],
            "scenario_version": self.scenario["scenario_version"],
            "random_seed_policy": self.seed_policy,
            "random_seed": self.random_seed,
            "runtime_version": RUNTIME_VERSION,
            "ruleset_version": ruleset_version(
                self.scenario, sorted(self.resolver.handlers)
            ),
            "input_hash": inputs,
            "output_hash": "0" * 64,
            "deterministic_replay_available": self.replayable,
            "run_metadata": {
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "compute_profile": f"python {platform.python_version()}",
                "operator_system": platform.platform(),
            },
        }

    def evaluate(self, termination_reason: str, event_count: int) -> dict[str, Any]:
        """
        Summarise how the run ended.

        Important:
        event_count is passed in rather than read from event memory, because
        this summary is built before SCENARIO_END is recorded and has to count
        that event too.
        """
        return build_evaluation_summary(self.world, termination_reason, event_count)


def utc_now() -> datetime:
    """The current time in UTC. Only the reproducibility block records it."""
    return datetime.now(timezone.utc)


def observer_names(policy: Any) -> tuple[str, ...]:
    """The observer profiles a policy decides from; empty for a world policy."""
    several = getattr(policy, "observer_profiles", None)
    if several:
        return tuple(several)
    single = getattr(policy, "observer_profile", None)
    return (single,) if single else ()
