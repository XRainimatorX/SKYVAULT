"""Observe = one observer's view of the world at one tick (pure).

Important:
history maps a tick to the units as they were then ({entity id: entity
snapshot}); the earliest tick is the start of the run. Every observation
is built from history alone and checked against the observation contract.
Five views (Formal Spec section 5, development plan Phase 5):

    local      TAC ANGEL: one unit, its side, enemies in sight or recently lost
    aggregate  STARTX: counts, health and trends — no positions at all
    mission    NEXUS: progress of the run for every side (no fog)
    threat     HADES: enemies in sight and how soon they can strike
    coverage   AEROGRID: how much of the map the side's sensors cover
"""

import math
from typing import Any

from ..contracts import validate_observation
from .sensing import grid_distance, is_active, sensor_range, visible_contacts

Units = dict[str, Any]
History = dict[int, Units]


def observe(
    history: History,
    tick: int,
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    What the profile's system sees at tick from viewpoint {faction, actor_id}.

    Important:
    The observation shows tick − delay_ticks (information delay). context
    holds what is not in the units: max_ticks, resources, available_actions,
    mission, constraints, concealment (a function of a cell, or None) and
    space (the world's space model).
    """
    observed_at = max(0, tick - profile["delay_ticks"])
    faction = viewpoint["faction"]
    units = units_at(history, observed_at)
    view = profile["view"]

    contacts = (
        []
        if view == "mission"
        else enemy_contacts(history, observed_at, faction, profile, context)
    )
    hidden = view != "mission" and any(
        is_active(unit) and unit["entity_id"] not in _ids(contacts, "visible")
        for unit in units.values()
        if unit["faction"] != faction
    )
    state = VIEWS[view](
        history, observed_at, units, contacts, profile, viewpoint, context
    )

    if view == "mission":
        confidence = 1.0
    elif contacts:
        confidence = round(sum(c["confidence"] for c in contacts) / len(contacts), 4)
    else:
        confidence = 0.0 if hidden else 1.0

    return validate_observation(
        {
            "observer_id": profile["observer_id"],
            "time": tick,
            "view": view,
            "viewpoint": {"faction": faction, "actor_id": viewpoint.get("actor_id")},
            "visible_world_state": {
                "resources_visible": dict(context.get("resources", {})),
                **state,
            },
            "hidden_state": {
                "exists": hidden,
                "reason": "fog_of_war" if hidden else None,
            },
            "uncertainty": {
                "confidence_level": confidence,
                "stale_after": profile["stale_after_ticks"],
                "source_quality": profile["source_quality"],
                "delay_ticks": profile["delay_ticks"],
                "observed_at": observed_at,
            },
            "decision_context": {
                "mission_goal": context.get("mission"),
                "constraints": list(context.get("constraints", [])),
                "available_actions": sorted(context.get("available_actions", [])),
            },
        }
    )


def units_at(history: History, tick: int) -> Units:
    """The units at tick: the latest recorded tick at or before it."""
    if tick in history:
        return history[tick]
    known = [t for t in history if t <= tick]
    if not known:
        raise ValueError(f"no history at or before tick {tick}")
    return history[max(known)]


def enemy_contacts(
    history: History,
    tick: int,
    faction: str,
    profile: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Every enemy the side knows of at tick, ordered by id.

    Important:
    In sight now: visible (or destroyed, a wreck in sight). Out of sight but
    seen within the last stale_after_ticks ticks: stale, where and as it was
    when last seen, with confidence × (1 − age / (stale_after + 1)). An enemy
    last seen as a wreck is not remembered: it is known to be gone.
    """
    concealment = context.get("concealment")
    space = context.get("space")
    start = initial_hp(history)
    units = units_at(history, tick)
    contacts = {
        entity_id: _contact(
            units[entity_id], confidence, None, start, profile, current=True
        )
        for entity_id, confidence in visible_contacts(
            units, faction, profile, concealment, space
        ).items()
    }
    first = first_tick(history)
    stale_after = profile["stale_after_ticks"]
    for age in range(1, stale_after + 1):
        past = tick - age
        if past < first:
            break
        earlier = units_at(history, past)
        seen = visible_contacts(earlier, faction, profile, concealment, space)
        for entity_id, confidence in seen.items():
            if entity_id in contacts:
                continue
            fade = round(confidence * (1 - age / (stale_after + 1)), 4)
            contacts[entity_id] = _contact(
                earlier[entity_id], fade, (past, age), start, profile, current=False
            )
    return [
        contact
        for _, contact in sorted(contacts.items())
        if contact["status"] != "forgotten"
    ]


def first_tick(history: History) -> int:
    """The earliest tick in history: tick 0 for every run, found without a scan."""
    return 0 if 0 in history else min(history)


def initial_hp(history: History) -> dict[str, float]:
    """Every unit's hp at the start of the run, the scale health bands use."""
    return {
        entity_id: float(unit["state"].get("hp", 0))
        for entity_id, unit in history[first_tick(history)].items()
    }


def hp_band(hp: float, start: float) -> str:
    """intact above two thirds of the starting hp, critical below one third."""
    share = hp / start if start > 0 else 0.0
    if share > 2 / 3:
        return "intact"
    if share < 1 / 3:
        return "critical"
    return "damaged"


def _contact(
    unit: dict[str, Any],
    confidence: float,
    stale: tuple[int, int] | None,
    start: dict[str, float],
    profile: dict[str, Any],
    current: bool,
) -> dict[str, Any]:
    """One enemy as known: its health only as the profile's enemy_detail allows."""
    destroyed = not is_active(unit)
    if destroyed:
        status = "destroyed" if current else "forgotten"
    else:
        status = "visible" if current else "stale"
    hp = max(float(unit["state"].get("hp", 0)), 0.0)
    detail = profile["enemy_detail"]
    entity_id = unit["entity_id"]
    return {
        "entity_id": entity_id,
        "faction": unit["faction"],
        "relation": "enemy",
        "status": status,
        "position": unit["position"],
        "hp": hp if detail == "exact" and not destroyed else None,
        "hp_band": (
            hp_band(hp, start.get(entity_id, hp))
            if detail == "banded" and not destroyed
            else None
        ),
        "confidence": confidence,
        "last_seen": stale[0] if stale else None,
        "age": stale[1] if stale else None,
        "capabilities": None,
        "state": None,
    }


def _own(unit: dict[str, Any], relation: str) -> dict[str, Any]:
    """An own unit: always exact, with its state and capabilities."""
    return {
        "entity_id": unit["entity_id"],
        "faction": unit["faction"],
        "relation": relation,
        "status": "active" if is_active(unit) else "destroyed",
        "position": unit["position"],
        "hp": max(float(unit["state"].get("hp", 0)), 0.0),
        "hp_band": None,
        "confidence": 1.0,
        "last_seen": None,
        "age": None,
        "capabilities": dict(unit["capabilities"]),
        "state": dict(unit["state"]),
    }


def _ids(contacts: list[dict[str, Any]], *statuses: str) -> set[str]:
    return {c["entity_id"] for c in contacts if c["status"] in statuses}


def _count(contacts: list[dict[str, Any]], status: str) -> int:
    return sum(1 for c in contacts if c["status"] == status)


def _side(units: Units, start: dict[str, float], faction: str) -> dict[str, Any]:
    """A side's living and destroyed units and its share of starting hp."""
    own = [u for u in units.values() if u["faction"] == faction]
    total = sum(start.get(u["entity_id"], 0.0) for u in own)
    left = sum(max(float(u["state"].get("hp", 0)), 0.0) for u in own if is_active(u))
    return {
        "active": sum(1 for u in own if is_active(u)),
        "destroyed": sum(1 for u in own if not is_active(u)),
        "hp_ratio": round(left / total, 4) if total else 0.0,
    }


def _move(unit: dict[str, Any]) -> float:
    return float(unit["capabilities"].get("move_range", 1)) or 1.0


def local_view(
    history: History,
    tick: int,
    units: Units,
    contacts: list[dict[str, Any]],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    TAC ANGEL: the deciding unit, its whole side, the enemies it knows of and
    the ones that can strike it — in range now, or after one move.
    """
    actor_id = viewpoint.get("actor_id")
    if actor_id not in units:
        raise ValueError("the local view needs the deciding unit's actor_id")
    actor = units[actor_id]
    space = context.get("space")
    allies = sorted(
        (u for u in units.values() if u["faction"] == actor["faction"]),
        key=lambda u: u["entity_id"],
    )
    known = [_own(actor, "self")] + [
        _own(u, "ally") for u in allies if u["entity_id"] != actor_id
    ]
    known += contacts
    centre = actor["position"]
    radius = profile["local_radius"]
    risks = []
    for contact in contacts:
        if contact["status"] == "destroyed" or centre is None:
            continue
        enemy = units[contact["entity_id"]]
        distance = grid_distance(space, centre, contact["position"])
        reach = float(enemy["capabilities"].get("attack_range", 1))
        if distance <= reach + _move(enemy):
            risks.append(
                {
                    "entity_id": contact["entity_id"],
                    "kind": "in_range" if distance <= reach else "can_close",
                    "distance": distance,
                    "confidence": contact["confidence"],
                }
            )
    risks.sort(key=lambda r: (r["distance"], r["entity_id"]))
    area = (
        None
        if centre is None
        else {
            "center": centre,
            "radius": radius,
            "distance_model": (space or {}).get("distance_model") or "chebyshev",
            "entity_ids": sorted(
                e["entity_id"]
                for e in known
                if e["position"] is not None
                and grid_distance(space, centre, e["position"]) <= radius
            ),
        }
    )
    return {
        "local_area": area,
        "known_entities": known,
        "known_risks": risks,
        "summary": {
            "own_active": sum(1 for u in allies if is_active(u)),
            "visible_enemies": _count(contacts, "visible"),
            "stale_enemies": _count(contacts, "stale"),
            "destroyed_enemies_in_sight": _count(contacts, "destroyed"),
        },
    }


def aggregate_view(
    history: History,
    tick: int,
    units: Units,
    contacts: list[dict[str, Any]],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    STARTX: how each side is doing and where it is heading — counts and
    shares of health only, never a position or an id. The trend window is
    the profile's memory, stale_after_ticks (at least one tick).
    """
    faction = viewpoint["faction"]
    start = initial_hp(history)
    window = max(1, profile["stale_after_ticks"])
    past_tick = max(first_tick(history), tick - window)
    own_now = _side(units, start, faction)
    own_then = _side(units_at(history, past_tick), start, faction)
    then = enemy_contacts(history, past_tick, faction, profile, context)
    return {
        "local_area": None,
        "known_entities": [],
        "known_risks": [],
        "summary": {
            "own": own_now,
            "enemy": {
                "visible": _count(contacts, "visible"),
                "stale": _count(contacts, "stale"),
                "destroyed_in_sight": _count(contacts, "destroyed"),
            },
            "trend": {
                "window": tick - past_tick,
                "own_hp_ratio_change": round(
                    own_now["hp_ratio"] - own_then["hp_ratio"], 4
                ),
                "own_losses": own_now["destroyed"] - own_then["destroyed"],
                "enemy_contacts_change": _count(contacts, "visible")
                - _count(then, "visible"),
            },
        },
    }


def mission_view(
    history: History,
    tick: int,
    units: Units,
    contacts: list[dict[str, Any]],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """NEXUS: how far the run is and how every side stands (no fog)."""
    start = initial_hp(history)
    max_ticks = int(context.get("max_ticks", 0))
    factions = sorted({u["faction"] for u in units.values()})
    return {
        "local_area": None,
        "known_entities": [],
        "known_risks": [],
        "summary": {
            "tick": tick,
            "max_ticks": max_ticks,
            "progress": round(tick / max_ticks, 4) if max_ticks else 0.0,
            "factions": {f: _side(units, start, f) for f in factions},
        },
    }


def threat_view(
    history: History,
    tick: int,
    units: Units,
    contacts: list[dict[str, Any]],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    HADES: every enemy in sight or recently lost, the own unit it is nearest
    and how many ticks until it can strike that unit; the defence window is
    the soonest of them.
    """
    faction = viewpoint["faction"]
    space = context.get("space")
    own = sorted(
        (
            u
            for u in units.values()
            if u["faction"] == faction and is_active(u) and u["position"]
        ),
        key=lambda u: u["entity_id"],
    )
    risks = []
    for contact in contacts:
        if contact["status"] == "destroyed" or not own:
            continue
        enemy = units[contact["entity_id"]]
        nearest = min(
            own,
            key=lambda u: (
                grid_distance(space, u["position"], contact["position"]),
                u["entity_id"],
            ),
        )
        distance = grid_distance(space, nearest["position"], contact["position"])
        reach = float(enemy["capabilities"].get("attack_range", 1))
        ticks = max(0, math.ceil((distance - reach) / _move(enemy)))
        risks.append(
            {
                "entity_id": contact["entity_id"],
                "nearest_own": nearest["entity_id"],
                "distance": distance,
                "ticks_to_strike": ticks,
                "confidence": contact["confidence"],
            }
        )
    risks.sort(key=lambda r: (r["ticks_to_strike"], r["distance"], r["entity_id"]))
    return {
        "local_area": None,
        "known_entities": contacts,
        "known_risks": risks,
        "summary": {
            "threats": len(risks),
            "in_range_now": sum(1 for r in risks if r["ticks_to_strike"] == 0),
            "defense_window": min((r["ticks_to_strike"] for r in risks), default=None),
        },
    }


def coverage_view(
    history: History,
    tick: int,
    units: Units,
    contacts: list[dict[str, Any]],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    AEROGRID: the cells within nominal range of the side's living sensors,
    their share of the map and the number of gaps (connected uncovered areas).
    """
    faction = viewpoint["faction"]
    space = context.get("space") or {}
    width, height = int(space.get("width", 0)), int(space.get("height", 0))
    if space.get("type", "grid") != "grid" or not width or not height:
        raise ValueError("the coverage view needs a grid space with a size")
    sensors = [
        u
        for u in units.values()
        if u["faction"] == faction and is_active(u) and u["position"]
    ]
    covered = {
        (x, y)
        for x in range(width)
        for y in range(height)
        if any(
            grid_distance(space, s["position"], (x, y)) <= sensor_range(s, profile)
            for s in sensors
        )
    }
    total = width * height
    return {
        "local_area": None,
        "known_entities": [],
        "known_risks": [],
        "summary": {
            "covered_cells": len(covered),
            "total_cells": total,
            "coverage_ratio": round(len(covered) / total, 4),
            "gaps": _gaps(width, height, covered),
            "contacts": _count(contacts, "visible"),
        },
    }


def _gaps(width: int, height: int, covered: set[tuple[int, int]]) -> int:
    """Connected areas (four neighbours) of cells no sensor covers."""
    seen = set(covered)
    gaps = 0
    for x in range(width):
        for y in range(height):
            if (x, y) in seen:
                continue
            gaps += 1
            stack = [(x, y)]
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
    return gaps


VIEWS = {
    "local": local_view,
    "aggregate": aggregate_view,
    "mission": mission_view,
    "threat": threat_view,
    "coverage": coverage_view,
}
