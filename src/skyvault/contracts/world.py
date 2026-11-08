"""World Contract = the minimum a world must declare before it can be run."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, NonNegative, check
from .provenance import DataProvenance


class SpaceModelSpec(ContractModel):
    """
    How space exists in this world.

    Important:
    grid       needs width and height; positions are [x, y] cells.
    graph      needs nodes and edges [a, b]; distance counts hops.
    network    needs nodes and edges [a, b, weight]; distance sums weights.

    Graph and network positions are node ids. No other space type is accepted
    in schema 0.2, so a misspelt type fails instead of building nothing.
    """

    type: Literal["grid", "graph", "network"]
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    distance_model: Literal["chebyshev", "manhattan", "euclidean_floor"] | None = None
    nodes: list[NonEmptyStr] | None = None
    edges: list[list[str | float]] | None = None
    units: list[str] | None = None

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
        return self


class TimeModelSpec(ContractModel):
    """
    How time advances in this world.

    Important:
    tick           one step per tick.
    phase          each step moves time forward by phase_length units;
                   time_unit names the unit (for example "hours").
    event_driven   time jumps to the next scheduled event.
    """

    type: Literal["tick", "phase", "event_driven"]
    max_ticks: int | None = Field(default=None, gt=0)
    phase_length: int | None = Field(default=None, gt=0)
    time_unit: str | None = None
    max_duration: str | None = None

    @model_validator(mode="after")
    def _phase_has_length(self) -> "TimeModelSpec":
        if self.type == "phase" and self.phase_length is None:
            raise ValueError("a phase time_model needs phase_length")
        return self


class WorldContract(ContractModel):
    """
    World Contract = Formal Spec section 2.

    Important:
    Schema 0.2 makes the four Phase 2 elements required, as ADR 004 promised:
    entity_model, environment_state, resource_state and rule_set. Each may be
    empty, but a world has to say so. resource_state maps a resource id to a
    non-negative amount.

    The remaining optional elements become required with their phase.

    actor_slots          Phase 6
    failure_variables    Phase 9
    """

    world_id: NonEmptyStr
    world_scope: NonEmptyStr
    purpose: list[str]
    space_model: SpaceModelSpec
    time_model: TimeModelSpec
    assumption_registry: dict[str, Any]
    evaluation_targets: list[str]
    entity_model: dict[str, Any]
    environment_state: dict[str, Any]
    resource_state: dict[NonEmptyStr, NonNegative]
    rule_set: dict[str, Any]

    actor_slots: list[str] | None = None
    event_memory: dict[str, Any] | None = None
    data_provenance: DataProvenance | None = None
    failure_variables: list[str] | None = None


def validate_world_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a world contract. Raises ContractError when it breaks."""
    return check(WorldContract, "world_contract", data)
