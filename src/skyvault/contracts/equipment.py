"""Equipment contracts = what STAR GUARD submits and what the virtual test returns.

Important:
Formal Spec section 18. The section's physical_parameters do not carry
enough to judge stability or energy, so five optional fields are added
(base_width, footprint, load_bearing_joints, energy_capacity,
cooling_capacity) — see ADR 020. Every parameter is optional: a rule that
lacks what it needs says it cannot judge, it never passes by default.
"""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, NonNegative, Probability, check

Category = Literal["EXO", "PAX", "MSX", "ERX", "vehicle"]
Status = Literal["continue", "redesign", "reject", "require_external_simulation"]


class PhysicalParameters(ContractModel):
    """Mass with operator (kg), lengths (m), loads (kN), power (kW), energy (kWh)."""

    mass: NonNegative | None = None
    height: NonNegative | None = None
    center_of_gravity: NonNegative | None = None
    joint_load: NonNegative | None = None
    power_requirement: NonNegative | None = None
    heat_output: NonNegative | None = None
    endurance: NonNegative | None = None
    base_width: NonNegative | None = None
    footprint: NonNegative | None = None
    load_bearing_joints: int | None = Field(default=None, ge=1)
    energy_capacity: NonNegative | None = None
    cooling_capacity: NonNegative | None = None


class EngineeringParameters(ContractModel):
    material_complexity: Literal["low", "medium", "high", "exotic"] | None = None
    maintenance_time: NonNegative | None = None
    part_replacement_difficulty: Literal["easy", "moderate", "hard"] | None = None
    supply_chain_risk: Probability | None = None
    repair_environment_required: Literal["field", "depot", "factory"] | None = None


class OperationalParameters(ContractModel):
    operator_fatigue: Probability | None = None
    terrain_accessibility: list[NonEmptyStr] | None = None
    transport_requirement: (
        Literal["none", "truck", "heavy_truck", "heavy_lift", "aircraft"] | None
    ) = None
    deployment_time: NonNegative | None = None
    mission_role: (
        Literal["assault", "support", "recon", "logistics", "command"] | None
    ) = None


class EquipmentProfile(ContractModel):
    """
    One piece of equipment, before it is built (section 18).

    capabilities and state are the Phase 12 path: they are copied onto the
    replaced unit as they are, after the profile's own mapping.
    """

    equipment_id: NonEmptyStr
    category: str
    description: str = ""
    physical_parameters: PhysicalParameters = Field(default_factory=PhysicalParameters)
    engineering_parameters: EngineeringParameters = Field(
        default_factory=EngineeringParameters
    )
    operational_parameters: OperationalParameters = Field(
        default_factory=OperationalParameters
    )
    test_targets: list[NonEmptyStr] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class PhysicalPossibility(ContractModel):
    score: Probability
    warnings: list[str] = Field(default_factory=list)
    impossible_flags: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


class EngineeringFeasibility(ContractModel):
    score: Probability
    bottlenecks: list[str] = Field(default_factory=list)
    maintenance_risks: list[str] = Field(default_factory=list)
    components: dict[str, Any] = Field(default_factory=dict)


class TacticalUsefulness(ContractModel):
    score: Probability | None
    useful_contexts: list[str] = Field(default_factory=list)
    weak_contexts: list[str] = Field(default_factory=list)
    logistics_burden: Literal["low", "medium", "high", ""] = ""
    contexts: list[dict[str, Any]] = Field(default_factory=list)
    unit: dict[str, Any] = Field(default_factory=dict)


class EquipmentFailureExploration(ContractModel):
    failure_points: list[dict[str, Any]] = Field(default_factory=list)
    collapse_sequence: list[dict[str, Any]] = Field(default_factory=list)
    redesign_triggers: list[dict[str, Any]] = Field(default_factory=list)


class ExternalSimulation(ContractModel):
    required: bool
    reasons: list[str] = Field(default_factory=list)
    adapter: dict[str, Any] = Field(default_factory=dict)


class FinalJudgement(ContractModel):
    status: Status
    reason: NonEmptyStr


class EquipmentTestResult(ContractModel):
    """What the virtual test says about one profile (section 18)."""

    equipment_id: NonEmptyStr
    category: str
    physical_possibility: PhysicalPossibility
    engineering_feasibility: EngineeringFeasibility
    tactical_usefulness: TacticalUsefulness
    failure_exploration: EquipmentFailureExploration
    require_external_simulation: ExternalSimulation
    final_judgement: FinalJudgement
    surrogate: dict[str, Any] | None = None


def validate_equipment_profile(data: dict[str, Any]) -> dict[str, Any]:
    """An equipment profile, or ContractError listing every violation."""
    return check(EquipmentProfile, "equipment_profile", data)


def validate_equipment_test_result(data: dict[str, Any]) -> dict[str, Any]:
    """An equipment test result, or ContractError listing every violation."""
    return check(EquipmentTestResult, "equipment_test_result", data)
