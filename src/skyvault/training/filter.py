"""The anti-gaming training filter: which runs may teach, which only warn.

Important:
Pure. A run with any violation goes to rejected and none of its
transitions may reach the clean dataset, whatever else is true of it. A run
without a violation that Phase 7 judged risky goes to risky. Everything
else is clean — including honest failures, which are worth learning from
and say so in their success_type.
"""

from typing import Any

from .labels import LABELS, run_labels
from .transitions import build_transitions, scenario_metadata

BUCKETS = ("clean", "risky", "rejected")


def bucket_of(package: dict[str, Any], labels: dict[str, Any]) -> tuple[str, str]:
    """(bucket, reason) for one run."""
    if labels["violations"]:
        return "rejected", "violations: " + ", ".join(labels["violations"])
    status = package["evaluation_result"]["overall_judgement"]["status"]
    if status == "risky":
        return "risky", "no violation; Phase 7 judged the run risky"
    return "clean", f"no violation; verdict {status}"


def split_runs(runs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, list]:
    """{clean, risky, rejected}: every transition of every run, by its run's bucket."""
    split: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKETS}
    for package, scenario in runs:
        bucket, _ = bucket_of(package, run_labels(package, scenario))
        split[bucket] += build_transitions(package, scenario)
    return split


def anti_gaming_report(
    runs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    """How many runs carry each label, and where every run went and why."""
    entries = []
    for package, scenario in runs:
        labels = run_labels(package, scenario)
        bucket, reason = bucket_of(package, labels)
        entries.append(
            {
                **scenario_metadata(package, scenario),
                "bucket": bucket,
                "reason": reason,
                "success_type": labels["success_type"],
                "labels": [label for label in LABELS if labels["labels"][label]],
                "violations": labels["violations"],
                "decisions": sum(
                    e["event_type"] == "ACTION_SELECTED"
                    for e in package["event_memory"]
                ),
            }
        )
    return {
        "runs": len(entries),
        "buckets": {b: sum(e["bucket"] == b for e in entries) for b in BUCKETS},
        "success_types": {
            kind: sum(e["success_type"] == kind for e in entries)
            for kind in ("genuine_success", "false_success", "failure")
        },
        "label_counts": {
            label: sum(label in e["labels"] for e in entries) for label in LABELS
        },
        "violation_counts": {
            label: sum(label in e["violations"] for e in entries) for label in LABELS
        },
        "entries": entries,
    }
