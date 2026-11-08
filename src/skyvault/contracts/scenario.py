"""Scenario Grammar = how a task is written so SKYVAULT can run it."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .assumption import AssumptionRegistry
from .base import ContractModel, NonEmptyStr, check
from .entity import EntityRecord
from .provenance import DataProvenance
from .world import WorldContract


class RuntimeSettings(ContractModel):
    """How the run executes. Formal Spec section 3.3 calls this execution_settings."""

    max_ticks: int = Field(gt=0)
    random_seed: int
    deterministic_mode: bool = False
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"] | None = (
        None
    )
    repeat_count: int | None = Field(default=None, ge=1)


class ScenarioEvaluation(ContractModel):
    """
    What the run reports, and whose plan it is.

    Important:
    primary_metrics names the summary fields the run reports (event_count,
    winner_or_result...). How the run is scored is the evaluation profile's
    business. perspective is the faction whose plan is judged when the
    profile does not say; without it, the first entity's faction is used.
    """

    primary_metrics: list[str]
    failure_thresholds: list[str] = Field(default_factory=list)
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


class Scenario(ContractModel):
    """
    Scenario = Formal Spec section 3.

    Important:
    Version 0.5 keeps the flat layout every scenario already uses. Section 3.3
    groups the same information under identity / world_binding /
    initial_conditions; adopting that grouping is a schema version change, not
    a Phase 1 task. See ADR 004.

    schema_version names the contract the file was written against, so a
    reader can refuse a file it does not understand instead of misreading it.
    scenario_version is the content's own version and is unrelated.
    """

    schema_version: Literal["0.5"]
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
    allowed_actions: dict[str, Any] | None = None
    failure_exploration: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    version_control: VersionControl | None = None

    @model_validator(mode="after")
    def _entity_ids_are_unique(self) -> "Scenario":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.entity_id in seen:
                raise ValueError(f"duplicate entity_id {entity.entity_id!r}")
            seen.add(entity.entity_id)
        return self

    @model_validator(mode="after")
    def _version_control_names_this_version(self) -> "Scenario":
        control = self.version_control
        if control is not None and control.version != self.scenario_version:
            raise ValueError(
                f"version_control.version {control.version!r} is not "
                f"scenario_version {self.scenario_version!r}"
            )
        return self

    @model_validator(mode="after")
    def _entities_stand_in_the_space(self) -> "Scenario":
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


def validate_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a scenario. Raises ContractError when it breaks the contract."""
    return check(Scenario, "scenario", data)
