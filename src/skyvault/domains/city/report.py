"""What a city run shows a reader: its cascade and its report, from result packages.

Important:
Pure: these read packages and score results; they run nothing.
"""

from typing import Any


def cascade(package: dict[str, Any]) -> dict[str, Any]:
    """
    The power outages of a run as a chain: each outage, what caused it
    (an incident, or the outage that sent it the load), the districts dark
    each tick, and when each substation came back.

    Important:
    A cascade is an outage caused by another outage. A failure the backups
    carry without tripping is an outage but no cascade (cascade_depth 0).
    """
    outages = []
    for event in package["event_memory"]:
        tags = event["tags"]
        if "power" in tags and ("failure" in tags or "trip" in tags):
            outages.append(
                {
                    "event_id": event["event_id"],
                    "tick": event["time"],
                    "substation": event["target_entity_id"],
                    "cause": event["data"]["cause"],
                    "caused_by_event": event["data"].get("caused_by_event", []),
                    "load": event["data"].get("load"),
                    "capacity": event["data"].get("capacity"),
                }
            )
    depth: dict[str, int] = {}
    for outage in outages:
        parents = [depth.get(e, 0) for e in outage["caused_by_event"] if e]
        depth[outage["event_id"]] = (max(parents) + 1) if parents else 0
        outage["depth"] = depth[outage["event_id"]]

    dark: dict[int, set[str]] = {}
    current: set[str] = set()
    last = package["final_world_state"]["tick"]
    by_tick: dict[int, list[dict[str, Any]]] = {}
    for event in package["event_memory"]:
        if (
            event["event_type"] == "ENTITY_STATE_CHANGED"
            and "power" in event["tags"]
            and "powered" in event["data"]
        ):
            by_tick.setdefault(event["time"], []).append(event)
    for tick in range(1, last + 1):
        for event in by_tick.get(tick, []):
            if event["data"]["powered"]:
                current.discard(event["target_entity_id"])
            else:
                current.add(event["target_entity_id"])
        dark[tick] = set(current)

    restored = [
        {"tick": e["time"], "substation": e["target_entity_id"]}
        for e in package["event_memory"]
        if "restored" in e["tags"]
    ]
    return {
        "outages": outages,
        "cascade_depth": max((o["depth"] for o in outages), default=0),
        "dark_districts": {
            str(tick): sorted(names) for tick, names in dark.items() if names
        },
        "most_dark": max((len(names) for names in dark.values()), default=0),
        "restored": restored,
    }


def city_report(summary: dict[str, Any]) -> str:
    """
    city_report.md from run_city's summary: each scenario's outcome and
    governance stability score, the cascade, and the supply delay study.
    """
    lines = ["# City report", ""]
    for name, run in summary["scenarios"].items():
        score = run["governance"]
        lines += [
            f"## {name}",
            "",
            f"- Outcome: {run['outcome']} (verdict {run['verdict']})",
            f"- Governance stability score: {score['score']:.2f} "
            f"(start {score['start']:.2f}; ticks {score['window'][0]}–"
            f"{score['window'][1]})",
            "- Components: "
            + ", ".join(f"{k} {v:.2f}" for k, v in score["components"].items()),
            "",
        ]
        chain = run["cascade"]
        if chain["outages"]:
            lines.append(
                f"Power: cascade depth {chain['cascade_depth']}, "
                f"at most {chain['most_dark']} districts dark."
            )
            lines.append("")
            for outage in chain["outages"]:
                why = (
                    "incident"
                    if outage["cause"] == "incident"
                    else f"overload {outage['load']} > {outage['capacity']}, "
                    f"after {', '.join(e for e in outage['caused_by_event'] if e)}"
                )
                lines.append(
                    f"- Tick {outage['tick']}: {outage['substation']} down "
                    f"({why}) [{outage['event_id']}]"
                )
            for back in chain["restored"]:
                lines.append(f"- Tick {back['tick']}: {back['substation']} restored")
            lines.append("")
        else:
            lines += ["Power: no outage.", ""]
    study = summary["supply_delay"]
    lines += [
        "## Supply delay and public order",
        "",
        f"{study['scenario']}, seeds {study['seeds'][0]}–{study['seeds'][-1]}.",
        "",
        "| delay factor | order restored | mean end order | mean score |",
        "|---|---|---|---|",
    ]
    for row in study["rows"]:
        lines.append(
            f"| {row['delay_factor']:g} | {row['restored_rate']:.0%} | "
            f"{row['mean_end_order']:.1f} | {row['mean_score']:.2f} |"
        )
    return "\n".join(lines) + "\n"
