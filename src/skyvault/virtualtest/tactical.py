"""tactical_usefulness = does the equipment help in a mission, and where.

Important:
The profile replaces one unit of a military scenario (the first unit of its
side whose type matches the profile's mission_role) and the scenario runs
over the same seeds with and without it. The mapping (unit_changes) is a
screening assumption, recorded in ADR 020:

hp              the replaced unit's hp × the category's hp_factor
move_range      +1 at a power-to-mass of fast_power_to_mass W/kg or more,
                −1 (at least 1) below slow_power_to_mass
accuracy        × (1 − (operator_fatigue − infantry_fatigue) × mission hours / 2),
                held to 0.5–1.2 and at most 0.95: tiring faster than an
                unequipped infantryman costs aim, tiring slower gains it
terrain_access  physics.accessible_terrain
endurance_ticks the effective endurance, one military tick = tick_minutes

The profile's own capabilities and state are then copied over (the Phase 12
path). Per context the difference against the baseline is read:

useful   mean score up by at least useful_delta and missions not less often,
         or missions more often with the score not down by useful_delta
weak     mean score down by at least useful_delta, or missions less often

The score is the mean over the applicable contexts of 0.5 + 2·Δscore +
0.5·Δmission, each held to 0–1. A scenario with no unit of the role is not
applicable (listed, not scored).
"""

import copy
import math
from pathlib import Path
from typing import Any

from ..domains import load_domain
from ..engine import SkyVaultEngine
from ..scenario_loader import load_scenario
from .engineering import maintenance_ratio
from .physics import accessible_terrain, effective_endurance
from .profile import param, physical

SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
TRANSPORT = {"none": 0, "truck": 0, "heavy_truck": 1, "heavy_lift": 2, "aircraft": 2}


def replaced_unit(
    scenario: dict[str, Any], profile: dict, rules: dict, replace: str | None = None
) -> dict | None:
    """
    The unit the equipment takes the place of, or None: the unit named
    replace (STAR GUARD names one), else the first of its role on the side.
    """
    if replace is not None:
        return next(
            (e for e in scenario["entities"] if e["entity_id"] == replace), None
        )
    tactical = rules["tactical"]
    role = param(profile, "operational_parameters", "mission_role") or "assault"
    wanted = tactical["roles"][role]
    candidates = sorted(
        (
            e
            for e in scenario["entities"]
            if e["faction"] == tactical["side"] and e["entity_type"] == wanted
        ),
        key=lambda e: e["entity_id"],
    )
    return candidates[0] if candidates else None


def unit_changes(
    profile: dict[str, Any],
    rules: dict[str, Any],
    unit: dict[str, Any],
    max_ticks: int,
) -> dict[str, Any]:
    """{name, capabilities, state}: the replaced unit as the equipment."""
    tactical = rules["tactical"]
    envelope = rules["categories"].get(profile["category"], {})
    capabilities = copy.deepcopy(unit["capabilities"])
    state = copy.deepcopy(unit["state"])
    state["hp"] = round(float(state["hp"]) * float(envelope.get("hp_factor", 1.0)), 4)
    mass, power = physical(profile, "mass"), physical(profile, "power_requirement")
    if mass and power is not None:
        specific = power * 1000 / mass
        move = int(capabilities.get("move_range", 1))
        if specific >= float(tactical["fast_power_to_mass"]):
            move += 1
        elif specific < float(tactical["slow_power_to_mass"]):
            move = max(1, move - 1)
        capabilities["move_range"] = move
    fatigue = param(profile, "operational_parameters", "operator_fatigue")
    if fatigue is not None and "accuracy" in capabilities:
        hours = max_ticks * float(rules["tick_minutes"]) / 60
        excess = float(fatigue) - float(tactical["infantry_fatigue"])
        factor = min(1.2, max(0.5, 1 - excess * hours / 2))
        aim = min(0.95, float(capabilities["accuracy"]) * factor)
        capabilities["accuracy"] = round(aim, 4)
    capabilities["terrain_access"] = accessible_terrain(profile, rules)
    hours_left = effective_endurance(profile)
    if hours_left is not None:
        capabilities["endurance_ticks"] = math.floor(
            hours_left * 60 / float(rules["tick_minutes"])
        )
    capabilities.update(copy.deepcopy(profile.get("capabilities") or {}))
    state.update(copy.deepcopy(profile.get("state") or {}))
    return {
        "name": profile["equipment_id"],
        "capabilities": capabilities,
        "state": state,
    }


def _run(scenario: dict[str, Any], seed: int) -> dict[str, Any]:
    scenario = copy.deepcopy(scenario)
    scenario["runtime"]["random_seed"] = seed
    return SkyVaultEngine(scenario).run()


def _measure(
    scenario: dict[str, Any], seeds: list[int], unit_id: str, side: str
) -> dict[str, float]:
    judge = load_domain(scenario["domain"]).mission_outcome  # type: ignore[attr-defined]
    scores, missions, survived = [], [], []
    for seed in seeds:
        package = _run(scenario, seed)
        scores.append(float(package["evaluation_result"]["overall_score"]))
        outcome = judge(package, scenario)
        missions.append(bool(outcome.get(side, {}).get("achieved")))
        status = package["final_world_state"]["entities"][unit_id]["state"]
        survived.append(status.get("status", "active") == "active")
    n = len(seeds)
    return {
        "mean_score": round(sum(scores) / n, 4),
        "mission_rate": round(sum(missions) / n, 4),
        "unit_survival": round(sum(survived) / n, 4),
    }


def logistics_burden(profile: dict[str, Any], rules: dict[str, Any]) -> str:
    """low / medium / high from transport, maintenance, deployment and supply."""
    points = TRANSPORT.get(
        param(profile, "operational_parameters", "transport_requirement") or "none", 0
    )
    ratio = maintenance_ratio(profile)
    if ratio is not None:
        points += 2 if ratio > 1 else 1 if ratio > 0.5 else 0
    deploy = param(profile, "operational_parameters", "deployment_time")
    if deploy is not None:
        points += 2 if float(deploy) > 60 else 1 if float(deploy) > 20 else 0
    risk = param(profile, "engineering_parameters", "supply_chain_risk")
    if risk is not None and float(risk) >= float(
        rules["engineering"]["supply_risk_high"]
    ):
        points += 1
    return "low" if points <= 1 else "medium" if points <= 3 else "high"


def tactical_usefulness(
    profile: dict[str, Any],
    rules: dict[str, Any],
    scenarios: list[str] | None = None,
    seeds: list[int] | None = None,
    replace: str | None = None,
) -> dict[str, Any]:
    """{score, useful_contexts, weak_contexts, logistics_burden, contexts, unit}."""
    tactical = rules["tactical"]
    names = list(scenarios or tactical["scenarios"])
    seeds = list(seeds or tactical["seeds"])
    delta = float(tactical["useful_delta"])
    contexts, useful, weak, values = [], [], [], []
    unit_seen: dict[str, Any] = {}
    for name in names:
        scenario_id, _, version = name.partition("/")
        scenario = load_scenario(SCENARIOS / scenario_id / f"{version or 'v0.1'}.json")
        unit = replaced_unit(scenario, profile, rules, replace)
        if unit is None:
            contexts.append({"scenario": name, "applicable": False})
            continue
        changes = unit_changes(
            profile, rules, unit, int(scenario["runtime"]["max_ticks"])
        )
        equipped = copy.deepcopy(scenario)
        target = next(
            e for e in equipped["entities"] if e["entity_id"] == unit["entity_id"]
        )
        target["name"] = changes["name"]
        target["capabilities"] = changes["capabilities"]
        target["state"] = changes["state"]
        side = str(unit["faction"])
        with_it = _measure(equipped, seeds, unit["entity_id"], side)
        without = _measure(scenario, seeds, unit["entity_id"], side)
        diff = {k: round(with_it[k] - without[k], 4) for k in with_it}
        value = min(
            1.0,
            max(0.0, 0.5 + 2 * diff["mean_score"] + 0.5 * diff["mission_rate"]),
        )
        values.append(value)
        better = diff["mean_score"] >= delta and diff["mission_rate"] >= 0
        if better or (diff["mission_rate"] > 0 and diff["mean_score"] > -delta):
            useful.append(name)
        elif diff["mean_score"] <= -delta or diff["mission_rate"] < 0:
            weak.append(name)
        unit_seen = {"replaces": unit["entity_id"], **changes}
        contexts.append(
            {
                "scenario": name,
                "applicable": True,
                "replaces": unit["entity_id"],
                "equipped": with_it,
                "baseline": without,
                "versus_baseline": diff,
                "value": round(value, 4),
            }
        )
    return {
        "score": round(sum(values) / len(values), 4) if values else None,
        "useful_contexts": useful,
        "weak_contexts": weak,
        "logistics_burden": logistics_burden(profile, rules),
        "contexts": contexts,
        "unit": unit_seen,
    }
