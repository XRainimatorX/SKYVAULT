"""Scenario compiler = Formal Spec section 4, step 2: "Compile Scenario".

Important:
SKYVAULT reads a scenario only in the section 3.3 grammar, and a world only
as a section 2 world contract. compile_scenario binds the two
(world_binding), lays the named environment and rule profiles over the world,
sets the starting resources, turns the participant slots into the run's
policies and scheduled orders, and writes the flat form the engine runs
(contracts.CompiledScenario). Nothing else builds that form from a file.

author_scenario goes the other way for SKYVAULT's own scenario builders: it
writes a compiled scenario back as a section 3.3 document bound to a world
contract, so builders can keep assembling worlds the way the engine sees
them while every file on disk is in the grammar.
"""

import copy
import json
from pathlib import Path
from typing import Any

from . import library
from .contracts import (
    ContractError,
    validate_compiled_scenario,
    validate_scenario,
    validate_world_contract,
)
from .contracts.scenario import Scenario
from .contracts.world import WorldContract, parse_duration

LEVELS = ("mild", "moderate", "severe", "collapse")
WORLDS = library.OWN["worlds"]
# section 14.3's own run policy, used when a scenario names none
DEFAULT_RUN_POLICY = {"repeat_count": 100, "random_seed_policy": "controlled_random"}


def load_world(world_contract_id: str, worlds_dir: Path = WORLDS) -> dict[str, Any]:
    """The world contract named world_contract_id, validated."""
    path = library.find(worlds_dir, f"{world_contract_id}.json")
    if path is None:
        raise ContractError(
            "scenario",
            [
                "world_binding.world_contract_id: "
                f"no world contract {world_contract_id!r}"
            ],
        )
    return validate_world_contract(json.loads(path.read_text(encoding="utf-8")))


def compile_scenario(
    document: dict[str, Any],
    world: dict[str, Any] | None = None,
    worlds_dir: Path = WORLDS,
) -> dict[str, Any]:
    """
    The compiled scenario a section 3.3 document describes.

    Important:
    world is the world contract to bind to; without it the one named by
    world_binding.world_contract_id is looked up in the world library.
    Raises ContractError when the document breaks the grammar, binds to a
    world that does not exist or is another, names a profile the world does
    not declare, sets a resource the world does not hold, asks for another
    time mode than the world's, or explores failures the world cannot
    suffer.
    """
    validate_scenario(document)
    # read with every default filled in: a document may leave optional fields out
    scenario = Scenario.model_validate(document).model_dump(mode="json", by_alias=True)
    binding = scenario["world_binding"]
    given = (
        world
        if world is not None
        else load_world(binding["world_contract_id"], worlds_dir)
    )
    validate_world_contract(given)
    world = WorldContract.model_validate(given).model_dump(mode="json", by_alias=True)
    problems: list[str] = []
    if world["world_id"] != binding["world_contract_id"]:
        problems.append(
            f"world_binding.world_contract_id: {binding['world_contract_id']!r} "
            f"but the world is {world['world_id']!r}"
        )

    compiled_world = _bind(world, binding, scenario["initial_conditions"], problems)
    settings = scenario["execution_settings"]
    if settings["time_mode"] != world["time_model"]["type"]:
        problems.append(
            f"execution_settings.time_mode: {settings['time_mode']!r} but the world "
            f"runs on {world['time_model']['type']!r}"
        )
    max_ticks = _steps(settings["duration_limit"], world["time_model"], problems)
    if (
        settings["random_seed_policy"] == "stochastic"
        and scenario["output"]["replay_required"]
    ):
        problems.append(
            "output.replay_required: a stochastic run draws no seed "
            "and cannot be replayed"
        )

    exploration = scenario["failure_exploration"]
    if exploration["enabled"]:
        undeclared = sorted(
            set(exploration["failure_variables"]) - set(world["failure_variables"])
        )
        if undeclared:
            problems.append(
                f"failure_exploration.failure_variables: {undeclared} are not "
                "among the world contract's failure_variables"
            )
    if problems:
        raise ContractError("scenario", problems)

    identity = scenario["identity"]
    policy, participants, orders = _slots(scenario["participants"])
    conditions = scenario["initial_conditions"]
    control = scenario.get("scenario_version_control")
    compiled: dict[str, Any] = {
        "schema_version": identity["schema_version"],
        "scenario_id": identity["scenario_id"],
        "scenario_version": identity["scenario_version"],
        "scenario_type": identity["scenario_type"],
        "domain": identity["domain"] or None,
        "purpose": identity["purpose"],
        "world_contract": compiled_world,
        "entities": copy.deepcopy(conditions["entities"]),
        "runtime": {
            "max_ticks": max_ticks,
            "random_seed": (
                settings["random_seed"] if settings["random_seed"] is not None else 0
            ),
            "deterministic_mode": settings["deterministic_mode"],
            "random_seed_policy": settings["random_seed_policy"],
            "repeat_count": settings["repeat_count"],
            "scheduled_actions": orders,
            "policy": policy,
            "participants": participants,
        },
        "evaluation": copy.deepcopy(scenario["evaluation"]),
        "assumption_registry": copy.deepcopy(scenario["assumption_registry"]),
        "data_provenance": copy.deepcopy(scenario["data_provenance"]),
        "participants": copy.deepcopy(scenario["participants"]),
        "allowed_actions": copy.deepcopy(scenario["allowed_actions"]),
        "failure_exploration": _exploration(exploration),
        "output": copy.deepcopy(scenario["output"]),
        "version_control": (
            {k: v for k, v in control.items() if k != "scenario_id"}
            if control
            else None
        ),
        "world_binding": dict(binding),
        "initial_conditions": {
            key: copy.deepcopy(conditions[key])
            for key in ("resources", "risks", "constraints", "uncertainty")
        },
    }
    return validate_compiled_scenario(compiled)


def author_scenario(
    compiled: dict[str, Any],
    world_contract_id: str | None = None,
    environment_profile: str = "baseline",
    rule_profile: str = "baseline",
) -> dict[str, Any]:
    """
    A compiled scenario written as a section 3.3 document.

    Important:
    The document binds to world_contract_id (the compiled world's own id by
    default) under the two profiles; the world contract itself is written
    separately (author_world). Slots: the default policy becomes the ai agent
    slot "default", each participant an ai agent slot of its own, and each
    ordering system a system slot holding its orders.
    """
    runtime = compiled["runtime"]
    world = compiled["world_contract"]
    ai_slots: list[dict[str, Any]] = []
    if runtime.get("policy"):
        ai_slots.append(
            {"slot_id": "default", "policy": copy.deepcopy(runtime["policy"])}
        )
    for participant in runtime.get("participants", []):
        ai_slots.append(
            {
                "slot_id": participant["participant_id"],
                "policy": copy.deepcopy(participant["policy"]),
                "controls": copy.deepcopy(participant["controls"]),
            }
        )
    system_slots: list[dict[str, Any]] = []
    by_id = {slot["slot_id"]: slot for slot in ai_slots}
    for order in runtime.get("scheduled_actions", []):
        order = copy.deepcopy(order)
        system = order.pop("system_id")
        slot = by_id.get(system)
        if slot is None:
            slot = {"slot_id": system, "orders": []}
            system_slots.append(slot)
            by_id[system] = slot
        slot.setdefault("orders", []).append(order)

    seed = runtime.get("random_seed")
    policy = runtime.get("random_seed_policy") or (
        "fixed" if isinstance(seed, int) else "stochastic"
    )
    evaluation = copy.deepcopy(compiled["evaluation"])
    for key in ("secondary_metrics", "anti_gaming_metrics", "comparison_targets"):
        if evaluation.get(key) is None:
            evaluation[key] = []
    control = compiled.get("version_control")
    explored = compiled.get("failure_exploration")
    document: dict[str, Any] = {
        "identity": {
            "scenario_id": compiled["scenario_id"],
            "scenario_type": compiled.get("scenario_type") or "",
            "domain": compiled.get("domain") or "",
            "purpose": compiled.get("purpose") or "",
            "scenario_version": compiled["scenario_version"],
            "schema_version": "1.0",
        },
        "world_binding": {
            "world_contract_id": world_contract_id or world["world_id"],
            "environment_profile": environment_profile,
            "rule_profile": rule_profile,
        },
        "initial_conditions": {
            "entities": copy.deepcopy(compiled["entities"]),
            "resources": {},
            "risks": {},
            "constraints": {},
            "uncertainty": {},
            **copy.deepcopy(
                {k: v for k, v in (compiled.get("initial_conditions") or {}).items()}
            ),
        },
        "assumption_registry": copy.deepcopy(compiled.get("assumption_registry") or {}),
        "data_provenance": copy.deepcopy(compiled.get("data_provenance") or {}),
        "participants": {
            "human_decision_slots": [],
            "ai_agent_slots": ai_slots,
            "system_slots": system_slots,
            "equipment_profiles": [],
        },
        "allowed_actions": copy.deepcopy(
            compiled.get("allowed_actions")
            or {"action_types": [], "actor_permissions": {}}
        ),
        "execution_settings": {
            "time_mode": world["time_model"]["type"],
            "duration_limit": runtime["max_ticks"],
            "repeat_count": runtime.get("repeat_count") or 1,
            "random_seed_policy": policy,
            "deterministic_mode": bool(runtime.get("deterministic_mode")),
            "random_seed": seed if policy != "stochastic" else None,
        },
        "failure_exploration": _author_exploration(explored),
        "evaluation": evaluation,
        "output": copy.deepcopy(
            compiled.get("output")
            or {
                "required_logs": [],
                "required_reports": [],
                "replay_required": True,
                "failure_map_required": explored is not None,
            }
        ),
    }
    if control:
        document["scenario_version_control"] = {
            "scenario_id": compiled["scenario_id"],
            **copy.deepcopy(control),
        }
    return validate_scenario(document)


def author_world(
    world: dict[str, Any],
    actor_slots: list[str] | None = None,
    event_memory: dict[str, Any] | None = None,
    data_provenance: dict[str, Any] | None = None,
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    A world contract from a compiled scenario's world, with the section 2.2
    elements a compiled world may lack filled in.
    """
    document = copy.deepcopy(world)
    document.setdefault("actor_slots", list(actor_slots or []))
    document.setdefault(
        "event_memory",
        event_memory or {"format": "event_sourcing", "snapshot_every": 5},
    )
    document.setdefault(
        "data_provenance",
        data_provenance or {"source_type": "manual_input", "source_quality": "medium"},
    )
    if profiles:
        document["profiles"] = copy.deepcopy(profiles)
    return validate_world_contract(document)


def overlay(base: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    """base with change laid over it: nested dicts merge, anything else replaces."""
    merged = copy.deepcopy(base)
    for key, value in change.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = overlay(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


# ── helpers ──────────────────────────────────────────────────────────────────


def _bind(
    world: dict[str, Any],
    binding: dict[str, Any],
    conditions: dict[str, Any],
    problems: list[str],
) -> dict[str, Any]:
    compiled = copy.deepcopy(world)
    profiles = compiled.pop("profiles", None) or {}
    for field, kind, target in (
        ("environment_profile", "environment", "environment_state"),
        ("rule_profile", "rules", "rule_set"),
    ):
        name = binding[field]
        if name == "baseline":
            continue
        declared = profiles.get(kind, {})
        if name not in declared:
            problems.append(
                f"world_binding.{field}: {name!r} is not one of the world's "
                f"{kind} profiles {sorted(declared)}"
            )
            continue
        compiled[target] = overlay(compiled[target], declared[name])

    for resource, amount in conditions["resources"].items():
        if resource not in compiled["resource_state"]:
            problems.append(
                f"initial_conditions.resources: the world holds no {resource!r}"
            )
        else:
            compiled["resource_state"][resource] = amount
    compiled["profiles"] = None
    return compiled


def _steps(limit: int | str, time_model: dict[str, Any], problems: list[str]) -> int:
    """How many clock steps duration_limit allows."""
    try:
        amount, unit = parse_duration(limit)
    except ValueError as error:
        problems.append(f"execution_settings.duration_limit: {error}")
        return 1
    if unit in (None, "ticks"):
        steps = amount
    else:
        length = time_model.get("phase_length")
        if length is None:
            problems.append(
                f"execution_settings.duration_limit: {limit!r} needs a phased world"
            )
            return 1
        phase, phase_unit = parse_duration(length)
        phase_unit = phase_unit or time_model.get("time_unit")
        scale = {"minutes": 1, "hours": 60, "days": 1440}
        if phase_unit not in scale:
            problems.append(
                "execution_settings.duration_limit: the world's phases have no unit"
            )
            return 1
        steps = (amount * scale[unit]) // (phase * scale[phase_unit])
    if steps <= 0:
        problems.append(
            "execution_settings.duration_limit must allow at least one step"
        )
        return 1
    return steps


def _slots(
    participants: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """(default policy, participants, scheduled orders) the slots describe."""
    policy = None
    controlled: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    for group in ("human_decision_slots", "ai_agent_slots", "system_slots"):
        for slot in participants[group]:
            if slot.get("policy") is not None:
                if slot.get("controls") is None:
                    policy = copy.deepcopy(slot["policy"])
                else:
                    controlled.append(
                        {
                            "participant_id": slot["slot_id"],
                            "policy": copy.deepcopy(slot["policy"]),
                            "controls": copy.deepcopy(slot["controls"]),
                        }
                    )
            for order in slot.get("orders", []):
                order = copy.deepcopy(order)
                order["system_id"] = order.get("system_id") or slot["slot_id"]
                orders.append(order)
    return policy, controlled, orders


def _exploration(exploration: dict[str, Any]) -> dict[str, Any] | None:
    if not exploration["enabled"]:
        return None
    levels = exploration["stress_levels"]
    chosen = [level for level in LEVELS if levels.get(level) is not None]
    run_policy = dict(exploration.get("run_policy") or DEFAULT_RUN_POLICY)
    run_policy["branch_comparison"] = exploration["branch_comparison"]
    return {
        "objective": exploration["objective"],
        "failure_variables": list(exploration["failure_variables"]),
        "stress_levels": chosen,
        "run_policy": run_policy,
        "alternatives": list(exploration["alternatives"]),
        "survival_threshold": exploration["survival_threshold"],
        "magnitudes": {level: dict(levels[level]) for level in chosen if levels[level]},
    }


def _author_exploration(explored: dict[str, Any] | None) -> dict[str, Any]:
    if explored is None:
        return {"enabled": False}
    magnitudes = explored.get("magnitudes") or {}
    run_policy = dict(explored["run_policy"])
    branch = bool(run_policy.pop("branch_comparison", False))
    return {
        "enabled": True,
        "failure_variables": list(explored["failure_variables"]),
        "stress_levels": {
            level: dict(magnitudes.get(level, {}))
            for level in explored["stress_levels"]
        },
        "branch_comparison": branch,
        "objective": explored.get("objective", "find_weakness"),
        "run_policy": run_policy,
        "alternatives": list(explored.get("alternatives", [])),
        "survival_threshold": explored.get("survival_threshold", 0.5),
    }


def publish(
    versions: dict[str, dict[str, Any]],
    actor_slots: list[str] | None = None,
    data_provenance: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    The files a set of compiled scenarios is kept as: one world contract per
    world ({"worlds/<world_id>.json": world}) and one section 3.3 document per
    version ({"scenarios/<scenario_id>/<version>.json": document}).

    Important:
    Every version of a world must agree on it except for its rule_set and
    environment_state (which become named profiles, named after the label a
    child version carries: v0.1+overwatch -> "overwatch") and its starting
    resources (which become initial_conditions.resources). The first
    version listed is the world as written. A version that changes anything
    else in the world raises ValueError: that is a different world.
    """
    files: dict[str, dict[str, Any]] = {}
    worlds: dict[str, dict[str, Any]] = {}
    profiles: dict[str, dict[str, dict[str, Any]]] = {}
    bindings: dict[str, tuple[str, str, dict[str, float]]] = {}
    for name, compiled in versions.items():
        world = compiled["world_contract"]
        world_id = world["world_id"]
        base = worlds.setdefault(world_id, copy.deepcopy(world))
        named = profiles.setdefault(world_id, {"environment": {}, "rules": {}})
        label = compiled["scenario_version"].rsplit("+", 1)[-1]
        chosen: dict[str, str] = {}
        for kind, field in (
            ("environment", "environment_state"),
            ("rules", "rule_set"),
        ):
            change = _difference(base[field], world[field])
            if not change:
                chosen[kind] = "baseline"
                continue
            if named[kind].get(label, change) != change:
                raise ValueError(
                    f"{name}: profile {label!r} means two different {field}s"
                )
            named[kind][label] = change
            chosen[kind] = label
        resources = {
            key: amount
            for key, amount in world["resource_state"].items()
            if base["resource_state"].get(key) != amount
        }
        if set(world["resource_state"]) != set(base["resource_state"]):
            raise ValueError(f"{name}: a version cannot add or remove world resources")
        rest = ("environment_state", "rule_set", "resource_state", "profiles")
        for key in sorted(set(world) | set(base)):
            if key not in rest and world.get(key) != base.get(key):
                raise ValueError(
                    f"{name}: world_contract.{key} differs between versions"
                )
        bindings[name] = (chosen["environment"], chosen["rules"], resources)

    for world_id, world in worlds.items():
        declared = {
            kind: dict(sorted(v.items())) for kind, v in profiles[world_id].items() if v
        }
        files[f"worlds/{world_id}.json"] = author_world(
            {k: v for k, v in world.items() if k != "profiles"},
            actor_slots=actor_slots,
            data_provenance=data_provenance,
            profiles=declared or None,
        )
    for name, compiled in versions.items():
        environment, rules, resources = bindings[name]
        compiled = copy.deepcopy(compiled)
        conditions = compiled.setdefault("initial_conditions", None) or {}
        conditions = {**conditions, "resources": resources}
        compiled["initial_conditions"] = conditions
        document = author_scenario(
            compiled, environment_profile=environment, rule_profile=rules
        )
        files[f"scenarios/{name}"] = document
    return files


def _difference(base: dict[str, Any], changed: dict[str, Any]) -> dict[str, Any]:
    """The smallest overlay that turns base into changed (nested keys only)."""
    if set(base) - set(changed):
        raise ValueError("a profile can change values but not remove keys")
    change: dict[str, Any] = {}
    for key, value in changed.items():
        if key not in base:
            change[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(base[key], dict):
            inner = _difference(base[key], value)
            if inner:
                change[key] = inner
        elif value != base[key]:
            change[key] = copy.deepcopy(value)
    return change
