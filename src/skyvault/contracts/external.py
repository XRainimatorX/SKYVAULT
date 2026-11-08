"""External contracts = what outside systems submit, and what goes back for a decision.

Important:
Formal Spec section 9: SKYVAULT serves the other systems; it is not their
superior. Section 17: it may simulate, recommend, alert, reject an invalid
scenario and return a failure map, but it never makes the final decision.
An authority handoff is how a result is put in front of whoever decides:
may_recommend is always true, may_execute_final_decision always false.
"""

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyStr, check

SYSTEMS = (
    "NEXUS",
    "STARTX",
    "TAC_ANGEL",
    "EIDEN_01",
    "AEROGRID",
    "SKYFOX",
    "HADES",
    "CYBERHOUND",
    "STAR_GUARD",
)
System = Literal[
    "NEXUS",
    "STARTX",
    "TAC_ANGEL",
    "EIDEN_01",
    "AEROGRID",
    "SKYFOX",
    "HADES",
    "CYBERHOUND",
    "STAR_GUARD",
]
TRIGGERS = (
    "high_risk_outcome",
    "strategic_tradeoff",
    "conflicting_branches",
    "failure_threshold_crossed",
)
Trigger = Literal[
    "high_risk_outcome",
    "strategic_tradeoff",
    "conflicting_branches",
    "failure_threshold_crossed",
]
NAME = r"^[A-Za-z0-9_.+-]+(/[A-Za-z0-9_.+-]+)?$"


class ExternalSubmission(ContractModel):
    """
    One submission from an outside system, in that system's own terms.

    Important:
    kind says what it is; content is the system's own payload, which its
    adapter reads. The scenario is named, never a path.
    """

    system: System
    kind: Literal[
        "task",
        "actions",
        "branches",
        "intel",
        "environment",
        "equipment",
        "mission",
        "defence",
        "airspace",
    ]
    scenario: str | None = Field(default=None, pattern=NAME)
    content: dict[str, Any] = Field(default_factory=dict)


class SkyvaultPosition(ContractModel):
    """What SKYVAULT can say: the facts and the tests it recommends — never a pick."""

    statement: NonEmptyStr
    recommended_next_tests: list[str] = Field(default_factory=list)


class AuthorityHandoff(ContractModel):
    """A result put in front of the authority that decides (Formal Spec section 17)."""

    handoff_id: NonEmptyStr
    triggers: list[Trigger] = Field(min_length=1)
    result_summary: dict[str, Any]
    branch_comparison: Any = None
    failure_map: dict[str, Any] | None = None
    required_decision: NonEmptyStr
    skyvault_position: SkyvaultPosition
    may_recommend: Literal[True] = True
    may_execute_final_decision: Literal[False] = False
    decision_authority: list[NonEmptyStr] = Field(min_length=1)
    status: Literal["awaiting_decision", "decided"] = "awaiting_decision"
    decided_by: NonEmptyStr | None = None
    decision: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _decided_by_an_authority(self) -> "AuthorityHandoff":
        if (self.status == "decided") != (self.decided_by is not None):
            raise ValueError("decided_by is given exactly when the handoff is decided")
        if (
            self.decided_by is not None
            and self.decided_by not in self.decision_authority
        ):
            raise ValueError("only a decision authority can decide")
        return self


def validate_external_submission(data: dict[str, Any]) -> dict[str, Any]:
    """An external submission, or ContractError listing every violation."""
    return check(ExternalSubmission, "external_submission", data)


def validate_authority_handoff(data: dict[str, Any]) -> dict[str, Any]:
    """An authority handoff package, or ContractError listing every violation."""
    return check(AuthorityHandoff, "authority_handoff", data)
