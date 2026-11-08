"""Briefing = the run, its failure exploration and its batch, for a meeting.

Important:
Pure: a workspace in, a plain dict out. It is built from the same views the
UI shows, so the briefing never says anything a screen does not. Sections
for the failure exploration and the batch appear only when their outputs are
in the workspace.
"""

from collections import Counter
from typing import Any

from ..views import comparison_view, failure_view, overview_view, timeline_view

Section = dict[str, Any]


def build_briefing(workspace: dict[str, Any]) -> dict[str, Any]:
    """
    {title, created, sections}; each section {title, paragraphs, bullets, table}.

    created is the run's end time, so a briefing rebuilt from the same
    workspace is identical down to its metadata.
    """
    package = workspace["result_package"]
    overview = overview_view(package)
    sections = [
        _summary(overview),
        _what_happened(package),
        _losses(overview),
        _evaluation(overview),
        _tradeoffs(package),
    ]
    failure = failure_view(workspace)
    if failure is not None:
        sections.append(_failure(failure))
    comparison = comparison_view(workspace)
    if comparison is not None:
        sections.append(_comparison(comparison))
    sections.append(_reproducibility(package["reproducibility"]))
    return {
        "title": f"SKYVAULT briefing — {overview['scenario_id']} "
        f"{overview['scenario_version']}",
        "created": package["reproducibility"]["run_metadata"]["ended_at"],
        "sections": sections,
    }


def section(
    title: str,
    paragraphs: list[str] | None = None,
    bullets: list[str] | None = None,
    table: dict[str, Any] | None = None,
) -> Section:
    """One briefing section; table is {columns, rows} or None."""
    return {
        "title": title,
        "paragraphs": paragraphs or [],
        "bullets": bullets or [],
        "table": table,
    }


def _summary(overview: dict[str, Any]) -> Section:
    return section(
        "Summary",
        paragraphs=[
            f"Scenario {overview['scenario_id']} {overview['scenario_version']}: "
            f"{overview['event_count']} events over {overview['ticks']} ticks."
        ],
        bullets=[
            f"Result: {overview['result']}",
            f"Verdict: {overview['verdict']} (confidence {overview['confidence']:.2f})",
            f"Score: {overview['score']:.2f}",
            f"Profile: {overview['profile_id']}, seen from {overview['perspective']}",
        ],
    )


def _what_happened(package: dict[str, Any]) -> Section:
    bullets = []
    for tick in timeline_view(package)["ticks"]:
        counts = Counter(
            WORDS.get(
                event["event_type"], event["event_type"].lower().replace("_", " ")
            )
            for event in package["event_memory"]
            if event["time"] == tick["tick"] and event["event_type"] not in UNCOUNTED
        )
        parts = [_count(count, kind) for kind, count in sorted(counts.items())]
        parts += [
            f"{loss['name']} destroyed by {loss['by_name']}"
            for loss in tick["destroyed"]
        ]
        bullets.append(f"Tick {tick['tick']}: " + ("; ".join(parts) or "no action"))
    return section(
        "What happened",
        paragraphs=["Each tick: what was done, and who was destroyed by whom."],
        bullets=bullets,
    )


# Events that are bookkeeping of another event, or are told separately
UNCOUNTED = {
    "ACTION_SELECTED",
    "ENTITY_DESTROYED",
    "SCENARIO_END",
    "ENTITY_STATE_CHANGED",
    "RESOURCE_CHANGED",
}
# What a person calls the rest
WORDS = {"ACTION_REJECTED": "refused order", "NO_ACTION": "idle unit"}


def _count(count: int, kind: str) -> str:
    """'1 miss', '2 misses', '4 attacks', '3 refused orders', '2 resupplies'."""
    if count == 1:
        return f"1 {kind}"
    if kind.endswith("s"):
        return f"{count} {kind}es"
    if kind.endswith("y") and kind[-2:-1] not in "aeiou":
        return f"{count} {kind[:-1]}ies"
    return f"{count} {kind}s"


def _losses(overview: dict[str, Any]) -> Section:
    bullets = []
    for faction in overview["losses"]:
        lost = faction["lost"]
        line = f"{faction['faction']} lost {len(lost)} of {faction['units']}"
        if lost:
            line += ": " + ", ".join(
                f"{unit['name']} at tick {unit['tick']}" for unit in lost
            )
        bullets.append(line)
    return section("Losses", bullets=bullets)


def _evaluation(overview: dict[str, Any]) -> Section:
    paragraphs = list(overview["key_findings"])
    bullets = [f"{axis} {score:.2f}" for axis, score in overview["scores"].items()]
    bullets += [f"Failure cause: {cause}" for cause in overview["failure_causes"]]
    bullets += [f"Next test: {test}" for test in overview["recommended_next_tests"]]
    bullets += [f"Flagged: {flag}" for flag in overview["flagged_behaviors"]]
    return section("Evaluation", paragraphs=paragraphs, bullets=bullets)


def _tradeoffs(package: dict[str, Any]) -> Section:
    report = package["tradeoff_report"]
    return section(
        "Trade-offs",
        bullets=[
            f"{t['gain']} {t['gain_score']:.2f} against {t['cost']} "
            f"{t['cost_score']:.2f}: {t['assessment']}"
            for t in report.get("tradeoffs", [])
        ],
    )


def _failure(failure: dict[str, Any]) -> Section:
    bullets = [
        f"Survives without stress: {failure['baseline_survival']:.0%}",
        f"Crushed by: {failure['crushing_variable']} "
        f"(assumption {failure['crushing_assumption']})",
        f"Best alternative: {failure['best_alternative']}",
        f"First loss on average at tick "
        f"{failure['how_fast']['mean_first_loss_tick']:.1f}",
    ]
    bullets += failure["conditions"]
    rows = [
        [row["variable"]]
        + [f"{rate:.0%}" if rate is not None else "-" for rate in row["survival"]]
        + [row["breaking_level"] or "never", f"{row['sensitivity']:+.2f}"]
        for row in failure["rows"]
        if row["applicable"]
    ]
    return section(
        "Failure exploration",
        paragraphs=[
            f"{failure['scenario_version']} stressed {failure['repeat_count']} times "
            f"per level; a level breaks below "
            f"{failure['survival_threshold']:.0%} survival."
        ],
        bullets=bullets,
        table={
            "columns": ["Variable", *failure["levels"], "Breaks at", "Sensitivity"],
            "rows": rows,
        },
    )


def _comparison(comparison: dict[str, Any]) -> Section:
    bullets = [
        f"Best {metric.replace('_', ' ')}: {variant}"
        for metric, variant in comparison["best"].items()
    ]
    package = comparison["conflict_package"]
    paragraphs = [
        f"Batch {comparison['batch_id']}: {comparison['repeat_count']} runs per "
        f"variant, {comparison['total_runs']} runs, seen from "
        f"{comparison['perspective']}."
    ]
    if package is not None:
        for conflict in package["conflicts"]:
            bullets.append(f"Conflict {conflict['conflict_id']}: {conflict['reason']}")
        recommendation = package["recommendation_to_nexus"]
        bullets.append(
            "Decision required: "
            + ("yes" if recommendation["required_decision"] else "no")
        )
        paragraphs.append(recommendation["decision_reason"])
    rows = [
        [
            stats["variant_id"],
            f"{stats['win_rate']:.0%}",
            f"{stats['failure_frequency']:.0%}",
            f"{stats['mean_hp_lost']:g}",
            f"{stats['mean_risk_events']:g}",
            f"{stats['mean_score']:.3f}",
        ]
        for stats in comparison["variants"]
    ]
    return section(
        "Plan comparison",
        paragraphs=paragraphs,
        bullets=bullets,
        table={
            "columns": ["Variant", "Win", "Fail", "HP lost", "Risk", "Score"],
            "rows": rows,
        },
    )


def _reproducibility(reproducibility: dict[str, Any]) -> Section:
    seed = reproducibility["random_seed"]
    return section(
        "Reproducibility",
        bullets=[
            f"Run: {reproducibility['run_id']}",
            (
                f"Random: seed {seed} ({reproducibility['random_seed_policy']})"
                if seed is not None
                else f"Random: {reproducibility['random_seed_policy']}, not replayable"
            ),
            f"Runtime {reproducibility['runtime_version']}, rules "
            f"{reproducibility['ruleset_version']}",
            f"Input hash: {reproducibility['input_hash']}",
            f"Output hash: {reproducibility['output_hash']}",
        ],
    )
