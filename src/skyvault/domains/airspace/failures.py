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

from typing import Any

from ...failure.variables import STRESS_LEVELS, FailureVariable

SENSING = (0.9, 0.75, 0.6, 0.4)
SPEED = (1.25, 1.5, 2.0, 3.0)
KILL = (0.9, 0.75, 0.5, 0.25)


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
    }
