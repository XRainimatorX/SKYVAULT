"""Consequence contract = what resolving an action did to the world."""

from typing import Any

from pydantic import Field

from .base import ContractModel, NonEmptyStr, check


class ConsequenceRecord(ContractModel):
    """
    Consequence = the result of resolving one action.

    Important:
    direct_effects stays a list of effect records, which is what the engine
    produces today. Formal Spec section 6.3 groups effects into state, resource
    and entity changes and adds secondary effects and chain reactions; those
    arrive with the Phase 3 action framework, so they are optional here.
    """

    action_id: NonEmptyStr
    accepted: bool
    reason: str
    direct_effects: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_impact: dict[str, Any] = Field(default_factory=dict)

    secondary_effects: dict[str, Any] | None = None
    chain_reactions: list[dict[str, Any]] | None = None


def validate_consequence(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one consequence. Raises ContractError when it breaks the contract."""
    return check(ConsequenceRecord, "consequence", data)
