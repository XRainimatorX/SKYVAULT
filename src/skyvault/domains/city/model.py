"""The city's model as pure functions: public order, power, travel.

Important:
Nothing here touches a world or runs a simulation. The handlers read the
world, call these, and turn the answers into consequences.

public_order is 0–100 in each district. order_state names its band:
stable ≥ rules.order.stable, tense ≥ tense, unrest ≥ unrest, riot below.
"""

import math
from typing import Any

ORDER_STATES = ("riot", "unrest", "tense", "stable")


def order_state(value: float, rules: dict[str, Any]) -> str:
    """The band public order value falls in (thresholds from rules.order)."""
    order = rules["order"]
    if value >= order["stable"]:
        return "stable"
    if value >= order["tense"]:
        return "tense"
    if value >= order["unrest"]:
        return "unrest"
    return "riot"


def consumption(population: float, rules: dict[str, Any]) -> float:
    """Food a district eats in one tick."""
    return float(population) / 10_000 * float(rules["food"]["per_10k"])


def demand(population: float, rules: dict[str, Any]) -> float:
    """Power a district draws."""
    return float(population) / 10_000 * float(rules["power"]["demand_per_10k"])


def order_delta(conditions: dict[str, Any], rules: dict[str, Any]) -> dict[str, float]:
    """
    How one tick moves a district's public order, part by part.

    conditions: food_left (after eating), eaten (this tick's consumption),
    powered, medical and administration (effective, 0–1), population,
    riot_next_door, and night (the share of the tick that is night, 1 when
    absent: darkness costs order at night only, Phase 23). Returns each part
    and their sum ("total").

    Important:
    Hunger hurts more where more people live (pressure_per_100k). A fed,
    lit district drifts back towards order (recovery); a riot next door
    pulls it down.
    """
    order = rules["order"]
    fed = conditions["food_left"] > 0
    parts = {
        "hunger": 0.0,
        "short_food": 0.0,
        "dark": 0.0,
        "medical": (conditions["medical"] - order["medical_par"])
        * order["medical_weight"],
        "administration": (conditions["administration"] - order["administration_par"])
        * order["administration_weight"],
        "recovery": 0.0,
        "riot_next_door": (
            order["riot_neighbour"] if conditions["riot_next_door"] else 0.0
        ),
    }
    if not fed:
        pressure = 1 + order["pressure_per_100k"] * conditions["population"] / 100_000
        parts["hunger"] = order["hunger"] * pressure
    elif conditions["food_left"] < conditions["eaten"] * rules["food"]["short_ticks"]:
        parts["short_food"] = order["short_food"]
    if not conditions["powered"]:
        parts["dark"] = order["dark"] * float(conditions.get("night", 1.0))
    if fed and conditions["powered"]:
        parts["recovery"] = order["recovery"]
    parts = {key: round(value, 4) for key, value in parts.items()}
    parts["total"] = round(sum(parts.values()), 4)
    return parts


def power_flow(
    substations: dict[str, dict[str, Any]], loads: dict[str, float]
) -> dict[str, Any]:
    """
    Which substation feeds which district, and which are overloaded.

    substations: {id: {capacity, serves, backup, online, transfers}};
    loads: {district: demand}. A district is fed by the substation that
    serves it while that one is online. When it is offline and transfers
    (it failed), its districts move to its backups — the i-th district to
    the i-th online backup, round robin — and are dark when no backup is
    online. A substation that does not transfer (protection tripped it)
    keeps its districts dark until it is back. Overloaded: an online
    substation whose load is above its capacity.

    Returns {feeds: {district: substation | None}, load: {substation: load},
    overloaded: [substation ids], moved: {district: offline substation}}.
    """
    feeds: dict[str, str | None] = {}
    moved: dict[str, str] = {}
    for sub_id in sorted(substations):
        sub = substations[sub_id]
        backups = [b for b in sub["backup"] if substations.get(b, {}).get("online")]
        for n, district in enumerate(sub["serves"]):
            if sub["online"]:
                feeds[district] = sub_id
            elif backups and sub.get("transfers", True):
                feeds[district] = backups[n % len(backups)]
                moved[district] = sub_id
            else:
                feeds[district] = None
    load = {sub_id: 0.0 for sub_id in substations}
    for district, feeder in feeds.items():
        if feeder is not None:
            load[feeder] += float(loads.get(district, 0.0))
    load = {sub_id: round(value, 4) for sub_id, value in load.items()}
    overloaded = sorted(
        sub_id
        for sub_id, sub in substations.items()
        if sub["online"] and load[sub_id] > float(sub["capacity"])
    )
    return {"feeds": feeds, "load": load, "overloaded": overloaded, "moved": moved}


def eta(distance: float, factor: float) -> int:
    """
    Ticks a trip takes: the route's travel ticks times factor, rounded up;
    at least one tick for any trip, none for staying put.
    """
    if distance == 0:
        return 0
    if math.isinf(distance):
        raise ValueError("no road leads there")
    return max(1, math.ceil(round(float(distance) * float(factor), 6)))


def night_share(
    start_hour: float | None, hours: float, night_from: float, night_to: float
) -> float:
    """
    The share of a step of hours, starting at start_hour of the day, that
    falls between night_from and night_to (night_to < night_from: the night
    crosses midnight). start_hour None (the clock has no time of day): the
    share of a whole day that is night.
    """
    night = (night_to - night_from) % 24
    if start_hour is None or hours <= 0:
        return round(night / 24, 4)
    covered = 0.0
    for day in range(int((start_hour + hours) // 24) + 2):
        begin = night_from + 24 * (day - 1)
        covered += max(
            0.0, min(begin + night, start_hour + hours) - max(begin, start_hour)
        )
    return round(min(1.0, covered / hours), 4)
