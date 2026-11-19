"""Detection gap, response time and failure points, read from a result package.

Important:
Pure: these read the package (its replay of every tick and its events)
and the scenario; they run nothing. Every threat that reached an asset is
a failure point with exactly one reason, checked in this order:

never_detected        no sensor ever saw it
misidentified         seen, but every track took it for a friend
detected_too_late     its first track was cleared to engage only when it hit
no_window             cleared in time, but never within an interceptor's
                      range while cleared (interception_window empty)
missed_in_window      engaged in its window, every salvo missed
not_engaged           in range while cleared, never fired on (out of
                      ammunition, reloading, other targets, or held fire)

A SKYFOX drone lost to its own side (fratricide) or to a collision is a
failure point too.
"""

from typing import Any

from ...observation.history import history_from_package
from .model import covered, interception_window


def _tracks(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every track ever opened, as it was when opened."""
    tracks: dict[str, dict[str, Any]] = {}
    for event in package["event_memory"]:
        if "sense" in event["tags"]:
            opened_now = event["after_state"]["state"]["tracks"]
            for key in event["data"]["opened"]:
                tracks[key] = dict(opened_now[key])
    return tracks


def _engagements(package: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"tick": e["time"], "by": e["source"]["actor_id"], **e["data"]}
        for e in package["event_memory"]
        if e["event_type"] == "ENTITY_STATE_CHANGED"
        and "engage" in e["tags"]
        and "track" not in e["tags"]
    ]


def detection_gap(package: dict[str, Any], scenario: dict[str, Any]) -> dict:
    """
    {uncovered_share, uncovered_cells, threats, mean_ticks_to_detect,
    worst_ticks_to_detect, undetected_leaks}: the share of the airspace no
    online sensor covers, and for each threat its launch, first detection and the
    ticks between (None: never detected).
    """
    space = scenario["world_contract"]["space_model"]
    size = (space["width"], space["height"])
    # an offline sensor (a spare not switched on) covers nothing
    sensors = [
        {"at": e["position"], "range": e["capabilities"]["range"]}
        for e in scenario["entities"]
        if e["entity_type"] == "sensor" and e["state"].get("online", True)
    ]
    seen = covered(sensors, size)
    total = size[0] * size[1]
    first: dict[str, int] = {}
    for event in package["event_memory"]:
        if "sense" in event["tags"]:
            for found in event["data"]["detections"]:
                first.setdefault(found["target"], event["time"])
    final = package["final_world_state"]["entities"]
    threats = {}
    for unit_id, unit in package["initial_world_state"]["entities"].items():
        if unit["entity_type"] != "threat":
            continue
        launch = int(unit["state"]["launch_tick"])
        detected = first.get(unit_id)
        threats[unit_id] = {
            "launch_tick": launch,
            "first_detected": detected,
            "ticks_to_detect": None if detected is None else detected - launch,
            "outcome": final[unit_id]["state"]["status"],
        }
    waits = [
        t["ticks_to_detect"]
        for t in threats.values()
        if t["ticks_to_detect"] is not None
    ]
    return {
        "uncovered_share": round(1 - len(seen) / total, 4) if total else 0.0,
        "uncovered_cells": total - len(seen),
        "threats": threats,
        "mean_ticks_to_detect": round(sum(waits) / len(waits), 4) if waits else None,
        "worst_ticks_to_detect": max(waits) if waits else None,
        "undetected_leaks": sorted(
            unit_id
            for unit_id, t in threats.items()
            if t["outcome"] == "leaked" and t["first_detected"] is None
        ),
    }


def _windows(package: dict[str, Any], scenario: dict[str, Any]) -> dict[str, list[int]]:
    """Each threat's interception window: cleared, in range, before it hit."""
    history = history_from_package(package)
    tracks = _tracks(package)
    interceptors = [
        {"at": e["position"], "range": e["capabilities"]["range"]}
        for e in scenario["entities"]
        if e["entity_type"] == "interceptor"
    ]
    hits = {
        e["target_entity_id"]: e["time"]
        for e in package["event_memory"]
        if "leak" in e["tags"]
    }
    windows = {}
    for unit_id, unit in package["initial_world_state"]["entities"].items():
        if unit["entity_type"] != "threat":
            continue
        cleared = min(
            (
                int(t["engageable_from"])
                for t in tracks.values()
                if t["target"] == unit_id and t["identified"] == "threat"
            ),
            default=None,
        )
        # where it was each tick it flew: active at the end of the tick, or
        # at the end of the one before (the tick it was shot down in counts)
        path = {}
        before = "reserve"
        for tick in sorted(history):
            unit_now = history[tick][unit_id]
            status = unit_now["state"]["status"]
            if status == "active" or before == "active":
                path[tick] = unit_now["position"]
            before = status
        windows[unit_id] = interception_window(
            path, interceptors, cleared, hits.get(unit_id)
        )
    return windows


def response_times(package: dict[str, Any], scenario: dict[str, Any]) -> dict:
    """
    {threats, mean, worst, mean_reaction, worst_reaction, never_engaged}.

    For each tracked threat: when its first track opened, when it could
    first be engaged (the first tick of its interception window), and when
    it was first fired on. Two measures, kept apart on purpose:

    response_ticks   track opened → first shot: includes the time the threat
                     needed to fly into range, so seeing it earlier makes
                     this longer
    reaction_ticks   first engageable tick → first shot: how long the
                     defence took once it could act

    None: never fired on (or never engageable).
    """
    windows = _windows(package, scenario)
    tracks = _tracks(package)
    engaged: dict[str, int] = {}
    for shot in _engagements(package):
        engaged.setdefault(shot["track"], shot["tick"])
    per_threat: dict[str, dict[str, Any]] = {}
    for key, track in sorted(tracks.items(), key=lambda kv: kv[1]["opened"]):
        if track["kind"] != "threat":
            continue
        entry = per_threat.setdefault(
            track["target"],
            {"track_opened": track["opened"], "first_engaged": None},
        )
        if key in engaged and (
            entry["first_engaged"] is None or engaged[key] < entry["first_engaged"]
        ):
            entry["first_engaged"] = engaged[key]
    for threat_id, entry in per_threat.items():
        window = windows.get(threat_id, [])
        entry["engageable_from"] = window[0] if window else None
        fired = entry["first_engaged"]
        entry["response_ticks"] = (
            None if fired is None else fired - entry["track_opened"]
        )
        entry["reaction_ticks"] = (
            None
            if fired is None or entry["engageable_from"] is None
            else max(0, fired - entry["engageable_from"])
        )

    def collect(key: str) -> list[int]:
        return [e[key] for e in per_threat.values() if e[key] is not None]

    times, reactions = collect("response_ticks"), collect("reaction_ticks")
    return {
        "threats": per_threat,
        "mean": round(sum(times) / len(times), 4) if times else None,
        "worst": max(times) if times else None,
        "mean_reaction": (
            round(sum(reactions) / len(reactions), 4) if reactions else None
        ),
        "worst_reaction": max(reactions) if reactions else None,
        "never_engaged": sorted(
            t for t, e in per_threat.items() if e["first_engaged"] is None
        ),
    }


def failure_points(package: dict[str, Any], scenario: dict[str, Any]) -> list[dict]:
    """Every leak and every drone lost, where and why (see the module doc)."""
    tracks = _tracks(package)
    shots = _engagements(package)
    windows = _windows(package, scenario)
    final = package["final_world_state"]["entities"]
    leak_tick = {
        e["target_entity_id"]: e["time"]
        for e in package["event_memory"]
        if "leak" in e["tags"]
    }
    points = []
    for unit_id, unit in sorted(final.items()):
        if unit["entity_type"] != "threat" or unit["state"]["status"] != "leaked":
            continue
        hit = leak_tick[unit_id]
        own = [t for t in tracks.values() if t["target"] == unit_id]
        hostile = [t for t in own if t["identified"] == "threat"]
        cleared = min((int(t["engageable_from"]) for t in hostile), default=None)
        window = windows[unit_id]
        fired = [s for s in shots if s["track"] in {t["track_id"] for t in hostile}]
        if not own:
            reason = "never_detected"
        elif not hostile:
            reason = "misidentified"
        elif cleared is not None and cleared >= hit:
            reason = "detected_too_late"
        elif not window:
            reason = "no_window"
        elif fired:
            reason = "missed_in_window"
        else:
            reason = "not_engaged"
        points.append(
            {
                "kind": "leak",
                "entity_id": unit_id,
                "tick": hit,
                "at": unit["position"],
                "target": unit["state"]["target"],
                "launched_from": package["initial_world_state"]["entities"][unit_id][
                    "position"
                ],
                "reason": reason,
                "interception_window": window,
                "salvos": len(fired),
            }
        )
    for event in package["event_memory"]:
        lost = event["event_type"] == "ENTITY_DESTROYED" and (
            "fratricide" in event["tags"] or "collision" in event["tags"]
        )
        if lost and final[event["target_entity_id"]]["entity_type"] == "drone":
            points.append(
                {
                    "kind": "drone_lost",
                    "entity_id": event["target_entity_id"],
                    "tick": event["time"],
                    "at": event["before_state"].get("position"),
                    "reason": (
                        "fratricide" if "fratricide" in event["tags"] else "collision"
                    ),
                }
            )
    return points


def airspace_outcome(package: dict[str, Any], scenario: dict[str, Any]) -> dict:
    """The three measures of a run, with the false alarms it cost."""
    shots = _engagements(package)
    false_alarms = sum(
        len(e["data"]["false_alarms"])
        for e in package["event_memory"]
        if "sense" in e["tags"]
    )
    points = failure_points(package, scenario)
    return {
        "outcome": package["evaluation_result"]["winner_or_result"],
        "detection_gap": detection_gap(package, scenario),
        "response_time": response_times(package, scenario),
        "failure_points": points,
        "leaks": sum(1 for p in points if p["kind"] == "leak"),
        "false_alarms": false_alarms,
        "shots_at_phantoms": sum(s["shots"] for s in shots if s["kind"] == "false"),
        "fratricide": sum(1 for p in points if p["reason"] == "fratricide"),
    }
