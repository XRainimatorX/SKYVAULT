"""build_airspace_scenario = an airspace spec turned into a full SKYVAULT scenario.

Important:
A 2D grid of airspace. DEFENCE holds the assets, sensors, interceptors,
the command node that keeps the tracks, and SKYFOX's patrolling drones;
THREAT holds the incoming drones, waiting in reserve at their launch cells
until their wave's tick. The rules — HADES's rules of engagement included
— are copied into world_contract.rule_set.airspace.
"""

import copy
from typing import Any

from ...contracts import SCHEMA_VERSION, validate_scenario

DOMAIN = "airspace"
DEFENCE = "DEFENCE"
THREAT = "THREAT"
FAILURE_VARIABLES = (
    "sensor_failure",
    "enemy_reaction_speed",
    "equipment_overheat",
    "communication_failure",
)
ALTITUDES = ("low", "medium")
PRIORITIES = ("nearest_to_asset", "first_tracked")


def build_airspace_scenario(
    spec: dict[str, Any],
    rules: dict[str, Any],
    behavior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    The scenario spec describes, validated against the scenario contract.

    behavior: HADES's rules of engagement, overriding rules.hades key by key
    (engage_at, priority, salvo, hold_fire_below).

    Raises ValueError for anything outside the grid, a threat aimed at an
    unknown asset, an unknown altitude or priority, or ids that repeat.
    """
    width, height = (int(n) for n in spec["size"])
    if width <= 0 or height <= 0:
        raise ValueError("the airspace needs a positive size")

    def inside(entity_id: str, cell: Any) -> list[int]:
        x, y = int(cell[0]), int(cell[1])
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"{entity_id} at {[x, y]} is outside the airspace")
        return [x, y]

    assets = {a["id"] for a in spec["assets"]}
    hades = {**rules["hades"], **(behavior or {})}
    if hades["priority"] not in PRIORITIES:
        raise ValueError(f"unknown engagement priority {hades['priority']!r}")
    if not 0 <= float(hades["engage_at"]) <= 1:
        raise ValueError("engage_at is a share of the interceptor's range (0–1)")

    entities = [
        _entity(
            a["id"],
            "asset",
            DEFENCE,
            inside(a["id"], a["at"]),
            state={"hits": 0},
            capabilities={"value": float(a["value"])},
        )
        for a in spec["assets"]
    ]
    entities += [
        _entity(
            s["id"],
            "sensor",
            DEFENCE,
            inside(s["id"], s["at"]),
            state={"online": bool(s.get("online", True))},
            capabilities={
                "range": float(s["range"]),
                "detection": float(s["detection"]),
                "false_alarm": float(s["false_alarm"]),
                "low_altitude": float(s["low_altitude"]),
            },
        )
        for s in spec.get("sensors", [])
    ]
    entities += [
        _entity(
            i["id"],
            "interceptor",
            DEFENCE,
            inside(i["id"], i["at"]),
            state={"ammo": int(i["ammo"]), "ready_at": 0},
            capabilities={
                "range": float(i["range"]),
                "kill": float(i["kill"]),
                "reload": int(i["reload"]),
            },
        )
        for i in spec.get("interceptors", [])
    ]
    first_asset = entities[0]["position"] if entities else [0, 0]
    entities.append(
        _entity(
            "command",
            "command",
            DEFENCE,
            first_asset,
            state={"tracks": {}, "next_track": 1},
        )
    )
    for patrol in spec.get("patrols", []):
        route = [inside(patrol["id"], cell) for cell in patrol["route"]]
        if not route:
            raise ValueError(f"{patrol['id']} has no route")
        entities.append(
            _entity(
                patrol["id"],
                "drone",
                DEFENCE,
                route[0],
                state={"leg": 0, "altitude": rules["drone"]["altitude"]},
                capabilities={"speed": int(patrol["speed"]), "route": route},
            )
        )
    for wave in spec.get("threats", []):
        if wave["target"] not in assets:
            raise ValueError(f"wave {wave['wave']} aims at an unknown asset")
        if wave["altitude"] not in ALTITUDES:
            raise ValueError(f"unknown altitude {wave['altitude']!r}")
        for n, cell in enumerate(wave["from"], 1):
            threat_id = f"threat_w{wave['wave']}_{n}"
            entities.append(
                _entity(
                    threat_id,
                    "threat",
                    THREAT,
                    inside(threat_id, cell),
                    state={
                        "status": "reserve",
                        "wave": int(wave["wave"]),
                        "launch_tick": int(wave["tick"]),
                        "altitude": wave["altitude"],
                        "target": wave["target"],
                        "carry": 0.0,
                    },
                    capabilities={"speed": float(wave["speed"])},
                )
            )
    ids = [e["entity_id"] for e in entities]
    if len(set(ids)) != len(ids):
        raise ValueError("entity ids repeat")

    airspace_rules = copy.deepcopy(rules)
    airspace_rules.pop("description", None)
    airspace_rules["hades"] = hades
    airspace_rules["command"] = dict(spec["command"])
    airspace_rules["size"] = [width, height]
    scenario = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": spec["scenario_id"],
        "scenario_version": spec["scenario_version"],
        "scenario_type": "air_defence",
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
            "change_reason": "Built from the airspace domain pack spec.",
        },
        "world_contract": {
            "world_id": f"{spec['scenario_id']}_world",
            "world_scope": "low_altitude_airspace",
            "purpose": [spec.get("purpose", "")],
            "space_model": {
                "type": "grid",
                "width": width,
                "height": height,
                "distance_model": "chebyshev",
            },
            "time_model": {"type": "tick", "max_ticks": spec["max_ticks"]},
            "assumption_registry": {
                "movement_model": "straight_line_flight",
                "sensing": "probabilistic_detection_with_false_alarms",
                "command": "tracks_with_reaction_delay",
                "combat_resolution": "kill_probability_per_shot",
                "actor_policy": "hades_rules_of_engagement",
                "distance_model": "chebyshev",
            },
            "evaluation_targets": [
                "world_state_changed",
                "event_memory_created",
                "result_package_created",
            ],
            "entity_model": {
                "entity_types": sorted({e["entity_type"] for e in entities})
            },
            "environment_state": {},
            "resource_state": {},
            "rule_set": {"airspace": airspace_rules},
            "failure_variables": list(FAILURE_VARIABLES),
        },
        "entities": entities,
        "runtime": {
            "max_ticks": spec["max_ticks"],
            "random_seed": spec["random_seed"],
            "deterministic_mode": True,
        },
        "evaluation": {
            "primary_metrics": ["event_count", "winner_or_result"],
            "failure_thresholds": [],
            "perspective": DEFENCE,
            "success_outcomes": ["defended"],
        },
        "failure_exploration": {
            "objective": "find_weakness",
            "failure_variables": list(FAILURE_VARIABLES),
            "stress_levels": ["mild", "moderate", "severe", "collapse"],
            "run_policy": {
                "repeat_count": 5,
                "random_seed_policy": "controlled_random",
                "branch_comparison": True,
            },
            "survival_threshold": 0.5,
        },
    }
    return validate_scenario(scenario)


def _entity(
    entity_id: str,
    entity_type: str,
    faction: str,
    position: list[int],
    state: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "name": entity_id.replace("_", " ").title(),
        "entity_type": entity_type,
        "faction": faction,
        "position": position,
        "state": {"status": "active", **(state or {})},
        "capabilities": dict(capabilities or {}),
        "tags": [entity_type.upper()],
    }
