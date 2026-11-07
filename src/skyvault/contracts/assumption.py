"""Assumption Registry contract = what a scenario takes for granted, and how firmly."""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, Probability, check


class Assumption(ContractModel):
    """One assumption, with how much it is trusted and how much rides on it."""

    assumption_id: NonEmptyStr
    description: str
    category: NonEmptyStr
    value: Any
    confidence: Probability
    criticality: Literal["low", "medium", "high"]


class AssumptionRegistry(ContractModel):
    """
    Assumption Registry = Formal Spec section 11.2.

    Important:
    This is the structured registry a scenario carries at its top level. It is
    not world_contract.assumption_registry, which stays the flat name-to-value
    mapping of Formal Spec section 2.3 that the engine reads its actor_policy
    from. See ADR 004.

    assumption_confidence comes from the scenario grammar of section 3.3.
    """

    scenario_id: str | None = None
    assumptions: list[Assumption] = Field(default_factory=list)
    critical_assumptions: list[str] = Field(default_factory=list)
    assumption_risks: list[str] = Field(default_factory=list)
    assumption_confidence: dict[str, Probability] | None = None


def validate_assumption_registry(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an assumption registry. Raises ContractError when it breaks."""
    return check(AssumptionRegistry, "assumption_registry", data)
