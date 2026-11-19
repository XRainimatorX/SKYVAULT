"""Disasters = floods, fires and closed roads in a city, as pure functions.

Important:
SKYVAULT Definition VI.C: 災害應變 — floods, fires, blackouts, roads cut.
A city's rules may list disasters (rules.city.disasters); without them the
city runs exactly as before. Each disaster starts at its tick and lasts
duration steps:

    flood         a district: food spoils (× 1 − severity), medical care
                  falls (× 1 − severity / 2), public order drops (10 ×
                  severity); every road into it is cut while it lasts
    fire          a district: industry burns (× 1 − severity),
                  administration and medical care fall (× 1 − severity /
                  2), public order drops (5 × severity); roads stay open
                  unless closes_roads
    road_closure  one road [a, b] is cut while it lasts

A cut road is gone from every route: convoys, police and crews go round,
or cannot go at all.
"""

from typing import Any

DISASTERS = ("flood", "fire", "road_closure")


def active(disaster: dict[str, Any], tick: int) -> bool:
    """Is the disaster under way at tick (from its tick, for duration steps)?"""
    start = int(disaster["tick"])
    return start <= tick < start + int(disaster.get("duration", 1))


def closed_roads(
    rules: dict[str, Any], tick: int, edges: list[list[Any]]
) -> set[frozenset[str]]:
    """Every road cut at tick, as {a, b} pairs."""
    closed: set[frozenset[str]] = set()
    for disaster in rules.get("disasters", []):
        if not active(disaster, tick):
            continue
        if disaster["type"] == "road_closure":
            closed.add(frozenset(disaster["road"]))
        elif disaster["type"] == "flood" or disaster.get("closes_roads"):
            place = disaster["district"]
            closed |= {frozenset((a, b)) for a, b, *_ in edges if place in (a, b)}
    return closed


def damage(disaster: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What a flood or a fire does to its district's state when it starts."""
    severity = float(disaster.get("severity", 0.5))
    half = 1 - severity / 2
    if disaster["type"] == "flood":
        changes = {
            "food": float(state["food"]) * (1 - severity),
            "medical": float(state["medical"]) * half,
            "public_order": float(state["public_order"]) - 10 * severity,
        }
    elif disaster["type"] == "fire":
        changes = {
            "industry": float(state["industry"]) * (1 - severity),
            "administration": float(state["administration"]) * half,
            "medical": float(state["medical"]) * half,
            "public_order": float(state["public_order"]) - 5 * severity,
        }
    else:
        return {}
    changes["public_order"] = max(0.0, changes["public_order"])
    return {key: round(value, 4) for key, value in changes.items()}
