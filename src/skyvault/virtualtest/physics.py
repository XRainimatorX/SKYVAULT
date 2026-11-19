"""physical_possibility = the physics-lite rules: is this roughly possible at all?

Important:
Pure functions over a profile and the rules. Six checks, each a margin —
how far the design is inside its limit, as a share of the limit (0.3 =
30 % to spare, −0.1 = 10 % over):

stability        (base_width / 2) / center_of_gravity against the category's
                 minimum: how far it leans before it tips, statically
joint_load       each supporting joint's rating against mass · g · the
                 category's dynamic factor, shared by half the load-bearing
                 joints (a biped stands on one leg mid-stride)
ground_pressure  mass · g / footprint against the bearing of open ground;
                 the terrain it can stand on follows from the same pressure
energy           energy_capacity against power_requirement × endurance:
                 can the declared endurance be powered
heat             cooling_capacity against heat_output; short of it the
                 equipment runs only part of the time (its duty)
scale            mass / height³ against the category's range: outside it,
                 the rules here were not made for the design

A margin below 0 is impossible, except heat (a warning while the duty is
at least heat_min_duty) and scale (a warning: physics-lite cannot say). A
margin below warning_margin is a warning. A check whose inputs the profile
does not give is "unknown": it is listed, never passed.

These are screening rules, not engineering: they say where to look, and
external.py says when a real simulation is needed.
"""

from typing import Any

from .profile import category_rules, param, physical

CHECKS = ("stability", "joint_load", "ground_pressure", "energy", "heat", "scale")


def _ratio_margin(available: float, needed: float) -> float:
    if needed <= 0:
        return 1.0 if available > 0 else 0.0
    return round(available / needed - 1, 6)


def ground_pressure_kpa(profile: dict[str, Any], rules: dict[str, Any]) -> float | None:
    mass, footprint = physical(profile, "mass"), physical(profile, "footprint")
    if mass is None or not footprint:
        return None
    return round(mass * float(rules["gravity"]) / footprint / 1000, 6)


def accessible_terrain(profile: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    """
    The terrain the equipment can stand on and go into: bearing at least its
    ground pressure, no building when taller than max_height_indoors, and
    only what the profile's own terrain_accessibility allows.
    """
    pressure = ground_pressure_kpa(profile, rules)
    height = physical(profile, "height")
    names = []
    for name, bearing in rules["terrain_bearing_kpa"].items():
        if pressure is not None and float(bearing) < pressure:
            continue
        if (
            name == "building"
            and height is not None
            and height > float(rules["max_height_indoors"])
        ):
            continue
        names.append(name)
    declared = param(profile, "operational_parameters", "terrain_accessibility")
    if declared is not None:
        names = [n for n in names if n in set(declared)]
    return sorted(names)


def effective_endurance(profile: dict[str, Any]) -> float | None:
    """Hours the energy store powers the equipment, capped at the declared endurance."""
    power = physical(profile, "power_requirement")
    capacity = physical(profile, "energy_capacity")
    declared = physical(profile, "endurance")
    if power is None or capacity is None:
        return declared
    if power == 0:
        return declared
    hours = capacity / power
    return round(hours if declared is None else min(hours, declared), 6)


def margins(profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, float | None]:
    """Each check's margin, or None when the profile does not give its inputs."""
    envelope = category_rules(profile, rules) or {}
    g = float(rules["gravity"])
    p = {name: physical(profile, name) for name in (
        "mass", "height", "center_of_gravity", "joint_load", "power_requirement",
        "heat_output", "endurance", "base_width", "footprint", "energy_capacity",
        "cooling_capacity",
    )}  # fmt: skip
    joints = param(profile, "physical_parameters", "load_bearing_joints")
    found: dict[str, float | None] = dict.fromkeys(CHECKS)
    if p["base_width"] is not None and p["center_of_gravity"] and envelope:
        ratio = p["base_width"] / 2 / p["center_of_gravity"]
        found["stability"] = _ratio_margin(ratio, float(envelope["min_stability"]))
    if p["mass"] is not None and p["joint_load"] is not None and joints and envelope:
        load = p["mass"] * g * float(envelope["dynamic_factor"]) / 1000
        found["joint_load"] = _ratio_margin(p["joint_load"], load / max(1, joints / 2))
    pressure = ground_pressure_kpa(profile, rules)
    if pressure is not None:
        found["ground_pressure"] = _ratio_margin(
            float(rules["terrain_bearing_kpa"]["open"]), pressure
        )
    if None not in (p["energy_capacity"], p["power_requirement"], p["endurance"]):
        need = float(p["power_requirement"] or 0) * float(p["endurance"] or 0)
        found["energy"] = _ratio_margin(float(p["energy_capacity"] or 0), need)
    if p["cooling_capacity"] is not None and p["heat_output"] is not None:
        found["heat"] = _ratio_margin(p["cooling_capacity"], p["heat_output"])
    if p["mass"] is not None and p["height"] and envelope:
        density = p["mass"] / p["height"] ** 3
        low, high = (float(x) for x in envelope["density"])
        # a massless design is as far outside every range as it can be
        found["scale"] = (
            round(min(density / low - 1, high / density - 1), 6)
            if density > 0
            else -1.0
        )
    return found


def _status(check: str, margin: float | None, rules: dict[str, Any]) -> str:
    if margin is None:
        return "unknown"
    if margin < 0:
        if check == "scale":
            return "warning"
        if check == "heat" and 1 + margin >= float(rules["heat_min_duty"]):
            return "warning"
        return "impossible"
    if margin < float(rules["warning_margin"]):
        return "warning"
    return "pass"


DETAIL = {
    "stability": "tips over at a smaller lean than its category allows",
    "joint_load": "its joints carry more than their rating while it moves",
    "ground_pressure": "it sinks into open ground",
    "energy": "its energy store cannot power the declared endurance",
    "heat": "it makes more heat than it can shed",
    "scale": "its mass for its height is outside what its category is",
}


def physical_possibility(profile: dict[str, Any], rules: dict[str, Any]) -> dict:
    """
    {score, warnings, impossible_flags, checks}: score is the mean over the
    known checks of 0.5 + margin (each held to 0–1), and 0 with any
    impossible flag. An unknown category is a warning.
    """
    checks: list[dict[str, Any]] = []
    for check, margin in margins(profile, rules).items():
        checks.append(
            {"check": check, "margin": margin, "status": _status(check, margin, rules)}
        )
    warnings = [
        f"{c['check']}: {DETAIL[c['check']]} (margin {c['margin']:+.2f})"
        for c in checks
        if c["status"] == "warning"
    ] + [
        f"{c['check']}: cannot judge — the profile does not give what it needs"
        for c in checks
        if c["status"] == "unknown"
    ]
    if category_rules(profile, rules) is None:
        warnings.append(
            f"category {profile['category']!r} has no envelope in the rules"
        )
    impossible = [
        f"{c['check']}: {DETAIL[c['check']]} (margin {c['margin']:+.2f})"
        for c in checks
        if c["status"] == "impossible"
    ]
    known = [float(c["margin"]) for c in checks if c["margin"] is not None]
    score = (
        0.0
        if impossible or not known
        else round(sum(min(1.0, max(0.0, 0.5 + m)) for m in known) / len(known), 4)
    )
    return {
        "score": score,
        "warnings": warnings,
        "impossible_flags": impossible,
        "checks": checks,
    }
