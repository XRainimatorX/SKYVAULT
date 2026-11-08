"""build_city_scenario = a city spec turned into a full SKYVAULT scenario.

Important:
The world is a road network: districts are its nodes, roads its links
weighted by travel ticks. Every district, facility and actor is an entity
of the one faction CITY. The rules are copied into
world_contract.rule_set.city, so the scenario runs and reproduces without
the rules file and compare_scenarios sees every difference.
"""

import copy
from typing import Any

from ...contracts import SCHEMA_VERSION, validate_scenario
from .model import order_state

DOMAIN = "city"
FACTION = "CITY"


def build_city_scenario(spec: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """
    The scenario spec describes, validated against the scenario contract.

    Raises ValueError for a road, facility or actor at a place the city
    does not have, a substation serving or backed up by something unknown,
    a district served by two substations, or an incident naming nothing.
    """
    nodes = [d["id"] for d in spec["districts"]]
    known = set(nodes)
    if len(known) != len(nodes):
        raise ValueError("district ids repeat")
    for a, b, ticks in spec["roads"]:
        if a not in known or b not in known:
            raise ValueError(f"road {a}–{b} leaves the city")
        if float(ticks) <= 0:
            raise ValueError(f"road {a}–{b} must take some time ({ticks} ticks)")

    entities = [_district(d, rules) for d in spec["districts"]]
    entities += _power(spec["power"], known)
    entities += [
        _entity(
            depot["id"],
            "depot",
            depot["at"],
            known,
            state={"food": float(depot["food"])},
        )
        for depot in spec.get("depots", [])
    ]
    entities += _forces(spec.get("forces", {}), known)

    ids = {e["entity_id"] for e in entities}
    if len(ids) != len(entities):
        raise ValueError("entity ids repeat")
    for incident in spec.get("incidents", []):
        if incident["type"] != "substation_failure":
            raise ValueError(f"unknown incident {incident['type']!r}")
        if incident["target"] not in ids:
            raise ValueError(f"incident names nothing: {incident['target']!r}")

    city_rules = copy.deepcopy(rules)
    city_rules.pop("description", None)
    city_rules["incidents"] = copy.deepcopy(spec.get("incidents", []))
    scenario = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": spec["scenario_id"],
        "scenario_version": spec["scenario_version"],
        "scenario_type": "governance",
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
            "change_reason": "Built from the city domain pack spec.",
        },
        "world_contract": {
            "world_id": f"{spec['scenario_id']}_world",
            "world_scope": "city_governance",
            "purpose": [spec.get("purpose", "")],
            "space_model": {
                "type": "network",
                "nodes": nodes,
                "edges": [[a, b, float(ticks)] for a, b, ticks in spec["roads"]],
            },
            "time_model": {"type": "tick", "max_ticks": spec["max_ticks"]},
            "assumption_registry": {
                "movement_model": "road_network_travel_ticks",
                "public_order": "banded_state_machine",
                "power": "substation_backup_with_overload_trip",
                "supply": "convoys_on_shortest_road",
                "actor_policy": "city_administration_baseline",
                "distance_model": "travel_ticks",
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
            "rule_set": {"city": city_rules},
            "failure_variables": [],
        },
        "entities": entities,
        "runtime": {
            "max_ticks": spec["max_ticks"],
            "random_seed": spec["random_seed"],
            "deterministic_mode": True,
        },
        "evaluation": {
            "primary_metrics": ["event_count", "winner_or_result"],
            "failure_thresholds": ["governance_collapsed"],
            "success_outcomes": ["order_restored", "order_held"],
            "perspective": FACTION,
        },
    }
    return validate_scenario(scenario)


def _entity(
    entity_id: str,
    entity_type: str,
    at: str,
    known: set[str],
    state: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    if at not in known:
        raise ValueError(f"{entity_id} stands at {at!r}, which the city does not have")
    return {
        "entity_id": entity_id,
        "name": name or entity_id.replace("_", " ").title(),
        "entity_type": entity_type,
        "faction": FACTION,
        "position": at,
        "state": {"status": "active", **(state or {})},
        "capabilities": dict(capabilities or {}),
        "tags": [entity_type.upper()],
    }


def _district(district: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    order = float(district["public_order"])
    if not 0 <= order <= 100:
        raise ValueError(f"{district['id']}: public order {order} is outside 0–100")
    if float(district["population"]) < 0:
        raise ValueError(f"{district['id']}: negative population")
    return _entity(
        district["id"],
        "district",
        district["id"],
        {district["id"]},
        name=district.get("name"),
        state={
            "population": float(district["population"]),
            "public_order": order,
            "order_state": order_state(order, rules),
            "food": float(district["food"]),
            "medical": float(district["medical"]),
            "industry": float(district["industry"]),
            "administration": float(district["administration"]),
            "power": 1,
            "communication": 1.0,
            "substation": None,
        },
    )


def _power(power: dict[str, Any], known: set[str]) -> list[dict[str, Any]]:
    entities = [
        _entity(
            plant["id"],
            "power_plant",
            plant["at"],
            known,
            state={"online": True},
            capabilities={"output": float(plant["output"])},
        )
        for plant in power.get("plants", [])
    ]
    substation_ids = {sub["id"] for sub in power.get("substations", [])}
    served: dict[str, str] = {}
    for sub in power.get("substations", []):
        for district in sub["serves"]:
            if district not in known:
                raise ValueError(f"{sub['id']} serves an unknown district {district!r}")
            if district in served:
                raise ValueError(
                    f"{district} is served by both {served[district]} and {sub['id']}"
                )
            served[district] = sub["id"]
        for backup in sub.get("backup", []):
            if backup not in substation_ids or backup == sub["id"]:
                raise ValueError(f"{sub['id']}: unknown backup {backup!r}")
        entities.append(
            _entity(
                sub["id"],
                "substation",
                sub["at"],
                known,
                state={
                    "online": True,
                    "load": 0.0,
                    "overloaded": False,
                    "outage": None,
                    "repair_needed": 0,
                    "repair_done": 0,
                },
                capabilities={
                    "capacity": float(sub["capacity"]),
                    "serves": list(sub["serves"]),
                    "backup": list(sub.get("backup", [])),
                },
            )
        )
    return entities


def _forces(forces: dict[str, Any], known: set[str]) -> list[dict[str, Any]]:
    entities = []
    office = forces.get("administration")
    if office:
        entities.append(_entity(office["id"], "city_office", office["at"], known))
    for police in forces.get("police", []):
        entities.append(
            _entity(
                police["id"],
                "police",
                police["at"],
                known,
                state={"destination": None, "arrives_at": None},
            )
        )
    for convoy in forces.get("convoys", []):
        entities.append(
            _entity(
                convoy["id"],
                "convoy",
                convoy["at"],
                known,
                state={
                    "home": convoy["at"],
                    "cargo": 0.0,
                    "destination": None,
                    "arrives_at": None,
                    "dispatched_at": None,
                    "leg": "idle",
                },
                capabilities={"capacity": float(convoy["capacity"])},
            )
        )
    for crew in forces.get("repair_crews", []):
        entities.append(
            _entity(
                crew["id"],
                "repair_crew",
                crew["at"],
                known,
                state={"destination": None, "arrives_at": None},
            )
        )
    return entities
