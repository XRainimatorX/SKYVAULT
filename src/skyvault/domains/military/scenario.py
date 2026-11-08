"""build_scenario = a compact military spec turned into a full SKYVAULT scenario.

Important:
The spec names profiles (unit types, formations, doctrines, command delay,
missions) and draws the map with terrain symbols. The built scenario has
every profile value written into it — capabilities and state on each unit,
terrain and morale in the world contract — so it runs and reproduces
without the profile file, and compare_scenarios sees every difference.
"""

import copy
from typing import Any

from ...contracts import SCHEMA_VERSION, validate_scenario

DOMAIN = "military"


def build_scenario(spec: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    """
    The scenario spec describes, validated against the scenario contract.

    Raises ValueError when a unit stands outside the map or on impassable
    ground, a symbol or profile name is unknown, or the map is not a
    rectangle.
    """
    rows = list(spec["map"])
    width, height = _size(rows)
    legend = {terrain["symbol"]: name for name, terrain in profiles["terrain"].items()}
    for y, row in enumerate(rows):
        for x, symbol in enumerate(row):
            if symbol not in legend:
                raise ValueError(f"unknown terrain symbol {symbol!r} at {[x, y]}")

    factions: dict[str, Any] = {}
    entities: list[dict[str, Any]] = []
    for faction, side in spec["factions"].items():
        factions[faction] = _faction_rules(faction, side, profiles)
        entities += _units(faction, side, profiles, rows, legend)

    doctrines = "/".join(f"{f}:{side['doctrine']}" for f, side in factions.items())
    scenario = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": spec["scenario_id"],
        "scenario_version": spec["scenario_version"],
        "scenario_type": "tactical",
        "domain": DOMAIN,
        "purpose": spec.get("purpose", ""),
        "version_control": {
            "version": spec["scenario_version"],
            "parent_version": None,
            "changed_from_previous": {
                "assumptions_changed": [],
                "data_changed": [],
                "rules_changed": [],
                "metrics_changed": [],
                "failure_variables_changed": [],
            },
            "change_reason": "Built from the military domain pack spec.",
        },
        "world_contract": {
            "world_id": f"{spec['scenario_id']}_world",
            "world_scope": "military_tactical",
            "purpose": [spec.get("purpose", "")],
            "space_model": {
                "type": "grid",
                "width": width,
                "height": height,
                "distance_model": "chebyshev",
            },
            "time_model": {"type": "tick", "max_ticks": spec["max_ticks"]},
            "assumption_registry": {
                "movement_model": "terrain_weighted_grid",
                "combat_resolution": "accuracy_cover_suppression",
                "sensing": "range_times_concealment",
                "command": "delay_and_order_loss",
                "actor_policy": f"military_baseline[{doctrines}]",
                "distance_model": "chebyshev",
            },
            "evaluation_targets": [
                "world_state_changed",
                "event_memory_created",
                "result_package_created",
            ],
            "entity_model": {
                "unit_types": sorted({entity["entity_type"] for entity in entities})
            },
            "environment_state": {"terrain": {"rows": rows, "legend": legend}},
            "resource_state": {"ammo": float(profiles["logistics"]["ammo_stock"])},
            "rule_set": {
                "action_costs": {
                    "supply": {"ammo": float(profiles["logistics"]["resupply_amount"])}
                },
                "military": {
                    "pack": f"{profiles['pack_id']}@{profiles['version']}",
                    "terrain": copy.deepcopy(profiles["terrain"]),
                    "morale": dict(profiles["morale"]),
                    "logistics": dict(profiles["logistics"]),
                    "factions": factions,
                },
            },
            "failure_variables": [],
        },
        "entities": entities,
        "runtime": {
            "max_ticks": spec["max_ticks"],
            "random_seed": spec["random_seed"],
            "deterministic_mode": True,
        },
        "evaluation": {
            "primary_metrics": [
                "event_count",
                "active_entities",
                "destroyed_entities",
                "winner_or_result",
            ],
            "failure_thresholds": ["all_entities_destroyed"],
            "perspective": next(iter(spec["factions"])),
        },
    }
    return validate_scenario(scenario)


def _size(rows: list[str]) -> tuple[int, int]:
    if not rows or len({len(row) for row in rows}) != 1 or not rows[0]:
        raise ValueError("the map must be a non-empty rectangle of terrain symbols")
    return len(rows[0]), len(rows)


def _faction_rules(
    faction: str, side: dict[str, Any], profiles: dict[str, Any]
) -> dict[str, Any]:
    if side["doctrine"] not in profiles["doctrines"]:
        raise ValueError(f"{faction}: unknown doctrine {side['doctrine']!r}")
    if side["command"] not in profiles["command_delay"]:
        raise ValueError(f"{faction}: unknown command profile {side['command']!r}")
    mission = dict(side["mission"])
    if mission["type"] not in profiles["missions"]:
        raise ValueError(f"{faction}: unknown mission {mission['type']!r}")
    if mission["type"] in ("seize", "hold") and not mission.get("objective"):
        raise ValueError(f"{faction}: a {mission['type']} mission needs an objective")
    mission["objective"] = [list(cell) for cell in mission.get("objective", [])]
    return {
        "doctrine": side["doctrine"],
        "command": dict(profiles["command_delay"][side["command"]]),
        "command_profile": side["command"],
        "mission": mission,
    }


def _units(
    faction: str,
    side: dict[str, Any],
    profiles: dict[str, Any],
    rows: list[str],
    legend: dict[str, str],
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for group in side["groups"]:
        if group["formation"] not in profiles["formations"]:
            raise ValueError(f"{faction}: unknown formation {group['formation']!r}")
        slots = profiles["formations"][group["formation"]]["slots"]
        if len(group["units"]) > len(slots):
            raise ValueError(
                f"{faction} {group['name']}: {len(group['units'])} units but the "
                f"{group['formation']} formation has {len(slots)} slots"
            )
        totals: dict[str, int] = {}
        for unit_type in group["units"]:
            totals[unit_type] = totals.get(unit_type, 0) + 1
        seen: dict[str, int] = {}
        for unit_type, (dx, dy) in zip(group["units"], slots, strict=False):
            if unit_type not in profiles["units"]:
                raise ValueError(f"{faction}: unknown unit type {unit_type!r}")
            seen[unit_type] = seen.get(unit_type, 0) + 1
            title = unit_type.replace("_", " ").title()
            if totals[unit_type] > 1:
                title += f" {seen[unit_type]}"
            x, y = group["anchor"][0] + dx, group["anchor"][1] + dy
            _check_ground(faction, title, x, y, rows, legend, profiles)
            entities.append(
                _unit(
                    f"{faction.lower()}_{len(entities) + 1:02d}",
                    f"{faction.title()} {group['name']} {title}",
                    faction,
                    unit_type,
                    group["name"],
                    [x, y],
                    profiles,
                )
            )
    return entities


def _check_ground(
    faction: str,
    title: str,
    x: int,
    y: int,
    rows: list[str],
    legend: dict[str, str],
    profiles: dict[str, Any],
) -> None:
    if not (0 <= y < len(rows) and 0 <= x < len(rows[0])):
        raise ValueError(f"{faction} {title} at {[x, y]} is outside the map")
    terrain = legend[rows[y][x]]
    if profiles["terrain"][terrain]["move_cost"] is None:
        raise ValueError(f"{faction} {title} at {[x, y]} stands on {terrain}")


def _unit(
    entity_id: str,
    name: str,
    faction: str,
    unit_type: str,
    group: str,
    position: list[int],
    profiles: dict[str, Any],
) -> dict[str, Any]:
    unit = profiles["units"][unit_type]
    weapon = profiles["weapons"][unit["weapon"]]
    capabilities: dict[str, Any] = {
        "move_range": unit["move_range"],
        "attack_range": weapon["range"],
        "attack_damage": weapon["damage"],
        "accuracy": weapon["accuracy"],
        "suppression": weapon["suppression"],
        "ammo_per_shot": weapon["ammo_per_shot"],
        "sensor_range": profiles["sensors"][unit["sensor"]]["range"],
        "max_ammo": unit["ammo"],
        "weapon": unit["weapon"],
        "sensor": unit["sensor"],
    }
    if unit["role"] == "logistics":
        capabilities["supply_range"] = profiles["logistics"]["supply_range"]
    return {
        "entity_id": entity_id,
        "name": name,
        "entity_type": unit_type,
        "faction": faction,
        "position": position,
        "state": {
            "hp": unit["hp"],
            "ammo": unit["ammo"],
            "morale": profiles["morale"]["start"],
            "suppression": 0,
            "readiness": unit["readiness"],
            "status": "active",
        },
        "capabilities": capabilities,
        "tags": [unit["role"].upper(), group],
    }
