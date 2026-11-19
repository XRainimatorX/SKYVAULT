"""The governance stability score: how steadily a city is governed, from its package.

Important:
Pure: it reads the package's replay of every tick and the scenario's
rules, imports nothing that runs a simulation, and leaves the core
evaluation untouched (it is the pack's model, like mission_outcome).

Each tick has four components, each 0–1, all weighted by population:

order           public order / 100
services        the mean of power (0 or 1), food on hand (as a share of
                rules.food.short_ticks ticks of eating, at most 1) and
                medical care (halved in the dark: rules.power.dark_medical)
administration  administrative capacity
trend           0.5 + the change of order over the last trend_span ticks
                / 40 points, clamped — rising order scores above 0.5

The tick's score is their weighted sum (rules.score.weights). The run's
score is the mean over its last rules.score.window share of ticks: how the
city stands at the end, not how it started.
"""

import math
from typing import Any

from ...observation.history import history_from_package
from .model import consumption

COMPONENTS = ("order", "services", "administration", "trend")


def population_order(states: dict[str, dict[str, Any]]) -> float:
    """Public order weighted by population (0 when nobody lives there)."""
    people = sum(float(s["population"]) for s in states.values())
    if people <= 0:
        return 0.0
    return round(
        sum(float(s["public_order"]) * float(s["population"]) for s in states.values())
        / people,
        4,
    )


def _weighted(states: dict[str, dict[str, Any]], value: Any) -> float:
    people = sum(float(s["population"]) for s in states.values())
    if people <= 0:
        return 0.0
    return sum(value(s) * float(s["population"]) for s in states.values()) / people


def components_at(
    states: dict[str, dict[str, Any]],
    order_before: float,
    rules: dict[str, Any],
) -> dict[str, float]:
    """The four components of one tick (order_before: weighted order trend_span ago)."""
    dark_medical = float(rules["power"]["dark_medical"])
    short = float(rules["food"]["short_ticks"])

    def services(s: dict[str, Any]) -> float:
        eaten = consumption(s["population"], rules)
        food = 1.0 if eaten <= 0 else min(1.0, float(s["food"]) / (eaten * short))
        medical = float(s["medical"]) * (1.0 if s["power"] else dark_medical)
        return (float(s["power"]) + food + medical) / 3

    order = population_order(states)
    return {
        "order": round(order / 100, 4),
        "services": round(_weighted(states, services), 4),
        "administration": round(
            _weighted(states, lambda s: float(s["administration"])), 4
        ),
        "trend": round(min(1.0, max(0.0, 0.5 + (order - order_before) / 40)), 4),
    }


def governance_stability(
    package: dict[str, Any], scenario: dict[str, Any]
) -> dict[str, Any]:
    """
    {score, components, window, series, start, districts}: the run's score
    and components (means over the window), the ticks the window covers,
    every tick's components and score, tick 0's score, and each district
    at the end.
    """
    rules = scenario["world_contract"]["rule_set"]["city"]
    weights = rules["score"]["weights"]
    span = int(rules["score"]["trend_span"])
    history = history_from_package(package)

    def district_states(units: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            unit_id: unit["state"]
            for unit_id, unit in units.items()
            if unit["entity_type"] == "district"
        }

    orders = {
        tick: population_order(district_states(units))
        for tick, units in history.items()
    }
    series = []
    for tick, units in sorted(history.items()):
        parts = components_at(
            district_states(units), orders[max(0, tick - span)], rules
        )
        score = round(sum(weights[c] * parts[c] for c in COMPONENTS), 4)
        series.append({"tick": tick, **parts, "score": score})

    ticks = [row for row in series if row["tick"] > 0] or series
    size = max(1, math.ceil(len(ticks) * float(rules["score"]["window"])))
    window = ticks[-size:]
    last = district_states(history[max(history)])
    return {
        "score": round(sum(row["score"] for row in window) / len(window), 4),
        "components": {
            c: round(sum(row[c] for row in window) / len(window), 4) for c in COMPONENTS
        },
        "window": [window[0]["tick"], window[-1]["tick"]],
        "start": series[0]["score"],
        "series": series,
        "districts": {
            district_id: {
                "public_order": state["public_order"],
                "order_state": state["order_state"],
                "power": state["power"],
                "food": state["food"],
            }
            for district_id, state in sorted(last.items())
        },
    }


RECOVERY_MEASURES = ("industry", "administration", "medical", "power", "logistics")


def recovery_outcome(package: dict[str, Any], scenario: dict[str, Any]) -> dict:
    """
    How fast the city recovers (SKYVAULT Definition VI.C, 戰後重建: industry,
    infrastructure, medical care and logistics), measure by measure.

    Important:
    industry, administration and medical are population-weighted means;
    power is the share of people with power; logistics the food delivered in
    the step (SUPPLY events). For each: where it started, its lowest point
    and when, where it ended, and the first time after the lowest point it
    was back at its start (recovered_at; None if it never was). A measure
    that never fell recovers at its start.
    """
    history = history_from_package(package)
    delivered: dict[int, float] = {}
    for event in package["event_memory"]:
        if event["event_type"] == "SUPPLY":
            time = int(event["time"])
            delivered[time] = delivered.get(time, 0.0) + float(
                event["data"]["delivered"]
            )

    def values(units: dict[str, Any], tick: int) -> dict[str, float]:
        states = {
            k: u["state"] for k, u in units.items() if u["entity_type"] == "district"
        }
        return {
            "industry": _weighted(states, lambda s: float(s["industry"])),
            "administration": _weighted(states, lambda s: float(s["administration"])),
            "medical": _weighted(states, lambda s: float(s["medical"])),
            "power": _weighted(states, lambda s: float(s["power"])),
            "logistics": delivered.get(tick, 0.0),
        }

    series = [(tick, values(units, tick)) for tick, units in sorted(history.items())]
    measures = {}
    for name in RECOVERY_MEASURES:
        points = [(tick, round(v[name], 4)) for tick, v in series]
        start = points[0][1]
        low_tick, low = min(points, key=lambda p: (p[1], p[0]))
        back = next(
            (tick for tick, value in points if tick >= low_tick and value >= start),
            None,
        )
        measures[name] = {
            "start": start,
            "lowest": low,
            "lowest_at": low_tick,
            "end": points[-1][1],
            "recovered_at": back,
        }
    return {
        "measures": measures,
        "recovered": sorted(
            n for n, m in measures.items() if m["recovered_at"] is not None
        ),
        "not_recovered": sorted(
            n for n, m in measures.items() if m["recovered_at"] is None
        ),
        "end_tick": series[-1][0],
    }
