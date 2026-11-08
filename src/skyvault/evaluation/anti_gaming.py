"""Metric anti-gaming = catch a high score earned by an unreasonable plan.

Important:
Formal Spec section 16: a badly set evaluation teaches the system to game it.
Never acting keeps losses at zero; destroying everything wins fast; ignoring
risk keeps the visible score high. Each check below looks for one of those
patterns in what the run recorded.

A triggered check is always reported. It only costs score, and only counts as
gaming, when the profile lists its behaviour as forbidden: a profile that does
not care about stability may let a scorched-earth win stand.
"""

from collections import Counter
from collections.abc import Callable
from typing import Any

from .metrics import EvaluationContext, MetricValue

# What each check detects, Formal Spec section 16 names first
BEHAVIORS = {
    "inaction_penalty": "maximize_score_by_inaction",
    "stability_penalty": "sacrifice_long_term_stability_for_short_term_success",
    "risk_spike_penalty": "extreme_high_risk_optimization",
    "hidden_risk_penalty": "ignore_hidden_risk_to_improve_visible_score",
    "long_term_cost_penalty": "sacrifice_strategic_value_for_short_term_tactical_value",
}

# A score at or above this counts as a visible success worth hiding behind
VISIBLE_SUCCESS = 0.8
# A survivor at or below this share of its starting hp is critically damaged
CRITICAL_HP_SHARE = 0.25

Scores = dict[str, MetricValue]
Check = Callable[[EvaluationContext, Scores, float], tuple[float, bool]]


def _good(scores: Scores, name: str) -> bool:
    value = scores[name]
    return value.applicable and value.score >= VISIBLE_SUCCESS


def inaction(context: EvaluationContext, scores: Scores, threshold: float):
    """Share of own turns spent passing or waiting; triggered above threshold."""
    turns = context.own_turns()
    idle = [
        turn
        for turn in turns
        if turn["event_type"] == "NO_ACTION"
        or turn["data"].get("action_type") == "wait"
    ]
    share = len(idle) / len(turns) if turns else 0.0
    return share, share > threshold


def stability(context: EvaluationContext, scores: Scores, threshold: float):
    """stability_impact below threshold while the mission visibly succeeded."""
    value = scores["stability_impact"]
    triggered = value.applicable and value.score < threshold
    return value.score, triggered and _good(scores, "mission_success")


def risk_spike(context: EvaluationContext, scores: Scores, threshold: float):
    """The worst single tick: risk events against own entities per own entity."""
    if not context.own:
        return 0.0, False
    per_tick = Counter(event["time"] for event in context.risk_events_against_own())
    worst = max(per_tick.values(), default=0) / len(context.own)
    return worst, worst > threshold


def hidden_risk(context: EvaluationContext, scores: Scores, threshold: float):
    """Share of own survivors left critically damaged behind a visible success."""
    survivors = [
        entity_id
        for entity_id in context.own
        if context.is_active_at_end(entity_id) and context.initial_hp(entity_id) > 0
    ]
    critical = [
        entity_id
        for entity_id in survivors
        if context.final_hp(entity_id)
        <= CRITICAL_HP_SHARE * context.initial_hp(entity_id)
    ]
    share = len(critical) / len(survivors) if survivors else 0.0
    return share, share > threshold and _good(scores, "mission_success")


def long_term_cost(context: EvaluationContext, scores: Scores, threshold: float):
    """strategic_value below threshold while tactical_value visibly succeeded."""
    value = scores["strategic_value"]
    triggered = value.applicable and value.score < threshold
    return value.score, triggered and _good(scores, "tactical_value")


CHECKS: dict[str, Check] = {
    "inaction_penalty": inaction,
    "stability_penalty": stability,
    "risk_spike_penalty": risk_spike,
    "hidden_risk_penalty": hidden_risk,
    "long_term_cost_penalty": long_term_cost,
}


def detect_gaming(
    context: EvaluationContext, scores: Scores, profile: dict[str, Any]
) -> dict[str, Any]:
    """
    Run every anti-gaming check the profile asks for.

    Returns the Formal Spec section 16 fields of the profile, then one entry
    per check (its value, threshold, whether it triggered, the behaviour, and
    the penalty actually applied), the behaviours flagged as gaming, and the
    total penalty.
    """
    forbidden = set(profile["forbidden_optimization_behaviors"])
    checks = []

    for spec in profile["anti_gaming_metrics"]:
        name = spec["metric"]
        value, triggered = CHECKS[name](context, scores, float(spec["threshold"]))
        behavior = BEHAVIORS[name]
        is_forbidden = behavior in forbidden
        checks.append(
            {
                "metric": name,
                "reason": spec["reason"],
                "value": round(value, 4),
                "threshold": spec["threshold"],
                "triggered": triggered,
                "behavior": behavior,
                "forbidden": is_forbidden,
                "penalty": spec["penalty"] if triggered and is_forbidden else 0.0,
            }
        )

    flagged = [check["behavior"] for check in checks if check["penalty"] > 0]
    return {
        "profile_id": profile["profile_id"],
        "primary_metric": profile["primary_metric"],
        "secondary_metrics": list(profile["secondary_metrics"]),
        "anti_gaming_metrics": [
            {"metric": spec["metric"], "reason": spec["reason"]}
            for spec in profile["anti_gaming_metrics"]
        ],
        "forbidden_optimization_behaviors": list(
            profile["forbidden_optimization_behaviors"]
        ),
        "tradeoff_report_required": profile["tradeoff_report_required"],
        "checks": checks,
        "triggered_behaviors": [c["behavior"] for c in checks if c["triggered"]],
        "flagged_behaviors": flagged,
        "gaming_detected": bool(flagged),
        "penalty_total": round(sum(check["penalty"] for check in checks), 4),
    }
