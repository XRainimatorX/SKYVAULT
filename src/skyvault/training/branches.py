"""STARTX branch evaluation: the batch's variants and branches as records.

Important:
Pure: reads the three batch outputs (Phase 10). One record per variant with
its metrics, its difference from the first variant and its rank; when the
batch had conflicting orders, one record per branch measured against the
baseline, with whether a decision is required. Nothing is chosen here.
"""

from typing import Any


def branch_evaluation(
    batch_result: dict[str, Any],
    branch_comparison: dict[str, Any],
    conflict_package: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Variant records in batch order, then branch records in package order."""
    ranking = branch_comparison["ranking"]
    best = branch_comparison["best"]
    records: list[dict[str, Any]] = []
    for stats in batch_result["variants"]:
        variant = stats["variant_id"]
        records.append(
            {
                "record_type": "variant",
                "batch_id": batch_result["batch_id"],
                "scenario_id": batch_result["scenario_id"],
                "perspective": batch_result["perspective"],
                "variant_id": variant,
                "kind": stats["kind"],
                "scenario_version": stats["scenario_version"],
                "runs": stats["runs"],
                "metrics": dict(branch_comparison["table"][variant]),
                "win_rate_ci": list(stats["win_rate_ci"]),
                "delta_vs_first": dict(branch_comparison["deltas_vs_first"][variant]),
                "rank": ranking.index(variant) + 1,
                "best_at": sorted(m for m, v in best.items() if v == variant),
            }
        )
    if conflict_package is not None:
        decision = conflict_package["recommendation_to_nexus"]["required_decision"]
        for branch in [*conflict_package["branch_runs"], conflict_package["baseline"]]:
            records.append(
                {
                    "record_type": "branch",
                    "batch_id": batch_result["batch_id"],
                    "scenario_id": batch_result["scenario_id"],
                    "perspective": batch_result["perspective"],
                    "conflict_id": conflict_package["conflict_id"],
                    "branch_id": branch["branch_id"],
                    "action_set": list(branch["action_set"]),
                    "metrics": dict(branch["metrics"]),
                    "delta_vs_baseline": dict(branch["evaluation_delta"]),
                    "result_summary": branch["result_summary"],
                    "required_decision": decision,
                }
            )
    return records
