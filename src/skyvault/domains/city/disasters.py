"""Disasters = floods, fires and closed roads in a city, as pure functions.

Important:
SKYVAULT Definition VI.C: 災害應變 — floods, fires, blackouts, roads cut.
A city's rules may list disasters (rules.city.disasters); without them the
city runs exactly as before. Each disaster starts at its tick and lasts
duration steps. With severity s and the city rules' disaster_effects
(Phase 23: each coefficient's source and confidence is in
data/domains/city/calibration.json):

    flood         a district: food spoils (× 1 − food_loss·s), medical care
                  falls (× 1 − medical_loss·s), public order drops
                  (order_drop·s); while it lasts, every road into it is cut
                  when s ≥ road_cut_at and the district is dark when
                  s ≥ power_cut_at
    fire          a district: industry and the capacity behind it burn
                  (× 1 − industry_loss·s), administration and medical care
                  fall (× 1 − administration_loss·s, × 1 − medical_loss·s),
                  public order drops (order_drop·s); roads stay open unless
                  closes_roads
    road_closure  one road [a, b] is cut while it lasts

A cut road is gone from every route: convoys, police and crews go round,
or cannot go at all. EFFECTS is the same set as the rules' disaster_effects,
for rules written without them.
"""

from typing import Any

DISASTERS = ("flood", "fire", "road_closure")
EFFECTS: dict[str, dict[str, float]] = {
    "flood": {
        "food_loss": 1.0,
        "medical_loss": 0.5,
        "order_drop": 10.0,
        "road_cut_at": 0.6,
        "power_cut_at": 0.0,
    },
    "fire": {
        "industry_loss": 1.0,
        "administration_loss": 0.5,
        "medical_loss": 0.5,
        "order_drop": 5.0,
    },
}


def effects_of(rules: dict[str, Any], kind: str) -> dict[str, float]:
    """The coefficients of one kind of disaster: the rules', else EFFECTS."""
    given = rules.get("disaster_effects", {}).get(kind, {})
    return {**EFFECTS[kind], **given}


def severity_of(disaster: dict[str, Any]) -> float:
    """A disaster's severity (0.5 when the spec gives none)."""
    return float(disaster.get("severity", 0.5))


def active(disaster: dict[str, Any], tick: int) -> bool:
    """Is the disaster under way at tick (from its tick, for duration steps)?"""
    start = int(disaster["tick"])
    return start <= tick < start + int(disaster.get("duration", 1))


def closed_roads(
    rules: dict[str, Any], tick: int, edges: list[list[Any]]
) -> set[frozenset[str]]:
    """Every road cut at tick, as {a, b} pairs."""
    closed: set[frozenset[str]] = set()
    cut_at = effects_of(rules, "flood")["road_cut_at"]
    for disaster in rules.get("disasters", []):
        if not active(disaster, tick):
            continue
        if disaster["type"] == "road_closure":
            closed.add(frozenset(disaster["road"]))
            continue
        flooded = disaster["type"] == "flood" and severity_of(disaster) >= cut_at
        if flooded or disaster.get("closes_roads"):
            place = disaster["district"]
            closed |= {frozenset((a, b)) for a, b, *_ in edges if place in (a, b)}
    return closed


def flooded_dark(rules: dict[str, Any], tick: int) -> set[str]:
    """Districts a flood under way at tick has left without power."""
    cut_at = effects_of(rules, "flood")["power_cut_at"]
    return {
        str(disaster["district"])
        for disaster in rules.get("disasters", [])
        if disaster["type"] == "flood"
        and active(disaster, tick)
        and severity_of(disaster) >= cut_at
    }


def damage(
    disaster: dict[str, Any],
    state: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What a flood or a fire does to its district's state when it starts."""
    if disaster["type"] not in ("flood", "fire"):
        return {}
    effects = effects_of(rules or {}, disaster["type"])
    severity = severity_of(disaster)

    def left(loss: str) -> float:
        return 1 - effects[loss] * severity

    order = float(state["public_order"]) - effects["order_drop"] * severity
    if disaster["type"] == "flood":
        changes = {
            "food": float(state["food"]) * left("food_loss"),
            "medical": float(state["medical"]) * left("medical_loss"),
        }
    else:
        changes = {
            "industry": float(state["industry"]) * left("industry_loss"),
            "industry_capacity": float(state.get("industry_capacity", 1.0))
            * left("industry_loss"),
            "administration": float(state["administration"])
            * left("administration_loss"),
            "medical": float(state["medical"]) * left("medical_loss"),
        }
    changes = {key: max(0.0, value) for key, value in changes.items()}
    changes["public_order"] = max(0.0, order)
    return {key: round(value, 4) for key, value in changes.items()}
