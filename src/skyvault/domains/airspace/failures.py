"""What the core failure variables mean in the airspace (Formal Spec section 14).

Important:
HADES / AEROGRID are to miss, misjudge, react too slowly and face too many
targets; this is how the core variables say so here:

sensor_failure        sensors see less: detection × 0.9 / 0.75 / 0.6 / 0.4
enemy_reaction_speed  threats fly faster: speed × 1.25 / 1.5 / 2 / 3 (a fractional
                      speed carries over from tick to tick)
equipment_overheat    interceptors hit less: kill × 0.9 / 0.75 / 0.5 / 0.25

communication_failure keeps its core meaning (the defence's orders are lost).
"""

import copy
from typing import Any

from ...failure.variables import STRESS_LEVELS, FailureVariable

SENSING = (0.9, 0.75, 0.6, 0.4)
SPEED = (1.25, 1.5, 2.0, 3.0)
KILL = (0.9, 0.75, 0.5, 0.25)
REACTION = (1.0, 2.0, 3.0, 5.0)
SATURATION = (0.25, 0.5, 1.0, 2.0)
COLLISION = (0.25, 0.5, 0.75, 1.0)
BLOCKED = (0.25, 0.5, 0.75, 1.0)


def _of(scenario: dict[str, Any], entity_type: str) -> list[dict[str, Any]]:
    return [e for e in scenario["entities"] if e["entity_type"] == entity_type]


def _needs(entity_type: str, what: str) -> Any:
    def applies(scenario: dict[str, Any], perspective: str) -> tuple[bool, str]:
        if _of(scenario, entity_type):
            return True, ""
        return False, f"the airspace has no {what}"

    return applies


def _scale(entity_type: str, key: str, factors: tuple) -> Any:
    def apply(scenario: dict[str, Any], level: str, perspective: str) -> dict:
        factor = factors[STRESS_LEVELS.index(level)]
        for entity in _of(scenario, entity_type):
            value = float(entity["capabilities"][key]) * factor
            entity["capabilities"][key] = round(value, 4)
        return scenario

    return apply


def _command(key: str, change: Any) -> Any:
    def apply(scenario: dict[str, Any], level: str, perspective: str) -> dict:
        command = scenario["world_contract"]["rule_set"]["airspace"]["command"]
        command[key] = change(command[key], STRESS_LEVELS.index(level))
        return scenario

    return apply


def _needs_command(scenario: dict[str, Any], perspective: str) -> tuple[bool, str]:
    rules = scenario["world_contract"].get("rule_set", {}).get("airspace", {})
    if "command" in rules:
        return True, ""
    return False, "the airspace has no command rules"


def _saturate(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    """
    More threats than the defence was sized for: every threat gets copies
    (a quarter more at mild, three times as many at collapse), launched one
    tick after it from the same place towards the same target.
    """
    extra = SATURATION[STRESS_LEVELS.index(level)]
    threats = sorted(_of(scenario, "threat"), key=lambda e: e["entity_id"])
    copies = []
    count = round(len(threats) * extra)
    for n in range(count):
        original = threats[n % len(threats)]
        twin = copy.deepcopy(original)
        twin["entity_id"] = f"{original['entity_id']}_s{n // len(threats) + 1}"
        twin["name"] = f"{original.get('name') or original['entity_id']} (saturation)"
        twin["state"]["launch_tick"] = int(original["state"]["launch_tick"]) + 1
        copies.append(twin)
    scenario["entities"].extend(copies)
    return scenario


def _collide(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    """A share of the threats flies at the altitude of the drones."""
    drones = _of(scenario, "drone")
    altitude = drones[0]["state"]["altitude"]
    threats = sorted(_of(scenario, "threat"), key=lambda e: e["entity_id"])
    share = COLLISION[STRESS_LEVELS.index(level)]
    for threat in threats[: max(1, round(len(threats) * share))]:
        threat["state"]["altitude"] = altitude
    return scenario


def _needs_drones_and_threats(
    scenario: dict[str, Any], perspective: str
) -> tuple[bool, str]:
    if not _of(scenario, "drone"):
        return False, "the airspace has no drones"
    if not _of(scenario, "threat"):
        return False, "the airspace has no threats"
    return True, ""


def _block(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    """
    A share of every drone's route (its waypoints after the first) is closed
    to flight (rules.airspace.no_fly): the drone has to find its way round.
    """
    share = BLOCKED[STRESS_LEVELS.index(level)]
    rules = scenario["world_contract"]["rule_set"]["airspace"]
    closed = [list(c) for c in rules.get("no_fly") or []]
    for drone in sorted(_of(scenario, "drone"), key=lambda e: e["entity_id"]):
        waypoints = [list(c) for c in drone["capabilities"].get("route", [])[1:]]
        for waypoint in waypoints[: max(1, round(len(waypoints) * share))]:
            if waypoint not in closed:
                closed.append(waypoint)
    rules["no_fly"] = closed
    return scenario


def _needs_routes(scenario: dict[str, Any], perspective: str) -> tuple[bool, str]:
    if any(len(d["capabilities"].get("route", [])) > 1 for d in _of(scenario, "drone")):
        return True, ""
    return False, "no drone has a route to block"


def airspace_failure_variables() -> dict[str, FailureVariable]:
    """The variables the airspace reads in its own terms, by name."""
    return {
        "sensor_failure": FailureVariable(
            "sensor_failure",
            "Sensors degrade: every sensor detects less often",
            "sensing",
            SENSING,
            _needs("sensor", "sensors"),
            _scale("sensor", "detection", SENSING),
        ),
        "enemy_reaction_speed": FailureVariable(
            "enemy_reaction_speed",
            "Threats come faster: less time between launch and impact",
            "movement_model",
            SPEED,
            _needs("threat", "threats"),
            _scale("threat", "speed", SPEED),
        ),
        "equipment_overheat": FailureVariable(
            "equipment_overheat",
            "Interceptors overheat: every shot is less likely to kill",
            "combat_resolution",
            KILL,
            _needs("interceptor", "interceptors"),
            _scale("interceptor", "kill", KILL),
        ),
        "misidentification": FailureVariable(
            "misidentification",
            "Tracks are misidentified more often: command identifies less surely",
            "identification",
            SENSING,
            _needs_command,
            _command("identify", lambda v, i: round(float(v) * SENSING[i], 4)),
        ),
        "reaction_delay": FailureVariable(
            "reaction_delay",
            "The defence reacts later: more ticks before a track can be engaged",
            "command_reaction",
            REACTION,
            _needs_command,
            _command("reaction_delay", lambda v, i: int(v) + int(REACTION[i])),
        ),
        "target_saturation": FailureVariable(
            "target_saturation",
            "More threats than the defence was sized for",
            "threat_count",
            SATURATION,
            _needs("threat", "threats"),
            _saturate,
        ),
        "path_blocked": FailureVariable(
            "path_blocked",
            "The route is blocked: waypoints are closed to flight",
            "route_clearance",
            BLOCKED,
            _needs_routes,
            _block,
        ),
        "collision": FailureVariable(
            "collision",
            "Threats fly at the drones' altitude: drones and threats can collide",
            "airspace_deconfliction",
            COLLISION,
            _needs_drones_and_threats,
            _collide,
        ),
    }
