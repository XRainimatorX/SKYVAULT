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

from ...contracts import SCHEMA_VERSION, validate_compiled_scenario
from .disasters import DISASTERS
from .model import order_state

DOMAIN = "city"
FACTION = "CITY"
# Spec section 14's city takeover failures, in the city's own terms (failures.py)
FAILURE_VARIABLES = (
    "supply_delay",
    "civilian_pressure",
    "resource_shortage",
    "communication_failure",
    "public_order_collapse",
)


def build_city_scenario(spec: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """
    The scenario spec describes, validated against the scenario contract.

    Raises ValueError for a road, facility or actor at a place the city
    does not have, a substation serving or backed up by something unknown,
    a district served by two substations, or an incident or disaster naming
    nothing.

    Important:
    Phase 22: a spec may describe its world (world: world_id, world_scope,
    purpose, space_type, units, time_model), its environment_state, an
    information environment (information), disasters, entity_model flags
    (added to the entity types), its own
    failure_variables, actor_slots, evaluation_targets, assumptions (added
    to the model's own), data_provenance, and the scenario's own
    assumption_registry and scenario_provenance (section 11); without them
    the city is built as before.
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
    roads = {frozenset((a, b)) for a, b, _ in spec["roads"]}
    for disaster in spec.get("disasters", []):
        if disaster["type"] not in DISASTERS:
            raise ValueError(f"unknown disaster {disaster['type']!r}")
        if disaster["type"] == "road_closure":
            if frozenset(disaster["road"]) not in roads:
                raise ValueError(f"no road {disaster['road']} to close")
        elif disaster["district"] not in known:
            raise ValueError(f"disaster in no district: {disaster['district']!r}")

    city_rules = copy.deepcopy(rules)
    city_rules.pop("description", None)
    city_rules["incidents"] = copy.deepcopy(spec.get("incidents", []))
    if spec.get("disasters"):
        city_rules["disasters"] = copy.deepcopy(spec["disasters"])
    if spec.get("information") is not None:
        city_rules["information"] = copy.deepcopy(spec["information"])
    world = spec.get("world", {})
    space: dict[str, Any] = {
        "type": world.get("space_type", "network"),
        "nodes": nodes,
        "edges": [[a, b, float(ticks)] for a, b, ticks in spec["roads"]],
    }
    if world.get("units"):
        space["units"] = list(world["units"])
    time_model = copy.deepcopy(
        world.get("time_model") or {"type": "tick", "max_ticks": spec["max_ticks"]}
    )
    variables = list(spec.get("failure_variables") or FAILURE_VARIABLES)
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
            "world_id": world.get("world_id", f"{spec['scenario_id']}_world"),
            "world_scope": world.get("world_scope", "city_governance"),
            "purpose": list(world.get("purpose") or [spec.get("purpose", "")]),
            "space_model": space,
            "time_model": time_model,
            "assumption_registry": {
                "movement_model": "road_network_travel_ticks",
                "public_order": "banded_state_machine",
                "power": "substation_backup_with_overload_trip",
                "supply": "convoys_on_shortest_road",
                "actor_policy": "city_administration_baseline",
                "distance_model": "travel_ticks",
                **copy.deepcopy(spec.get("assumptions", {})),
            },
            "evaluation_targets": list(
                spec.get("evaluation_targets")
                or [
                    "world_state_changed",
                    "event_memory_created",
                    "result_package_created",
                ]
            ),
            "entity_model": {
                **copy.deepcopy(spec.get("entity_model", {})),
                "entity_types": sorted({e["entity_type"] for e in entities}),
            },
            "environment_state": copy.deepcopy(spec.get("environment_state", {})),
            "resource_state": {},
            "rule_set": {"city": city_rules},
            "failure_variables": variables,
            "actor_slots": list(
                spec.get("actor_slots")
                or ["NEXUS", "STARTX", "TAC_ANGEL", "EIDEN_01", "CYBERHOUND"]
            ),
            "event_memory": {"format": "event_sourcing", "snapshot_every": 5},
            "data_provenance": {
                "source_type": "city_domain_pack",
                "source_quality": "medium",
                **copy.deepcopy(spec.get("data_provenance", {})),
                "version": spec["scenario_version"],
            },
        },
        "failure_exploration": {
            "objective": "find_weakness",
            "failure_variables": variables,
            "stress_levels": ["mild", "moderate", "severe", "collapse"],
            "run_policy": {
                "repeat_count": 5,
                "random_seed_policy": "controlled_random",
                "branch_comparison": True,
            },
            "survival_threshold": 0.5,
        },
        **(
            {
                "assumption_registry": {
                    "scenario_id": spec["scenario_id"],
                    "assumptions": copy.deepcopy(spec["assumption_registry"]),
                }
            }
            if spec.get("assumption_registry")
            else {}
        ),
        **(
            {
                "data_provenance": {
                    "scenario_id": spec["scenario_id"],
                    **copy.deepcopy(spec["scenario_provenance"]),
                }
            }
            if spec.get("scenario_provenance")
            else {}
        ),
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
    return validate_compiled_scenario(scenario)


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
