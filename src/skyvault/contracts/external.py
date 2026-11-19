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

from .base import Authority, ContractModel, NonEmptyStr, check

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
    """
    Formal Spec 17.2 skyvault_position: SKYVAULT may recommend and may never
    execute the final decision. statement and recommended_next_tests say what
    it recommends — the facts and the tests, never a pick.
    """

    may_recommend: Literal[True] = True
    may_execute_final_decision: Literal[False] = False
    statement: NonEmptyStr
    recommended_next_tests: list[str] = Field(default_factory=list)


class PackageToNexus(ContractModel):
    """Formal Spec 17.2 package_to_nexus: what the deciding authority reads."""

    result_summary: Any
    branch_comparison: Any = None
    failure_map: Any = None
    required_decision: NonEmptyStr


class AuthorityHandoff(ContractModel):
    """
    Authority Handoff = Formal Spec section 17.2, field by field.

    Important:
    scenario_id, handoff_required, reason, package_to_nexus and
    skyvault_position are the section's own. handoff_id names the package by
    its content; decision_authority, status, decided_by and decision record
    who may decide and who did.
    """

    scenario_id: NonEmptyStr
    handoff_required: Literal[True] = True
    reason: list[Trigger] = Field(min_length=1)
    package_to_nexus: PackageToNexus
    skyvault_position: SkyvaultPosition
    handoff_id: NonEmptyStr
    decision_authority: list[Authority] = Field(min_length=1)
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


class MissionPlan(ContractModel):
    """
    One plan a mission tries: orders (scheduled actions), unit changes and
    rule changes on the mission's world. system_id names who wrote it
    (NEXUS, or STARTX / TAC ANGEL in the triangle loop).
    """

    plan_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = ""
    system_id: NonEmptyStr | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    entity_changes: dict[str, dict[str, Any]] | None = None
    rule_changes: dict[str, dict[str, Any]] | None = None


class NexusMission(ContractModel):
    """
    What NEXUS hands SKYVAULT when an order needs a world (Formal Spec 21
    Phase I: NEXUS command interface).

    Important:
    order is 陛下's order as NEXUS received it, kept word for word: it
    becomes each compiled scenario's purpose. compare_plans needs at least
    two plans and test_plan at most one; every objective but report_status
    names the world (scenario) it runs in.
    """

    mission_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    order: NonEmptyStr
    objective: Literal[
        "compare_plans", "test_plan", "stress_test", "explore_failures", "report_status"
    ]
    scenario: str | None = Field(default=None, pattern=NAME)
    plans: list[MissionPlan] = Field(default_factory=list)
    repeat_count: int | None = Field(default=None, ge=1)
    max_ticks: int | None = Field(default=None, ge=1)
    stress_level: Literal["mild", "moderate", "severe", "collapse"] = "severe"
    report_format: Literal["markdown", "none"] = "markdown"
    priority: Literal["low", "medium", "high", "urgent"] | None = None

    @model_validator(mode="after")
    def _plans_fit_the_objective(self) -> "NexusMission":
        if self.objective != "report_status" and self.scenario is None:
            raise ValueError(f"a {self.objective} mission names its scenario")
        if self.objective == "compare_plans" and len(self.plans) < 2:
            raise ValueError("compare_plans needs at least two plans")
        if self.objective in ("test_plan", "stress_test") and len(self.plans) > 1:
            raise ValueError(f"{self.objective} tries one plan at most")
        ids = [p.plan_id for p in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("plan ids must be unique")
        return self


def validate_nexus_mission(data: dict[str, Any]) -> dict[str, Any]:
    """A NEXUS mission with every default filled, or ContractError."""
    check(NexusMission, "nexus_mission", data)
    full: dict[str, Any] = NexusMission.model_validate(data).model_dump(mode="json")
    return full
