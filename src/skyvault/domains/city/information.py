"""The information environment CYBERHOUND describes, as pure functions.

Important:
Formal Spec 5.2 and 9.2: CYBERHOUND sees the information environment,
emotional pressure, spread paths and cognitive risk, and gets back how
opinion moved, the pressure it put on public order and the risk of
backlash. The model is off unless the world's rule set carries
city.information, so a city without it runs exactly as before.

Each district carries emotional_pressure (0–100). Every tick it moves by:
  shortage   less than a tick's food left
  dark       no power
  unrest     its order is in unrest (twice that in riot)
  rumor      sources active this tick (rules.information.sources)
  spread     from each neighbour on the road network with more pressure:
             spread × the neighbour's communication × the difference
  decay      a share of its own pressure fades
Pressure pulls public order down (order_weight per 100 pressure, in
order_delta); police patrolling a district at or above backlash_threshold
gain less order and raise pressure (backlash); the city office can answer
with counter-messaging (inform).
"""

from typing import Any

OPINION_STATES = ("calm", "uneasy", "agitated", "inflamed")
DEFAULTS: dict[str, Any] = {
    "shortage": 4.0,
    "dark": 3.0,
    "unrest": 2.0,
    "spread": 0.25,
    "decay": 0.1,
    "order_weight": 2.0,
    "backlash_threshold": 60.0,
    "backlash": 5.0,
    "backlash_dampen": 0.6,
    "counter": 12.0,
    "inform_at": 50.0,
    "initial": {},
    "sources": [],
}


def information_rules(rules: dict[str, Any]) -> dict[str, Any] | None:
    """The information rules with defaults filled, or None when the model is off."""
    given = rules.get("information")
    if given is None:
        return None
    return {**DEFAULTS, **given}


def opinion_state(pressure: float) -> str:
    """calm below 25, uneasy below 50, agitated below 75, inflamed above."""
    return OPINION_STATES[min(3, int(float(pressure) // 25))]


def pressure_of(
    district: dict[str, Any], info: dict[str, Any], entity_id: str
) -> float:
    """A district's emotional pressure: its state, else the initial value, else 0."""
    if "emotional_pressure" in district:
        return float(district["emotional_pressure"])
    return float(info["initial"].get(entity_id, 0.0))


def active_sources(info: dict[str, Any], tick: int) -> dict[str, float]:
    """Rumor magnitude per district from sources active at tick."""
    found: dict[str, float] = {}
    for source in info["sources"]:
        start = int(source.get("tick", 0))
        until = int(source.get("until", start))
        if start <= tick <= until:
            district = str(source["district"])
            found[district] = found.get(district, 0.0) + float(source["magnitude"])
    return found


def pressure_step(
    districts: dict[str, dict[str, Any]],
    neighbours: dict[str, list[str]],
    rumors: dict[str, float],
    info: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    One tick of the information environment.

    districts: {id: {pressure, short, powered, order_state, communication}};
    neighbours: {id: [ids]} on the road network; rumors: active_sources.
    Returns {id: {before, after, parts, spread_from}}: spread_from lists
    the neighbours pressure came from and how much, largest first — the
    spread paths. All districts move together from the same before-state.
    """
    out: dict[str, dict[str, Any]] = {}
    for did in sorted(districts):
        d = districts[did]
        before = float(d["pressure"])
        spread_from = []
        for other in sorted(neighbours.get(did, [])):
            o = districts[other]
            gap = float(o["pressure"]) - before
            if gap > 0:
                amount = round(info["spread"] * float(o["communication"]) * gap, 4)
                if amount > 0:
                    spread_from.append({"from": other, "amount": amount})
        spread_from.sort(key=lambda row: (-row["amount"], row["from"]))
        parts = {
            "shortage": float(info["shortage"]) if d["short"] else 0.0,
            "dark": 0.0 if d["powered"] else float(info["dark"]),
            "unrest": float(info["unrest"])
            * {"unrest": 1, "riot": 2}.get(d["order_state"], 0),
            "rumor": float(rumors.get(did, 0.0)),
            "spread": sum(row["amount"] for row in spread_from),
            "decay": -float(info["decay"]) * before,
        }
        parts = {key: round(value, 4) for key, value in parts.items()}
        parts["total"] = round(sum(parts.values()), 4)
        after = round(min(100.0, max(0.0, before + parts["total"])), 4)
        out[did] = {
            "before": before,
            "after": after,
            "parts": parts,
            "spread_from": spread_from,
        }
    return out


def order_pull(pressure: float, info: dict[str, Any]) -> float:
    """How much emotional pressure pulls public order down this tick (≤ 0)."""
    return round(-float(info["order_weight"]) * float(pressure) / 100.0, 4)


def backlash(pressure: float, info: dict[str, Any]) -> bool:
    """Does a patrol here backfire? At or above backlash_threshold."""
    return float(pressure) >= float(info["backlash_threshold"])
