"""airspace_report.md: what run_airspace found, for a person to read (pure)."""

from typing import Any

REASONS = {
    "never_detected": "never detected",
    "misidentified": "taken for a friend",
    "detected_too_late": "cleared to engage only when it hit",
    "no_window": "never within an interceptor's range while cleared",
    "missed_in_window": "every salvo in its window missed",
    "not_engaged": "in range and cleared, never fired on",
    "fratricide": "shot down by its own side",
    "collision": "collided with a threat",
}


def _ticks(value: Any) -> str:
    return "—" if value is None else f"{float(value):.1f}"


def airspace_report(summary: dict[str, Any]) -> str:
    """The reference run, the HADES behaviours and the AEROGRID configurations."""
    run = summary["reference"]
    gap = run["detection_gap"]
    response = run["response_time"]
    lines = [
        "# Airspace report",
        "",
        f"## {summary['scenario']} (seed {summary['seed']})",
        "",
        f"- Outcome: {run['outcome']}; {run['leaks']} threat(s) reached an asset",
        f"- Detection gap: {gap['uncovered_share']:.0%} of the airspace uncovered; "
        f"mean {_ticks(gap['mean_ticks_to_detect'])} ticks from launch to first "
        f"detection (worst {gap['worst_ticks_to_detect']})",
        f"- Response: {_ticks(response['mean'])} ticks from track to first shot; "
        f"reaction {_ticks(response['mean_reaction'])} ticks from first chance to "
        "first shot",
        f"- False alarms: {run['false_alarms']}; shots at phantoms: "
        f"{run['shots_at_phantoms']}; fratricide: {run['fratricide']}",
        "",
    ]
    if run["failure_points"]:
        lines.append("Failure points:")
        lines.append("")
        for point in run["failure_points"]:
            where = f"at {point['at']}" if point.get("at") is not None else ""
            lines.append(
                f"- Tick {point['tick']}: {point['entity_id']} {where} — "
                f"{REASONS[point['reason']]}"
            )
        lines.append("")
    for title, key, label in (
        ("HADES rules of engagement", "behaviors", "behavior"),
        ("AEROGRID sensor configurations", "configs", "config"),
    ):
        lines += [
            f"## {title}",
            "",
            f"{summary['runs']} runs each (seeds {summary['seed']}–"
            f"{summary['seed'] + summary['runs'] - 1}).",
            "",
            f"| {label} | defended | mean leaks | uncovered | detect (ticks) | "
            "reaction (ticks) |",
            "|---|---|---|---|---|---|",
        ]
        for name, row in summary[key].items():
            lines.append(
                f"| {name} | {row['defended_rate']:.0%} | {row['mean_leaks']:.1f} | "
                f"{row['uncovered_share']:.0%} | "
                f"{_ticks(row['mean_ticks_to_detect'])} | "
                f"{_ticks(row['mean_reaction_ticks'])} |"
            )
        lines.append("")
    return "\n".join(lines)
