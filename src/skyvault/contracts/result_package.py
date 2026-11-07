"""Result Package contract = everything one run hands back."""

from typing import Any

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, check
from .entity import EntityRecord
from .evaluation import EvaluationResult
from .event import EventRecord
from .reproducibility import ReproducibilityMetadata


class WorldSnapshot(ContractModel):
    """The whole world at one moment, as WorldState.snapshot() writes it."""

    world_id: NonEmptyStr
    scenario_id: NonEmptyStr
    tick: int = Field(ge=0)
    space: dict[str, Any]
    entities: dict[str, EntityRecord]
    assumptions: dict[str, Any] = Field(default_factory=dict)


class ResultPackage(ContractModel):
    """
    Result Package = one finished run.

    Important:
    evaluation_result is mandatory; a run without a verdict is not a result.
    The field was called evaluation before Phase 1 and was renamed to match the
    development plan's acceptance criterion and Formal Spec section 8.3. See
    ADR 004.

    The four derived outputs (timeline, replay, entity history, causal chain)
    are built from this package alone, so initial_world_state is required too.

    reproducibility stays optional until Phase 8 fills it.
    """

    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    initial_world_state: WorldSnapshot
    final_world_state: WorldSnapshot
    event_memory: list[EventRecord]
    evaluation_result: EvaluationResult
    reproducibility: ReproducibilityMetadata | None = None

    @model_validator(mode="after")
    def _event_count_matches_event_memory(self) -> "ResultPackage":
        counted = self.evaluation_result.event_count
        recorded = len(self.event_memory)
        if counted != recorded:
            raise ValueError(
                f"evaluation_result.event_count is {counted} "
                f"but event_memory holds {recorded} events"
            )
        return self


def validate_result_package(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a result package. Raises ContractError when it breaks."""
    return check(ResultPackage, "result_package", data)
