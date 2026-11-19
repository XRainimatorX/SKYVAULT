"""World service contract = Formal Spec section 10.4, as the service reports itself."""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, check

# Formal Spec 10.4 service_actions, in the spec's order
SERVICE_ACTIONS = (
    "receive_task",
    "create_world_instance",
    "run_scenario",
    "pause_world",
    "resume_world",
    "branch_world",
    "terminate_world",
    "archive_world",
    "export_result_package",
)
# Formal Spec 10.2 operation modes
OPERATION_MODES = (
    "standby",
    "triggered_scenario",
    "persistent_world",
    "batch_simulation",
    "monitoring",
    "replay",
    "failure_exploration",
)


class ServiceStatus(ContractModel):
    """What the service is doing and how well."""

    mode: Literal["standby", "running", "batch", "persistent", "failure_exploration"]
    health: Literal["normal", "degraded", "failed"]


class TaskIntake(ContractModel):
    """The task the service last took in (all null before the first)."""

    source_system: str | None
    task_type: str | None
    priority: str | None
    required_result_package: bool | None


class WorldInstanceRef(ContractModel):
    """The world instance the service last created or moved (null before one)."""

    world_id: NonEmptyStr
    scenario_id: NonEmptyStr
    lifecycle_state: NonEmptyStr


class WorldServiceContract(ContractModel):
    """
    world_service_contract = Formal Spec section 10.4, field by field.

    Important:
    service_status, task_intake, world_instance and service_actions are the
    section's own. operation_modes lists the section 10.2 modes the service
    offers and routes says, for each service action, the request that
    performs it.
    """

    service_status: ServiceStatus
    task_intake: TaskIntake
    world_instance: WorldInstanceRef | None
    service_actions: list[NonEmptyStr] = Field(min_length=len(SERVICE_ACTIONS))
    operation_modes: list[NonEmptyStr]
    routes: dict[NonEmptyStr, NonEmptyStr]


def validate_world_service_contract(data: dict[str, Any]) -> dict[str, Any]:
    """The service contract, or ContractError listing every violation."""
    return check(WorldServiceContract, "world_service_contract", data)
