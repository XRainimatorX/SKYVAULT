"""Scenario Grammar = how a task is written so SKYVAULT can run it."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .assumption import AssumptionRegistry
from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check
from .entity import EntityRecord
from .failure import FailureExplorationSpec, FailureVariableName
from .failure import RunPolicy as RunPolicyRequest
from .order import Order
from .provenance import DataProvenance
from .world import WorldContract


class ScheduledAction(Order):
    """
    An order an outside system gives one actor for one tick.

    Important:
    At that tick the actor carries it out instead of asking its policy. The
    action id is still issued by the run, so ids stay deterministic; the
    ordering system is recorded as source.system_id on every event it
    causes. Batch branches use this to play out conflicting orders.
    """

    tick: int = Field(ge=1)
    actor_id: NonEmptyStr
    system_id: NonEmptyStr


class PolicyChoice(ContractModel):
    """
    The registered policy a run uses, by name, with its parameters.

    Important:
    Only names registered with skyvault.policies can be chosen here, so a
    scenario file can pick a policy but never load arbitrary code.
    """

    name: NonEmptyStr
    params: dict[str, Any] = Field(default_factory=dict)


class Controls(ContractModel):
    """Which units a participant decides for: whole factions, single units, or both."""

    factions: list[NonEmptyStr] = Field(default_factory=list)
    entity_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _controls_something(self) -> "Controls":
        if not (self.factions or self.entity_ids):
            raise ValueError("a participant controls at least one faction or unit")
        return self


class Participant(ContractModel):
    """
    One actor slot (Formal Spec section 4, step 4): a registered policy and
    the units it decides for. Units no participant controls keep the run's
    default policy.
    """

    participant_id: NonEmptyStr
    policy: PolicyChoice
    controls: Controls


class RuntimeSettings(ContractModel):
    """How the run executes. Formal Spec section 3.3 calls this execution_settings."""

    max_ticks: int = Field(gt=0)
    random_seed: int
    deterministic_mode: bool = False
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"] | None = (
        None
    )
    repeat_count: int | None = Field(default=None, ge=1)
    scheduled_actions: list[ScheduledAction] = Field(default_factory=list)
    policy: PolicyChoice | None = None
    participants: list[Participant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_participants(self) -> "RuntimeSettings":
        ids = [p.participant_id for p in self.participants]
        if len(set(ids)) != len(ids):
            raise ValueError("participant_id must be unique")
        return self


class ScenarioEvaluation(ContractModel):
    """
    What the run reports, and whose plan it is.

    Important:
    primary_metrics names the summary fields the run reports (event_count,
    winner_or_result...). How the run is scored is the evaluation profile's
    business. perspective is the faction whose plan is judged when the
    profile does not say; without it, the first entity's faction is used.
    success_outcomes names the results (winner_or_result) that count as the
    mission achieved in a world with no opposing faction (Phase 14).
    """

    primary_metrics: list[str]
    failure_thresholds: list[str] = Field(default_factory=list)
    success_outcomes: list[NonEmptyStr] | None = None
    secondary_metrics: list[str] | None = None
    anti_gaming_metrics: list[str] | None = None
    comparison_targets: list[str] | None = None
    perspective: NonEmptyStr | None = None


class ChangedFromPrevious(ContractModel):
    """Formal Spec section 11: what moved since the parent version, by kind."""

    assumptions_changed: list[str] = Field(default_factory=list)
    data_changed: list[str] = Field(default_factory=list)
    rules_changed: list[str] = Field(default_factory=list)
    metrics_changed: list[str] = Field(default_factory=list)
    failure_variables_changed: list[str] = Field(default_factory=list)


class VersionControl(ContractModel):
    """
    Formal Spec section 11 scenario_version_control.

    Important:
    version must equal the scenario's own scenario_version, so the two can
    never tell different stories. parent_version is null for a first version.
    """

    version: NonEmptyStr
    parent_version: NonEmptyStr | None
    changed_from_previous: ChangedFromPrevious
    change_reason: str


class CompiledScenario(ContractModel):
    """
    A scenario compiled for the engine (Formal Spec section 4, step 2).

    Important:
    This is not a file format. SKYVAULT reads scenarios only in the section
    3.3 grammar (Scenario below); compile_scenario joins one with its world
    contract and writes this flat form, which is what the engine, the batch
    runner and failure exploration work on. schema_version is the grammar
    version the scenario was compiled from.
    """

    schema_version: Literal["1.0"]
    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    world_contract: WorldContract
    entities: list[EntityRecord] = Field(min_length=1)
    runtime: RuntimeSettings
    evaluation: ScenarioEvaluation

    scenario_type: str | None = None
    domain: str | None = None
    purpose: str | None = None
    assumption_registry: AssumptionRegistry | None = None
    data_provenance: DataProvenance | None = None
    participants: dict[str, Any] | None = None
    allowed_actions: "AllowedActions | None" = None
    failure_exploration: FailureExplorationSpec | None = None
    output: "OutputSettings | None" = None
    version_control: VersionControl | None = None
    world_binding: "WorldBinding | None" = None
    initial_conditions: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _entity_ids_are_unique(self) -> "CompiledScenario":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.entity_id in seen:
                raise ValueError(f"duplicate entity_id {entity.entity_id!r}")
            seen.add(entity.entity_id)
        return self

    @model_validator(mode="after")
    def _scheduled_actions_fit_the_run(self) -> "CompiledScenario":
        ids = {entity.entity_id for entity in self.entities}
        seen: set[tuple[int, str]] = set()
        for scheduled in self.runtime.scheduled_actions:
            if scheduled.actor_id not in ids:
                raise ValueError(
                    f"scheduled action for unknown actor {scheduled.actor_id!r}"
                )
            if scheduled.tick > self.runtime.max_ticks:
                raise ValueError(
                    f"scheduled action at tick {scheduled.tick} is after max_ticks"
                )
            key = (scheduled.tick, scheduled.actor_id)
            if key in seen:
                raise ValueError(
                    f"{scheduled.actor_id!r} has two scheduled actions "
                    f"at tick {scheduled.tick}"
                )
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _explores_only_declared_failures(self) -> "CompiledScenario":
        exploration = self.failure_exploration
        if exploration is None:
            return self
        declared = set(self.world_contract.failure_variables)
        undeclared = sorted(set(exploration.failure_variables) - declared)
        if undeclared:
            raise ValueError(
                f"failure_exploration names {undeclared}, which the world contract "
                "does not list in failure_variables"
            )
        return self

    @model_validator(mode="after")
    def _version_control_names_this_version(self) -> "CompiledScenario":
        control = self.version_control
        if control is not None and control.version != self.scenario_version:
            raise ValueError(
                f"version_control.version {control.version!r} is not "
                f"scenario_version {self.scenario_version!r}"
            )
        return self

    @model_validator(mode="after")
    def _entities_stand_in_the_space(self) -> "CompiledScenario":
        """
        A grid entity needs an [x, y] cell inside the grid; a graph or network
        entity needs the id of one of its nodes.
        """
        space = self.world_contract.space_model
        nodes = set(space.nodes or [])

        for entity in self.entities:
            position = entity.position
            if position is None:
                continue

            if space.type == "grid":
                inside = (
                    isinstance(position, list)
                    and 0 <= position[0] < (space.width or 0)
                    and 0 <= position[1] < (space.height or 0)
                )
            else:
                inside = isinstance(position, str) and position in nodes

            if not inside:
                raise ValueError(
                    f"entity {entity.entity_id!r} at {position!r} is outside "
                    f"the {space.type} space"
                )
        return self


def validate_compiled_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a compiled scenario. Raises ContractError when it breaks."""
    return check(CompiledScenario, "scenario", data)


# ── the section 3.3 grammar ──────────────────────────────────────────────────


class Identity(ContractModel):
    """Section 3.3 identity. schema_version names the grammar the file is written in."""

    scenario_id: NonEmptyStr
    scenario_type: str
    domain: str
    purpose: str
    scenario_version: NonEmptyStr
    schema_version: Literal["1.0"]


class WorldBinding(ContractModel):
    """
    Section 3.3 world_binding: which world the scenario runs in.

    Important:
    world_contract_id names a world contract document; environment_profile
    and rule_profile name one of its profiles, "baseline" meaning the world
    as written.
    """

    world_contract_id: NonEmptyStr
    environment_profile: NonEmptyStr = "baseline"
    rule_profile: NonEmptyStr = "baseline"


class InitialConditions(ContractModel):
    """
    Section 3.3 initial_conditions.

    Important:
    resources set the starting amount of named world resources (replacing the
    world's own). risks, constraints and uncertainty are recorded with the
    run and handed to evaluation and to the participants' decision context.
    """

    entities: list[EntityRecord] = Field(min_length=1)
    resources: dict[NonEmptyStr, NonNegative] = Field(default_factory=dict)
    risks: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)


class SlotOrder(Order):
    """An order a slot gives one actor at one tick (system_id defaults to the slot)."""

    tick: int = Field(ge=1)
    actor_id: NonEmptyStr
    system_id: NonEmptyStr | None = None


class Slot(ContractModel):
    """
    One actor slot of section 3.3 participants.

    Important:
    A slot decides through a registered policy, through orders for given
    ticks, or both. A policy slot with controls decides for those factions
    or units; a policy slot without controls decides for every unit no other
    slot controls (at most one may). Orders are carried out at their tick
    instead of asking any policy.
    """

    slot_id: NonEmptyStr
    description: str = ""
    policy: PolicyChoice | None = None
    controls: Controls | None = None
    orders: list[SlotOrder] = Field(default_factory=list)

    @model_validator(mode="after")
    def _slot_decides(self) -> "Slot":
        if self.policy is None and not self.orders:
            raise ValueError(f"slot {self.slot_id!r} has neither a policy nor orders")
        if self.controls is not None and self.policy is None:
            raise ValueError(f"slot {self.slot_id!r} controls units but has no policy")
        return self


class Participants(ContractModel):
    """Section 3.3 participants: who may enter the world and act in it."""

    human_decision_slots: list[Slot] = Field(default_factory=list)
    ai_agent_slots: list[Slot] = Field(default_factory=list)
    system_slots: list[Slot] = Field(default_factory=list)
    equipment_profiles: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _slots_are_sound(self) -> "Participants":
        slots = [*self.human_decision_slots, *self.ai_agent_slots, *self.system_slots]
        ids = [slot.slot_id for slot in slots]
        if len(set(ids)) != len(ids):
            raise ValueError("slot_id must be unique across all slots")
        for slot in self.human_decision_slots:
            if slot.policy is not None:
                raise ValueError(
                    f"human slot {slot.slot_id!r} decides by orders, not a policy"
                )
        for slot in self.ai_agent_slots:
            if slot.policy is None:
                raise ValueError(f"ai agent slot {slot.slot_id!r} needs a policy")
        defaults = [s.slot_id for s in slots if s.policy and s.controls is None]
        if len(defaults) > 1:
            raise ValueError(f"only one slot may decide by default, got {defaults}")
        return self


class AllowedActions(ContractModel):
    """
    Section 3.3 allowed_actions.

    Important:
    action_types lists what may be attempted in this scenario (empty: every
    registered type). actor_permissions narrows it for an entity id or a
    faction: {"red_01": ["move", "observe"]}. An action outside either is
    rejected at validation with a reason, never carried out.
    """

    action_types: list[NonEmptyStr] = Field(default_factory=list)
    actor_permissions: dict[NonEmptyStr, list[NonEmptyStr]] = Field(
        default_factory=dict
    )


class ExecutionSettings(ContractModel):
    """
    Section 3.3 execution_settings.

    Important:
    time_mode must be the world's time_model type. duration_limit is how
    many steps the run may take, as an integer or "40_ticks". random_seed is
    the seed a fixed or controlled_random run starts from.
    """

    time_mode: NonEmptyStr
    duration_limit: int | str
    repeat_count: int = Field(default=1, ge=1)
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"]
    deterministic_mode: bool = False
    random_seed: int | None = None

    @model_validator(mode="after")
    def _seeded(self) -> "ExecutionSettings":
        if self.random_seed_policy != "stochastic" and self.random_seed is None:
            raise ValueError(f"a {self.random_seed_policy} run needs random_seed")
        return self


class StressLevels(ContractModel):
    """
    Section 3.3 stress_levels: the levels to run, each with magnitudes that
    replace the failure engine's own for named variables ({} keeps them).
    A level left out (null) is not run.
    """

    mild: dict[FailureVariableName, NonNegative] | None = None
    moderate: dict[FailureVariableName, NonNegative] | None = None
    severe: dict[FailureVariableName, NonNegative] | None = None
    collapse: dict[FailureVariableName, NonNegative] | None = None


class ScenarioFailureExploration(ContractModel):
    """
    Section 3.3 failure_exploration.

    Important:
    enabled, failure_variables, stress_levels and branch_comparison are the
    section's own fields. objective, run_policy, alternatives and
    survival_threshold carry section 14.3's request so the scenario can be
    explored without a separate request.
    """

    enabled: bool = False
    failure_variables: list[FailureVariableName] = Field(default_factory=list)
    stress_levels: StressLevels = Field(default_factory=StressLevels)
    branch_comparison: bool = True
    objective: NonEmptyStr = "find_weakness"
    run_policy: RunPolicyRequest | None = None
    alternatives: list[NonEmptyStr] = Field(default_factory=list)
    survival_threshold: Probability = 0.5

    @model_validator(mode="after")
    def _enabled_names_something(self) -> "ScenarioFailureExploration":
        if self.enabled:
            if not self.failure_variables:
                raise ValueError("an enabled failure_exploration names variables")
            if all(
                getattr(self.stress_levels, level) is None
                for level in ("mild", "moderate", "severe", "collapse")
            ):
                raise ValueError("an enabled failure_exploration names stress_levels")
        return self


# what a run can be asked to hand back (section 3.3 output)
RequiredLog = Literal[
    "event_memory", "timeline", "causal_chain", "entity_history", "replay_state_at_tick"
]
RequiredReport = Literal[
    "evaluation_result",
    "score_breakdown",
    "tradeoff_report",
    "anti_gaming_report",
    "failure_map",
    "comparative_report",
    "briefing",
]


class OutputSettings(ContractModel):
    """
    Section 3.3 output: what the run must hand back.

    Important:
    required_logs and required_reports name result package parts
    (event_memory, timeline, causal_chain... / evaluation_result,
    tradeoff_report, failure_map...). replay_required makes the run fail
    when its result cannot be replayed; failure_map_required makes the
    service explore the scenario's failures along with the run.
    """

    required_logs: list[RequiredLog] = Field(default_factory=list)
    required_reports: list[RequiredReport] = Field(default_factory=list)
    replay_required: bool = True
    failure_map_required: bool = True


class Scenario(ContractModel):
    """
    Scenario = Formal Spec section 3.3, field by field.

    Important:
    The only scenario format SKYVAULT reads, from a file or over the API.
    A scenario is world scope (world_binding) + initial conditions +
    participants + limits + permissions + evaluation targets + end
    conditions + assumptions + failure variables (section 3.1).
    scenario_version_control is section 11.4. Nothing here builds a world:
    compile_scenario does, with the world contract it binds to.
    """

    identity: Identity
    world_binding: WorldBinding
    initial_conditions: InitialConditions
    assumption_registry: AssumptionRegistry
    data_provenance: DataProvenance
    participants: Participants
    allowed_actions: AllowedActions
    execution_settings: ExecutionSettings
    failure_exploration: ScenarioFailureExploration
    evaluation: ScenarioEvaluation
    output: OutputSettings
    scenario_version_control: "ScenarioVersionControl | None" = None

    @model_validator(mode="after")
    def _entity_ids_are_unique(self) -> "Scenario":
        seen: set[str] = set()
        for entity in self.initial_conditions.entities:
            if entity.entity_id in seen:
                raise ValueError(f"duplicate entity_id {entity.entity_id!r}")
            seen.add(entity.entity_id)
        return self

    @model_validator(mode="after")
    def _version_control_names_this_version(self) -> "Scenario":
        control = self.scenario_version_control
        if control is None:
            return self
        if control.version != self.identity.scenario_version:
            raise ValueError(
                f"scenario_version_control.version {control.version!r} is not "
                f"scenario_version {self.identity.scenario_version!r}"
            )
        if control.scenario_id != self.identity.scenario_id:
            raise ValueError("scenario_version_control.scenario_id is another scenario")
        return self


class ScenarioVersionControl(VersionControl):
    """Section 11.4 scenario_version_control, with the scenario it belongs to."""

    scenario_id: NonEmptyStr


CompiledScenario.model_rebuild()
Scenario.model_rebuild()


def validate_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a section 3.3 scenario. Raises ContractError when it breaks."""
    return check(Scenario, "scenario", data)
