"""Aggregation = many runs per variant, reduced to numbers you can compare.

Important:
Pure functions: plain records in, plain data out, nothing from the rest of
the project imported. pandas does the grouping (the development plan names
pandas / polars for this); everything returned is plain Python, so results
serialise to JSON and compare equal across pandas 2 and 3.
"""

import math
from typing import Any

import pandas as pd

# Metric, and whether a larger value is better
METRICS: dict[str, bool] = {
    "win_rate": True,
    "failure_frequency": False,
    "mean_hp_lost": False,
    "mean_risk_events": False,
    "mean_score": True,
}

Z_95 = 1.959964


def wilson_interval(successes: int, trials: int) -> list[float]:
    """The Wilson 95% interval for a rate; [0, 1] with no trials."""
    if trials == 0:
        return [0.0, 1.0]
    rate = successes / trials
    denominator = 1 + Z_95**2 / trials
    centre = (rate + Z_95**2 / (2 * trials)) / denominator
    spread = Z_95 * math.sqrt(rate * (1 - rate) / trials + Z_95**2 / (4 * trials**2))
    spread /= denominator
    return [round(max(0.0, centre - spread), 4), round(min(1.0, centre + spread), 4)]


def aggregate(
    records: list[dict[str, Any]],
    perspective: str,
    success_outcomes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    One summary per variant, in the order variants first appear.

    A run is a win when the perspective faction is the one that survived, a
    loss when another faction did, and a draw otherwise. A scenario that
    names its success_outcomes (a city: order_restored, order_held) wins
    with those and loses with every other outcome. The score standard
    deviation is the sample one, and 0 for a single run.
    """
    frame = pd.DataFrame(records)
    if success_outcomes:
        frame["win"] = frame["outcome"].isin(success_outcomes)
        frame["loss"] = ~frame["win"]
    else:
        frame["win"] = frame["outcome"] == f"{perspective}_survived"
        frame["loss"] = frame["outcome"].str.endswith("_survived") & ~frame["win"]
    frame["fail"] = frame["status"] == "fail"

    summaries = []
    for variant_id, group in frame.groupby("variant_id", sort=False):
        runs = len(group)
        wins = int(group["win"].sum())
        losses = int(group["loss"].sum())
        stdev = float(group["score"].std(ddof=1)) if runs > 1 else 0.0
        summaries.append(
            {
                "variant_id": str(variant_id),
                "kind": str(group["kind"].iloc[0]),
                "scenario_version": str(group["scenario_version"].iloc[0]),
                "runs": runs,
                "win_rate": round(wins / runs, 4),
                "win_rate_ci": wilson_interval(wins, runs),
                "loss_rate": round(losses / runs, 4),
                "draw_rate": round((runs - wins - losses) / runs, 4),
                "failure_frequency": round(float(group["fail"].mean()), 4),
                "mean_score": round(float(group["score"].mean()), 4),
                "score_stdev": round(stdev, 4),
                "mean_hp_lost": round(float(group["hp_lost"].mean()), 4),
                "mean_risk_events": round(float(group["risk_events"].mean()), 4),
                "mean_event_count": round(float(group["event_count"].mean()), 4),
                "outcomes": {
                    str(key): int(value)
                    for key, value in sorted(group["outcome"].value_counts().items())
                },
                "distinct_outputs": int(group["output_hash"].nunique()),
            }
        )
    return summaries


def compare_branches(stats: list[dict[str, Any]]) -> dict[str, Any]:
    """
    The variants side by side: every metric, the best variant per metric,
    each variant's difference from the first, and which variants each one
    beats on mean score.
    """
    order = [entry["variant_id"] for entry in stats]
    table = {entry["variant_id"]: {m: entry[m] for m in METRICS} for entry in stats}
    first = order[0]

    best = {}
    for metric, larger_is_better in METRICS.items():
        sign = -1 if larger_is_better else 1
        # Smallest signed value wins; ties go to the variant listed first
        best[metric] = min(
            order, key=lambda v: (sign * table[v][metric], order.index(v))
        )

    ranking = sorted(order, key=lambda v: (-table[v]["mean_score"], order.index(v)))
    return {
        "metrics": {
            m: ("higher" if better else "lower") + " is better"
            for m, better in METRICS.items()
        },
        "variants": order,
        "table": table,
        "best": best,
        "deltas_vs_first": {
            v: {m: round(table[v][m] - table[first][m], 4) for m in METRICS}
            for v in order
        },
        "ranking": ranking,
        "comparison": {
            v: {
                "better_than": [
                    w for w in order if table[v]["mean_score"] > table[w]["mean_score"]
                ],
                "worse_than": [
                    w for w in order if table[v]["mean_score"] < table[w]["mean_score"]
                ],
            }
            for v in order
        },
    }


def render_comparative_report(
    batch_result: dict[str, Any],
    comparison: dict[str, Any],
    conflict_package: dict[str, Any] | None = None,
) -> str:
    """
    comparative_report.md: the batch for a person to read.

    The variants side by side with a win-rate bar each, the best variant per
    metric, and, when there were conflicting orders, every branch next to
    the baseline with the decision left open.
    """
    lines = [
        f"# Comparative report — {batch_result['batch_id']}",
        "",
        f"Scenario `{batch_result['scenario_id']}` {batch_result['base_version']}, "
        f"profile `{batch_result['profile_id']}`, seen from "
        f"{batch_result['perspective']}; {batch_result['repeat_count']} runs per "
        f"variant, {batch_result['total_runs']} runs in all.",
        "",
        "## Variants",
        "",
        "| Variant | Kind | Win rate | 95% CI | Fail | HP lost | Risk events "
        "| Score | |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for stats in batch_result["variants"]:
        low, high = stats["win_rate_ci"]
        bar = "█" * round(stats["win_rate"] * 20)
        lines.append(
            f"| {stats['variant_id']} | {stats['kind']} | {stats['win_rate']:.0%} "
            f"| {low:.0%}–{high:.0%} | {stats['failure_frequency']:.0%} "
            f"| {stats['mean_hp_lost']:g} | {stats['mean_risk_events']:g} "
            f"| {stats['mean_score']:.3f} | `{bar or '·'}` |"
        )
    lines += ["", "## Best per metric", ""]
    for metric, rule in comparison["metrics"].items():
        lines.append(f"- **{metric}** ({rule}): {comparison['best'][metric]}")
    lines += ["", "Ranking by mean score: " + " > ".join(comparison["ranking"])]

    if conflict_package is not None:
        lines += ["", "## Conflicting orders", ""]
        for conflict in conflict_package["conflicts"]:
            lines.append(
                f"- {conflict['conflict_id']}: {conflict['reason']} "
                f"({', '.join(conflict['conflict_types'])})"
            )
        lines += ["", "| Branch | Orders | Result | Δ score vs baseline |"]
        lines.append("|---|---|---|---|")
        for branch in [*conflict_package["branch_runs"], conflict_package["baseline"]]:
            lines.append(
                f"| {branch['branch_id']} | {', '.join(branch['action_set']) or '—'} "
                f"| {branch['result_summary']} "
                f"| {branch['evaluation_delta']['mean_score']:+.4f} |"
            )
        recommendation = conflict_package["recommendation_to_nexus"]
        required = "yes" if recommendation["required_decision"] else "no"
        lines += [
            "",
            f"Decision required: **{required}**",
            "",
            recommendation["decision_reason"],
        ]
    return "\n".join(lines) + "\n"
