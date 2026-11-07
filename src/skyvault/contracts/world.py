"""World Contract = the minimum a world must declare before it can be run."""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, check
from .provenance import DataProvenance


class SpaceModelSpec(ContractModel):
    """
    How space exists in this world.

    Important:
    A grid needs width and height; the engine cannot place or move anything
    without them. Other space types (district networks, airspace) arrive with
    Phase 2 and declare their own units.
    """

    type: NonEmptyStr
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    distance_model: Literal["chebyshev", "manhattan", "euclidean_floor"] | None = None
    units: list[str] | None = None

    @model_validator(mode="after")
    def _grid_has_bounds(self) -> "SpaceModelSpec":
        if self.type == "grid" and (self.width is None or self.height is None):
            raise ValueError("a grid space_model needs both width and height")
        return self


class TimeModelSpec(ContractModel):
    """How time advances in this world."""

    type: NonEmptyStr
    max_ticks: int | None = Field(default=None, gt=0)
    phase_length: str | None = None
    max_duration: str | None = None


class WorldContract(ContractModel):
    """
    World Contract = Formal Spec section 2.

    Important:
    The required fields are the ones every world declares today. The optional
    ones are section 2.2 elements no part of the engine models yet; each will
    become required when the phase that gives it meaning lands.

    entity_model, environment_state, resource_state, rule_set   Phase 2
    actor_slots                                                 Phase 6
    failure_variables                                           Phase 9
    """

    world_id: NonEmptyStr
    world_scope: NonEmptyStr
    purpose: list[str]
    space_model: SpaceModelSpec
    time_model: TimeModelSpec
    assumption_registry: dict[str, Any]
    evaluation_targets: list[str]

    entity_model: dict[str, Any] | None = None
    environment_state: dict[str, Any] | None = None
    resource_state: dict[str, Any] | None = None
    rule_set: dict[str, Any] | list[Any] | None = None
    actor_slots: list[str] | None = None
    event_memory: dict[str, Any] | None = None
    data_provenance: DataProvenance | None = None
    failure_variables: list[str] | None = None


def validate_world_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a world contract. Raises ContractError when it breaks."""
    return check(WorldContract, "world_contract", data)
