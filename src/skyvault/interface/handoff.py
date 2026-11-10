"""Authority handoff = when a result needs a decision SKYVAULT may not make.

Important:
Pure. Four triggers (development plan Phase 12), each read from what the
run, the failure map or the conflict package already says:

    high_risk_outcome          Phase 7 flagged extreme_high_risk_optimization
                               (28% of 120 measured runs; "risky or fail"
                               would have been 94% — every run, not a signal)
    strategic_tradeoff         Phase 7 flagged a sacrifice of long-term
                               stability or strategic value for the short term
    conflicting_branches       a conflict package that requires a decision
    failure_threshold_crossed  a run that reached a scenario failure threshold,
                               or a failure map whose plan fails without
                               stress or already breaks at mild or moderate

The package never names a branch to take: skyvault_position states the
facts and the tests SKYVAULT recommends; may_execute_final_decision is
always false.
"""

import hashlib
import json
from typing import Any

from ..contracts import TRIGGERS, validate_authority_handoff
from ..contracts.base import is_skyvault

AUTHORITIES = ("NEXUS", "SOVEREIGN")
HIGH_RISK = "extreme_high_risk_optimization"
TRADEOFFS = (
    "sacrifice_long_term_stability_for_short_term_success",
    "sacrifice_strategic_value_for_short_term_tactical_value",
)
EARLY_BREAKS = ("mild", "moderate")
THRESHOLD_CAUSE = "Failure threshold reached"


def _flags(result: dict[str, Any] | None) -> set[str]:
    if result is None:
        return set()
    return set(result["evaluation_result"]["anti_gaming"]["flagged_behaviors"])


def map_crossed(failure_map: dict[str, Any]) -> bool:
    """The plan fails without stress, or some variable breaks it at mild or moderate."""
    baseline = failure_map["baseline"]
    if baseline["survival_rate"] < failure_map["survival_threshold"]:
        return True
    return any(v["breaking_level"] in EARLY_BREAKS for v in failure_map["variables"])


def handoff_triggers(
    result: dict[str, Any] | None = None,
    failure_map: dict[str, Any] | None = None,
    conflict_package: dict[str, Any] | None = None,
) -> list[str]:
    """Every trigger the inputs set off, in the order of TRIGGERS."""
    flags = _flags(result)
    fired = set()
    if HIGH_RISK in flags:
        fired.add("high_risk_outcome")
    if flags & set(TRADEOFFS):
        fired.add("strategic_tradeoff")
    if (
        conflict_package is not None
        and conflict_package["recommendation_to_nexus"]["required_decision"]
    ):
        fired.add("conflicting_branches")
    causes = result["evaluation_result"]["failure_causes"] if result else []
    if any(cause.startswith(THRESHOLD_CAUSE) for cause in causes) or (
        failure_map is not None and map_crossed(failure_map)
    ):
        fired.add("failure_threshold_crossed")
    return [t for t in TRIGGERS if t in fired]


def _summary(
    result: dict[str, Any] | None,
    failure_map: dict[str, Any] | None,
    conflict_package: dict[str, Any] | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if result is not None:
        verdict = result["evaluation_result"]
        summary["run"] = {
            "scenario_id": result["scenario_id"],
            "scenario_version": result["scenario_version"],
            "result": verdict["winner_or_result"],
            "status": verdict["overall_judgement"]["status"],
            "overall_score": verdict["overall_score"],
            "flagged_behaviors": sorted(_flags(result)),
            "failure_causes": list(verdict["failure_causes"][:5]),
            "output_hash": result["reproducibility"]["output_hash"],
        }
    if failure_map is not None:
        summary["failure_exploration"] = {
            "scenario_id": failure_map["scenario_id"],
            "baseline_survival_rate": failure_map["baseline"]["survival_rate"],
            "survival_threshold": failure_map["survival_threshold"],
            "crushing_variable": failure_map["crushing_variable"],
        }
    if conflict_package is not None:
        summary["conflict"] = {
            "conflict_id": conflict_package["conflict_id"],
            "conflict_type": list(conflict_package["conflict_type"]),
            "branches": [run["branch_id"] for run in conflict_package["branch_runs"]],
        }
    return summary


DECISIONS = {
    "high_risk_outcome": "accept or reject a plan SKYVAULT flagged for extreme risk",
    "strategic_tradeoff": (
        "accept or reject a short-term gain bought with long-term stability "
        "or strategic value"
    ),
    "conflicting_branches": "choose which conflicting orders to keep (one branch)",
    "failure_threshold_crossed": (
        "decide whether a plan that crosses its failure threshold may go ahead"
    ),
}


def authority_handoff(
    triggers: list[str],
    result: dict[str, Any] | None = None,
    branch_comparison: Any = None,
    failure_map: dict[str, Any] | None = None,
    conflict_package: dict[str, Any] | None = None,
    authorities: tuple[str, ...] = AUTHORITIES,
) -> dict[str, Any] | None:
    """
    The handoff package for triggers (None when nothing triggered).

    Important:
    handoff_id is named by content, so the same inputs always hand off the
    same package. The recommended tests are the run's own recommendations
    (Phase 7) or, for a failure map, the variables that break it.
    """
    if not triggers:
        return None
    summary = _summary(result, failure_map, conflict_package)
    tests = (
        list(result["evaluation_result"]["recommended_next_tests"]) if result else []
    )
    breaking = (
        {
            v["variable"]: v["breaking_level"]
            for v in failure_map["variables"]
            if v["breaking_level"]
        }
        if failure_map is not None
        else {}
    )
    tests += [
        f"stress {name} below {level}" for name, level in sorted(breaking.items())
    ]
    statement = "; ".join(f"{t}: {DECISIONS[t]}" for t in triggers)
    if conflict_package is not None:
        statement += (
            ". " + conflict_package["recommendation_to_nexus"]["decision_reason"]
        )
    package = {
        "handoff_id": "handoff_"
        + hashlib.sha256(
            json.dumps([triggers, summary], sort_keys=True).encode()
        ).hexdigest()[:16],
        "triggers": list(triggers),
        "result_summary": summary,
        "branch_comparison": branch_comparison,
        "failure_map": (
            {**summary["failure_exploration"], "breaking_levels": breaking}
            if failure_map is not None
            else None
        ),
        "required_decision": "; ".join(DECISIONS[t] for t in triggers),
        "skyvault_position": {
            "statement": (
                f"SKYVAULT simulated and recommends; it does not decide. {statement}"
            ),
            "recommended_next_tests": tests,
        },
        "may_recommend": True,
        "may_execute_final_decision": False,
        "decision_authority": list(authorities),
        "status": "awaiting_decision",
        "decided_by": None,
        "decision": None,
    }
    return validate_authority_handoff(package)


def decide(handoff: dict[str, Any], decided_by: str, decision: str) -> dict[str, Any]:
    """
    Record an authority's decision; anyone else is refused (PermissionError),
    and SKYVAULT always is, even named in the list (Final Authority Boundary).
    """
    if is_skyvault(decided_by):
        raise PermissionError(
            f"{decided_by} never decides: SKYVAULT simulates, recommends and warns"
        )
    if decided_by not in handoff["decision_authority"]:
        raise PermissionError(
            f"{decided_by} is not a decision authority for {handoff['handoff_id']}"
        )
    if handoff["status"] == "decided":
        raise ValueError(
            f"{handoff['handoff_id']} was already decided by {handoff['decided_by']}"
        )
    return validate_authority_handoff(
        {**handoff, "status": "decided", "decided_by": decided_by, "decision": decision}
    )
