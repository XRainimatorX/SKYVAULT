"""World Contract = the minimum a world must declare before it can be run.

Important:
Formal Spec section 2. A world contract is its own document, kept under
data/worlds/<world_id>.json; a scenario binds to it by world_contract_id
(section 3.3 world_binding) and the scenario compiler joins the two.
"""

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, NonNegative, check
from .failure import FailureVariableName

# "6_hours", "14_days", "40_ticks": an amount and a unit, as section 2.3 writes them
DURATION = re.compile(r"^(\d+)_(ticks|minutes|hours|days)$")
Duration = int | str


def parse_duration(value: Duration) -> tuple[int, str | None]:
    """(amount, unit) of a duration written as an integer or "6_hours"."""
    if isinstance(value, int):
        return value, None
    found = DURATION.match(value)
    if found is None:
        raise ValueError(
            f"{value!r} is not a duration: write an integer or <n>_<unit> "
            "(ticks, minutes, hours, days)"
        )
    return int(found.group(1)), found.group(2)


def _positive_duration(value: Duration | None, name: str) -> None:
    if value is None:
        return
    amount, _ = parse_duration(value)
    if amount <= 0:
        raise ValueError(f"{name} must be positive")


class SpaceModelSpec(ContractModel):
    """
    How space exists in this world.

    Important:
    grid               needs width and height; positions are [x, y] cells.
    graph              needs nodes and edges [a, b]; distance counts hops.
    network            needs nodes and edges [a, b, weight]; distance sums weights.
    district_network   a network of city districts, road nodes, facilities and
                       supply points (section 2.3): nodes and weighted edges,
                       and units naming the kinds of node it holds.

    Graph and network positions are node ids. No other space type is accepted,
    so a misspelt type fails instead of building nothing.
    """

    type: Literal["grid", "graph", "network", "district_network"]
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    distance_model: Literal["chebyshev", "manhattan", "euclidean_floor"] | None = None
    nodes: list[NonEmptyStr] | None = None
    edges: list[list[str | float]] | None = None
    units: list[str] | None = None
    node_units: dict[str, str] | None = None

    @model_validator(mode="after")
    def _space_is_complete(self) -> "SpaceModelSpec":
        if self.type == "grid":
            if self.width is None or self.height is None:
                raise ValueError("a grid space_model needs both width and height")
            return self

        if self.nodes is None or self.edges is None:
            raise ValueError(f"a {self.type} space_model needs nodes and edges")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("space_model nodes must be unique")

        size = 2 if self.type == "graph" else 3
        known = set(self.nodes)
        for edge in self.edges:
            if len(edge) != size:
                raise ValueError(f"a {self.type} edge has {size} items, got {edge!r}")
            for endpoint in edge[:2]:
                if not isinstance(endpoint, str) or endpoint not in known:
                    raise ValueError(f"edge {edge!r} names an unknown node")
            if size == 3:
                weight = edge[2]
                if isinstance(weight, str) or weight <= 0:
                    raise ValueError(f"edge {edge!r} needs a positive weight")

        if self.type == "district_network":
            if not self.units:
                raise ValueError("a district_network names its units (kinds of node)")
            kinds = self.node_units or {}
            unknown = sorted(set(kinds) - known)
            if unknown:
                raise ValueError(f"node_units names unknown nodes {unknown}")
            strange = sorted({kind for kind in kinds.values()} - set(self.units))
            if strange:
                raise ValueError(f"node_units uses kinds {strange} not in units")
        return self


class TimeModelSpec(ContractModel):
    """
    How time advances in this world (section 2.2: tick, phase, event-driven,
    long-duration).

    Important:
    tick                 one step per tick.
    phase                each step moves time forward by phase_length.
    event_driven         time jumps to the next scheduled event.
    phase_event_hybrid   fixed phases, and inside a phase time jumps to each
                         scheduled event (section 2.3's city crisis).
    long_duration        phases measured in days over a long horizon.

    phase_length and max_duration may be written as section 2.3 does
    ("6_hours", "14_days") or as integers with time_unit.
    """

    type: Literal[
        "tick", "phase", "event_driven", "phase_event_hybrid", "long_duration"
    ]
    max_ticks: int | None = Field(default=None, gt=0)
    phase_length: Duration | None = None
    time_unit: str | None = None
    max_duration: Duration | None = None

    @model_validator(mode="after")
    def _phase_has_length(self) -> "TimeModelSpec":
        _positive_duration(self.phase_length, "phase_length")
        _positive_duration(self.max_duration, "max_duration")
        phased = ("phase", "phase_event_hybrid", "long_duration")
        if self.type in phased and self.phase_length is None:
            raise ValueError(f"a {self.type} time_model needs phase_length")
        if self.type == "long_duration" and self.max_duration is None:
            raise ValueError("a long_duration time_model needs max_duration")
        return self


class WorldProvenance(ContractModel):
    """Where the world's data came from (section 2.3 data_provenance)."""

    source_type: NonEmptyStr
    source_quality: Literal["low", "medium", "high"]
    timestamp: str = ""
    version: str = ""


class WorldProfiles(ContractModel):
    """
    Named variations of the world a scenario can bind to (section 3.3
    world_binding.environment_profile and rule_profile).

    Important:
    Each profile is a partial environment_state or rule_set laid over the
    world's own (nested keys replace, others stay). "baseline" is the world
    as written and is never declared here.
    """

    environment: dict[NonEmptyStr, dict[str, Any]] = Field(default_factory=dict)
    rules: dict[NonEmptyStr, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _baseline_is_reserved(self) -> "WorldProfiles":
        for kind, named in (("environment", self.environment), ("rules", self.rules)):
            if "baseline" in named:
                raise ValueError(f"{kind} profile 'baseline' is the world itself")
        return self


class WorldContract(ContractModel):
    """
    World Contract = Formal Spec section 2.

    Important:
    Every one of the thirteen elements of section 2.2 is required: world_scope,
    space_model, time_model, entity_model, environment_state, resource_state,
    rule_set, actor_slots, event_memory, evaluation_targets,
    assumption_registry, data_provenance and failure_variables. Each may be
    empty where the world has nothing to say, but it has to say so.
    world_id and purpose come from section 2.3. resource_state maps a
    resource id to a non-negative amount. failure_variables are the ways this
    world can be deliberately made worse; a scenario's failure exploration
    may only choose among them.
    """

    world_id: NonEmptyStr
    world_scope: NonEmptyStr
    purpose: list[str]
    space_model: SpaceModelSpec
    time_model: TimeModelSpec
    entity_model: dict[str, Any]
    environment_state: dict[str, Any]
    resource_state: dict[NonEmptyStr, NonNegative]
    rule_set: dict[str, Any]
    actor_slots: list[NonEmptyStr]
    event_memory: dict[str, Any]
    evaluation_targets: list[str]
    assumption_registry: dict[str, Any]
    data_provenance: WorldProvenance
    failure_variables: list[FailureVariableName]

    profiles: WorldProfiles | None = None


def validate_world_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a world contract. Raises ContractError when it breaks."""
    return check(WorldContract, "world_contract", data)
