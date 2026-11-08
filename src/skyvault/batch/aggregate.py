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


def aggregate(records: list[dict[str, Any]], perspective: str) -> list[dict[str, Any]]:
    """
    One summary per variant, in the order variants first appear.

    A run is a win when the perspective faction is the one that survived, a
    loss when another faction did, and a draw otherwise. The score standard
    deviation is the sample one, and 0 for a single run.
    """
    frame = pd.DataFrame(records)
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
