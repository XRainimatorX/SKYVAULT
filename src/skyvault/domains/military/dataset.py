"""State-action-outcome dataset = every decision of a run, as a training record.

Important:
Pure: built from a result package and the scenario that produced it, with
nothing that runs a simulation imported. One record per ACTION_SELECTED,
in event order. The state is what the deciding unit had at that moment —
itself, the ground under it, the enemies its sensor saw and its friends —
rebuilt from the events' snapshots, so it is exactly what the run recorded.
Episodes are named by input and output hash rather than run id, so the
same runs always export the same bytes.
"""

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .mission import mission_outcome


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(_Model):
    entity_id: str
    offset: list[int] = Field(min_length=2, max_length=2)
    distance: float = Field(ge=0)
    hp: float
    terrain: str | None = None


class UnitState(_Model):
    position: list[int] = Field(min_length=2, max_length=2)
    hp: float
    ammo: float
    morale: float
    suppression: float
    terrain: str
    cover: float = Field(ge=0, le=1)
    seen_enemies: list[Contact]
    allies: list[Contact]


class Episode(_Model):
    """The run a decision belongs to, identified by content, not by clock."""

    input_hash: str = Field(min_length=64, max_length=64)
    output_hash: str = Field(min_length=64, max_length=64)
    scenario_id: str
    scenario_version: str
    seed: int | None
    result: str
    mission_achieved: bool | None


class Actor(_Model):
    entity_id: str
    unit_type: str
    faction: str


class Decision(_Model):
    action_id: str
    action_type: str
    target_entity_id: str | None
    target_location: list[int] | None
    intent: str
    system_id: str | None


class Outcome(_Model):
    accepted: bool
    reason: str | None
    events: list[str]
    damage_dealt: float = Field(ge=0)
    target_destroyed: bool
    hit: bool | None


class TrainingRecord(_Model):
    """One decision: what the unit had, what it chose, what came of it."""

    record_type: Literal["state_action_outcome"] = "state_action_outcome"
    episode: Episode
    tick: int = Field(ge=0)
    actor: Actor
    state: UnitState
    action: Decision
    outcome: Outcome


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    """The record as the model normalises it. Raises ValueError."""
    try:
        return TrainingRecord.model_validate(record).model_dump(mode="json")
    except ValidationError as error:
        raise ValueError(str(error)) from None


def build_dataset(package: dict[str, Any], scenario: dict[str, Any]) -> list[dict]:
    """Every decision of the run, in event order, each a TrainingRecord."""
    terrain = scenario["world_contract"]["environment_state"]["terrain"]
    table = scenario["world_contract"]["rule_set"]["military"]["terrain"]
    missions = mission_outcome(package, scenario)
    reproducibility = package["reproducibility"]
    result = package["evaluation_result"]["winner_or_result"]

    units = copy.deepcopy(package["initial_world_state"]["entities"])
    events = package["event_memory"]
    by_action: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        action_id = event["source"]["action_id"]
        if action_id is not None and event["event_type"] != "ACTION_SELECTED":
            by_action.setdefault(action_id, []).append(event)

    records = []
    for event in events:
        if event["event_type"] == "ACTION_SELECTED":
            actor = units[event["source"]["actor_id"]]
            records.append(
                validate_record(
                    {
                        "episode": {
                            "input_hash": reproducibility["input_hash"],
                            "output_hash": reproducibility["output_hash"],
                            "scenario_id": package["scenario_id"],
                            "scenario_version": package["scenario_version"],
                            "seed": reproducibility["random_seed"],
                            "result": result,
                            "mission_achieved": missions.get(actor["faction"], {}).get(
                                "achieved"
                            ),
                        },
                        "tick": event["time"],
                        "actor": {
                            "entity_id": actor["entity_id"],
                            "unit_type": actor["entity_type"],
                            "faction": actor["faction"],
                        },
                        "state": _state(actor, units, terrain, table, scenario),
                        "action": {
                            "action_id": event["source"]["action_id"],
                            "action_type": event["data"]["action_type"],
                            "target_entity_id": event["target_entity_id"],
                            "target_location": event["data"].get("target_position"),
                            "intent": event["data"].get("intent", ""),
                            "system_id": event["source"]["system_id"],
                        },
                        "outcome": _outcome(
                            by_action.get(event["source"]["action_id"], [])
                        ),
                    }
                )
            )
        # Keep every unit as the latest entity snapshot an event left
        after = event["after_state"]
        if "entity_id" in after and "state" in after:
            units[after["entity_id"]] = after
    return records


def _cell(terrain: dict[str, Any], table: dict[str, Any], position: list[int]):
    name = terrain["legend"][terrain["rows"][position[1]][position[0]]]
    return name, table[name]


def sensor_contacts(
    actor: dict[str, Any], units: dict[str, Any], scenario: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    (enemies actor's sensor sees, friends) from entity snapshots.

    The pack's sensing rule: an enemy is seen within sensor range × (1 −
    concealment of its cell). Both lists keep the order of units.
    """
    terrain = scenario["world_contract"]["environment_state"]["terrain"]
    table = scenario["world_contract"]["rule_set"]["military"]["terrain"]
    x, y = actor["position"]
    sensor = float(actor["capabilities"].get("sensor_range", 5))
    seen, allies = [], []
    for other in units.values():
        if (
            other["entity_id"] == actor["entity_id"]
            or other["state"].get("status", "active") != "active"
            or other["position"] is None
        ):
            continue
        ox, oy = other["position"]
        distance = float(max(abs(ox - x), abs(oy - y)))
        other_name, other_ground = _cell(terrain, table, other["position"])
        contact = {
            "entity_id": other["entity_id"],
            "offset": [ox - x, oy - y],
            "distance": distance,
            "hp": float(other["state"].get("hp", 0)),
            "terrain": other_name,
        }
        if other["faction"] == actor["faction"]:
            allies.append(contact)
        elif distance <= sensor * (1 - float(other_ground["concealment"])):
            seen.append(contact)
    return seen, allies


def _state(
    actor: dict[str, Any],
    units: dict[str, Any],
    terrain: dict[str, Any],
    table: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    name, ground = _cell(terrain, table, actor["position"])
    seen, allies = sensor_contacts(actor, units, scenario)
    state = actor["state"]
    return {
        "position": list(actor["position"]),
        "hp": float(state.get("hp", 0)),
        "ammo": float(state.get("ammo", 0)),
        "morale": float(state.get("morale", 0)),
        "suppression": float(state.get("suppression", 0)),
        "terrain": name,
        "cover": float(ground["cover"]),
        "seen_enemies": seen,
        "allies": allies,
    }


def _outcome(events: list[dict[str, Any]]) -> dict[str, Any]:
    rejected = [e for e in events if e["event_type"] == "ACTION_REJECTED"]
    shots = [e for e in events if e["event_type"] in ("ATTACK", "MISS")]
    return {
        "accepted": not rejected,
        "reason": rejected[0]["data"]["reason"] if rejected else None,
        "events": [e["event_type"] for e in events],
        "damage_dealt": float(
            sum(
                e["data"].get("damage", 0)
                for e in events
                if e["event_type"] == "ATTACK"
            )
        ),
        "target_destroyed": any(e["event_type"] == "ENTITY_DESTROYED" for e in events),
        "hit": shots[0]["event_type"] == "ATTACK" if shots else None,
    }
