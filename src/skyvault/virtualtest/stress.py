"""Where the equipment fails: stress conditions, failure points, collapse sequence.

Important:
Pure: no simulation runs here. Each condition in rules.stress moves one
quantity by a factor per level (mild → collapse) and the physics and
engineering are judged again:

payload             mass × 1.1 / 1.25 / 1.5 / 2
heat                cooling_capacity × 0.9 / 0.75 / 0.5 / 0.25 (a hot day)
soft_ground         every terrain's bearing × 0.75 / 0.5 / 0.25 / 0.1
extended_mission    the endurance asked of it × 1.25 / 1.5 / 2 / 3
supply_disruption   maintenance_time × 1.25 / 1.5 / 2 / 3

A condition breaks the equipment at the first level where a check that was
not impossible becomes so, or where the engineering score falls below
worth_investing having been above it. The collapse sequence raises every
condition together and lists what fails in the order it fails.
"""

import copy
from typing import Any

from .engineering import engineering_feasibility
from .physics import physical_possibility


def stressed(
    profile: dict[str, Any], rules: dict[str, Any], condition: str, level: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The profile and rules under one condition at one level."""
    spec = rules["stress"]["conditions"][condition]
    factor = float(spec["factors"][rules["stress"]["levels"].index(level)])
    profile, rules = copy.deepcopy(profile), copy.deepcopy(rules)
    if spec["group"] == "rules":
        rules["terrain_bearing_kpa"] = {
            name: round(float(kpa) * factor, 6)
            for name, kpa in rules["terrain_bearing_kpa"].items()
        }
        return profile, rules
    group = profile.setdefault(spec["group"], {})
    if group.get(spec["parameter"]) is not None:
        group[spec["parameter"]] = round(float(group[spec["parameter"]]) * factor, 6)
    return profile, rules


def _broken(profile: dict[str, Any], rules: dict[str, Any]) -> set[str]:
    """The checks that are impossible, plus "engineering" when not worth it."""
    physics = physical_possibility(profile, rules)
    found = {c["check"] for c in physics["checks"] if c["status"] == "impossible"}
    worth = float(rules["engineering"]["worth_investing"])
    if engineering_feasibility(profile, rules)["score"] < worth:
        found.add("engineering")
    return found


def explore_equipment(profile: dict[str, Any], rules: dict[str, Any]) -> dict:
    """
    {failure_points, collapse_sequence, baseline_broken}.

    failure_points: per condition, the first level that breaks something new
    and what it breaks (level None: it holds through collapse).
    collapse_sequence: [{level, fails}] as all conditions rise together.
    """
    levels = rules["stress"]["levels"]
    baseline = _broken(profile, rules)
    points = []
    for condition in rules["stress"]["conditions"]:
        point: dict[str, Any] = {"condition": condition, "level": None, "breaks": []}
        for level in levels:
            new = sorted(
                _broken(*stressed(profile, rules, condition, level)) - baseline
            )
            if new:
                point = {"condition": condition, "level": level, "breaks": new}
                break
        points.append(point)
    sequence = []
    seen = set(baseline)
    for level in levels:
        current_profile, current_rules = profile, rules
        for condition in rules["stress"]["conditions"]:
            current_profile, current_rules = stressed(
                current_profile, current_rules, condition, level
            )
        new = sorted(_broken(current_profile, current_rules) - seen)
        if new:
            sequence.append({"level": level, "fails": new})
            seen |= set(new)
    return {
        "failure_points": points,
        "collapse_sequence": sequence,
        "baseline_broken": sorted(baseline),
    }
