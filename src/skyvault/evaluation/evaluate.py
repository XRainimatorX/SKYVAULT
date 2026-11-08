"""Evaluate a run = the multi-axis verdict, from what the run recorded."""

import copy
from typing import Any

from .anti_gaming import detect_gaming
from .metrics import METRIC_REGISTRY, EvaluationContext, MetricValue
from .tradeoff import build_tradeoff_report

# Below this, risk_growth alone makes a plan risky
RISKY_RISK_GROWTH = 0.5

KNOWN_FAILURE_THRESHOLDS = ("all_entities_destroyed", "perspective_eliminated")


def evaluate_run(
    initial_world_state: dict[str, Any],
    event_memory: list[dict[str, Any]],
    final_world_state: dict[str, Any],
    summary: dict[str, Any],
    profile: dict[str, Any],
    max_ticks: int | None,
    failure_thresholds: list[str] | None = None,
    success_outcomes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Judge one finished run under one profile.

    Returns {evaluation_result, score_breakdown, anti_gaming_report,
    tradeoff_report}.

    Important:
    This is a pure function of its inputs: it never changes them, and the same
    inputs always give the same verdict. summary is the run-end summary the
    engine already recorded in SCENARIO_END; evaluation_result keeps every
    field of it and adds the multi-axis verdict.

    overall_judgement.status, checked in this order:

    fail             overall below the fail threshold, mission_success 0, or a
                     scenario failure threshold reached
    risky            a forbidden gaming behaviour, or risk_growth below 0.5
    pass             overall at or above the pass threshold
    needs_more_test  anything else

    confidence is the weight of the axes that had data over all weight.

    A world with no opposing faction (a city) has nothing for
    mission_success to measure; when the scenario names its success_outcomes,
    mission_success is 1 for a run whose winner_or_result is one of them and
    0 otherwise (Phase 14). A failure threshold is also reached when the run
    ended on a domain reason of that name (termination_condition_met:<name>).
    """
    perspective = profile["perspective"]
    if perspective is None:
        raise ValueError("the profile has no perspective; resolve it before evaluating")

    initial_world_state = copy.deepcopy(initial_world_state)
    event_memory = copy.deepcopy(event_memory)
    final_world_state = copy.deepcopy(final_world_state)

    context = EvaluationContext.build(
        initial_world_state, event_memory, final_world_state, perspective, max_ticks
    )
    values = {name: metric.compute(context) for name, metric in METRIC_REGISTRY.items()}
    if success_outcomes and not context.enemies:
        outcome = summary["winner_or_result"]
        achieved = 1.0 if outcome in success_outcomes else 0.0
        values["mission_success"] = MetricValue(
            raw=achieved,
            score=achieved,
            applicable=True,
            explanation=(
                f"outcome {outcome}; the scenario counts "
                f"{', '.join(success_outcomes)} as success"
            ),
        )
    weights = {name: float(profile["weights"].get(name, 0.0)) for name in values}
    breakdown = _score_breakdown(values, weights)

    counted = {n: w for n, w in weights.items() if w > 0 and values[n].applicable}
    total_weight = sum(w for w in weights.values() if w > 0)
    base = (
        sum(values[n].score * w for n, w in counted.items()) / sum(counted.values())
        if counted
        else 0.0
    )
    confidence = sum(counted.values()) / total_weight if total_weight else 0.0

    anti_gaming = detect_gaming(context, values, profile)
    overall = max(0.0, min(1.0, base - anti_gaming["penalty_total"]))

    reached, unevaluated = _failure_thresholds(
        context, failure_thresholds or [], summary["termination_reason"]
    )
    status = _status(values, overall, profile, anti_gaming, reached)

    judgement = {
        "scenario_id": initial_world_state["scenario_id"],
        "status": status,
        "confidence": round(confidence, 4),
        "overall_score": round(overall, 4),
    }
    evaluation_result = {
        **summary,
        "scenario_id": initial_world_state["scenario_id"],
        "profile_id": profile["profile_id"],
        "perspective": perspective,
        "overall_judgement": {"status": status, "confidence": judgement["confidence"]},
        "overall_score": judgement["overall_score"],
        "scores": {
            name: entry["score"]
            for name, entry in breakdown.items()
            if entry["applicable"]
        },
        "key_findings": list(summary["key_findings"])
        + _findings(breakdown, judgement, profile),
        "failure_causes": _failure_causes(
            context, breakdown, profile, anti_gaming, reached
        ),
        "recommended_next_tests": _next_tests(breakdown, anti_gaming, unevaluated),
        "comparison": {"better_than": [], "worse_than": []},
        "anti_gaming": {
            "gaming_detected": anti_gaming["gaming_detected"],
            "flagged_behaviors": list(anti_gaming["flagged_behaviors"]),
            "penalty_total": anti_gaming["penalty_total"],
        },
    }
    return {
        "evaluation_result": evaluation_result,
        "score_breakdown": breakdown,
        "anti_gaming_report": {"scenario_id": judgement["scenario_id"], **anti_gaming},
        "tradeoff_report": build_tradeoff_report(
            breakdown, anti_gaming, judgement, profile
        ),
    }


def _score_breakdown(
    values: dict[str, MetricValue], weights: dict[str, float]
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "score": round(value.score, 4),
            "raw": value.raw,
            "unit": METRIC_REGISTRY[name].unit,
            "weight": weights[name],
            "applicable": value.applicable,
            "description": METRIC_REGISTRY[name].description,
            "explanation": value.explanation,
        }
        for name, value in values.items()
    }


def _failure_thresholds(
    context: EvaluationContext, names: list[str], termination_reason: str = ""
) -> tuple[list[str], list[str]]:
    """
    (thresholds the run reached, thresholds this engine cannot evaluate).
    A domain pack that ends a run for a reason (termination_condition_met:
    <reason>) reaches the threshold of that name.
    """
    reached, unevaluated = [], []
    for name in names:
        if termination_reason == f"termination_condition_met:{name}":
            reached.append(name)
        elif name == "all_entities_destroyed":
            everyone = list(context.initial)
            if everyone and len(context.destroyed_at_end(everyone)) == len(everyone):
                reached.append(name)
        elif name == "perspective_eliminated":
            if context.own and not any(
                context.is_active_at_end(e) for e in context.own
            ):
                reached.append(name)
        else:
            unevaluated.append(name)
    return reached, unevaluated


def _status(
    values: dict[str, MetricValue],
    overall: float,
    profile: dict[str, Any],
    anti_gaming: dict[str, Any],
    reached: list[str],
) -> str:
    thresholds = profile["thresholds"]
    mission = values["mission_success"]
    risk = values["risk_growth"]
    if (
        overall < thresholds["fail"]
        or reached
        or (mission.applicable and mission.score == 0)
    ):
        return "fail"
    if anti_gaming["gaming_detected"] or (
        risk.applicable and risk.score < RISKY_RISK_GROWTH
    ):
        return "risky"
    if overall >= thresholds["pass"]:
        return "pass"
    return "needs_more_test"


def _ranked(breakdown: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    return sorted(
        (
            (name, entry["score"])
            for name, entry in breakdown.items()
            if entry["applicable"] and entry["weight"] > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )


def _findings(
    breakdown: dict[str, dict[str, Any]],
    judgement: dict[str, Any],
    profile: dict[str, Any],
) -> list[str]:
    findings = [
        f"Overall score {judgement['overall_score']:.2f} under profile "
        f"{profile['profile_id']}: {judgement['status']} "
        f"(confidence {judgement['confidence']:.2f})"
    ]
    ranked = _ranked(breakdown)
    if ranked:
        findings.append(f"Strongest axis: {ranked[0][0]} {ranked[0][1]:.2f}")
        weakest = min(ranked, key=lambda item: (item[1], item[0]))
        findings.append(f"Weakest axis: {weakest[0]} {weakest[1]:.2f}")
    return findings


def _failure_causes(
    context: EvaluationContext,
    breakdown: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    anti_gaming: dict[str, Any],
    reached: list[str],
) -> list[str]:
    causes = [
        f"{event['target_entity_id']} destroyed at tick {event['time']} "
        f"by {event['source']['actor_id']}"
        for event in context.against_own(context.of_type("ENTITY_DESTROYED"))
    ]
    causes += [f"Failure threshold reached: {name}" for name in reached]
    causes += [
        f"{name} {entry['score']:.2f}: {entry['explanation']}"
        for name, entry in breakdown.items()
        if entry["applicable"]
        and entry["weight"] > 0
        and entry["score"] < profile["thresholds"]["fail"]
    ]
    causes += [
        f"Anti-gaming: {behavior}" for behavior in anti_gaming["flagged_behaviors"]
    ]
    return causes


def _next_tests(
    breakdown: dict[str, dict[str, Any]],
    anti_gaming: dict[str, Any],
    unevaluated: list[str],
) -> list[str]:
    tests = [
        f"Exercise {name}: {entry['explanation']}"
        for name, entry in breakdown.items()
        if not entry["applicable"] and entry["weight"] > 0
    ]
    tests += [
        f"Check whether {check['behavior']} was intended: {check['reason']}"
        for check in anti_gaming["checks"]
        if check["triggered"]
    ]
    tests += [
        f"Failure threshold {name!r} is not evaluated yet" for name in unevaluated
    ]
    return tests
