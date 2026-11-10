"""Transitions = every decision of a run as a training record.

Important:
Pure: built from a result package and its scenario; nothing that runs a
simulation is imported. The state is the engine's own snapshot of the actor
on its ACTION_SELECTED event; next_state is the same actor's snapshot at its
next decision (or at the end). The observation comes from the scenario's
domain when the pack can observe, otherwise it is the full world state,
labelled as such — a real observation layer is Phase 5.
"""

import copy
from typing import Any

from ..domains import load_domain
from .labels import run_labels
from .records import validate_transition


def scenario_metadata(package: dict[str, Any], scenario: dict[str, Any]) -> dict:
    """Who ran what: scenario, domain, profile, seed and the run's two hashes."""
    reproducibility = package["reproducibility"]
    return {
        "scenario_id": package["scenario_id"],
        "scenario_version": package["scenario_version"],
        "domain": scenario.get("domain"),
        "profile_id": package["evaluation_result"]["profile_id"],
        "perspective": package["evaluation_result"]["perspective"],
        "seed": reproducibility["random_seed"],
        "input_hash": reproducibility["input_hash"],
        "output_hash": reproducibility["output_hash"],
    }


def build_transitions(
    package: dict[str, Any], scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    """One validated transition per ACTION_SELECTED, in event order."""
    events = package["event_memory"]
    meta = scenario_metadata(package, scenario)
    run = run_labels(package, scenario)
    observe = (
        getattr(load_domain(scenario["domain"]), "observe", None)
        if scenario.get("domain")
        else None
    )
    final = package["final_world_state"]["entities"]
    causes = list(package["evaluation_result"]["failure_causes"])

    caused: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        action_id = event["source"]["action_id"]
        if action_id is not None and event["event_type"] != "ACTION_SELECTED":
            caused.setdefault(action_id, []).append(event)
    decisions = [e for e in events if e["event_type"] == "ACTION_SELECTED"]
    following: dict[str, dict[str, Any]] = {}
    for later in reversed(decisions):
        actor_id = later["source"]["actor_id"]
        if actor_id in following:
            following[later["event_id"]] = following[actor_id]
        following[actor_id] = later

    units = copy.deepcopy(package["initial_world_state"]["entities"])
    transitions = []
    for event in events:
        if event["event_type"] == "ACTION_SELECTED":
            transitions.append(
                validate_transition(
                    _transition(
                        event,
                        caused.get(event["source"]["action_id"], []),
                        following.get(event["event_id"]),
                        units,
                        final,
                        observe,
                        scenario,
                        meta,
                        run,
                        causes,
                        float(package["evaluation_result"]["overall_score"]),
                    )
                )
            )
        after = event["after_state"]
        if "entity_id" in after and "state" in after:
            units[after["entity_id"]] = after
    return transitions


def _transition(
    event: dict[str, Any],
    consequence: list[dict[str, Any]],
    next_decision: dict[str, Any] | None,
    units: dict[str, Any],
    final: dict[str, Any],
    observe: Any,
    scenario: dict[str, Any],
    meta: dict[str, Any],
    run: dict[str, Any],
    causes: list[str],
    score: float,
) -> dict[str, Any]:
    actor = event["before_state"]
    actor_id = event["source"]["actor_id"]
    next_state = (
        next_decision["before_state"] if next_decision is not None else final[actor_id]
    )
    destroyed = next_state["state"].get("status") == "destroyed"
    hp_now = float(actor["state"].get("hp", 0))
    hp_next = max(0.0, float(next_state["state"].get("hp", 0)))
    rejected = [e for e in consequence if e["event_type"] == "ACTION_REJECTED"]
    observation = (
        observe(actor, units, scenario)
        if observe is not None
        else {
            "observation_model": "full_state",
            "units": [
                {
                    "entity_id": unit["entity_id"],
                    "faction": unit.get("faction"),
                    "position": unit.get("position"),
                    "hp": unit["state"].get("hp"),
                    "status": unit["state"].get("status", "active"),
                }
                for unit in units.values()
            ],
        }
    )
    return {
        "scenario": meta,
        "tick": event["time"],
        "state": actor,
        "observation": observation,
        "action": {
            "action_id": event["source"]["action_id"],
            "action_type": event["data"]["action_type"],
            "actor_id": actor_id,
            "faction": actor.get("faction"),
            "target_entity_id": event["target_entity_id"],
            "target_location": event["data"].get("target_position"),
            "intent": event["data"].get("intent", ""),
            "system_id": event["source"]["system_id"],
        },
        "consequence": {
            "accepted": not rejected,
            "reason": rejected[0]["data"]["reason"] if rejected else None,
            "events": [
                {"event_type": e["event_type"], "data": e["data"]} for e in consequence
            ],
        },
        "reward": {
            "damage_dealt": float(
                sum(
                    e["data"].get("damage", 0)
                    for e in consequence
                    if e["event_type"] == "ATTACK"
                )
            ),
            "damage_taken": max(0.0, hp_now - hp_next),
            "target_destroyed": any(
                e["event_type"] == "ENTITY_DESTROYED" for e in consequence
            ),
            "own_destroyed": destroyed,
            "episode_score": score,
        },
        "next_state": next_state,
        "done": destroyed or next_decision is None,
        "event_sequence": [event["event_id"]] + [e["event_id"] for e in consequence],
        "failure_labels": {
            "run_failure_causes": causes,
            "destroyed_later": destroyed,
            "mission_failed": not run["mission_achieved"],
        },
        "labels": run["labels"],
        "violations": run["violations"],
        "success_type": run["success_type"],
    }
