"""Failure variables = the ways a plan is deliberately made worse.

Important:
Every variable is a scenario transformation. It never touches a running world;
it writes a new scenario version that the ordinary engine then runs, so a
stressed run is as reproducible and comparable as any other.

A variable only changes what the current models have: capability values, hp,
world resources, or whether an order gets through. A variable whose target
does not exist in the scenario (resources in a world without any) says so
instead of pretending to stress something.
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..reproducibility import child_version

STRESS_LEVELS = ("mild", "moderate", "severe", "collapse")

Scenario = dict[str, Any]
Applies = Callable[[Scenario, str], tuple[bool, str]]
Apply = Callable[[Scenario, str, str], Scenario]


@dataclass(frozen=True)
class FailureVariable:
    """
    One way to stress a plan.

    assumption names the world_contract.assumption_registry entry the variable
    attacks, so a failure map can say which assumption the plan died on.
    """

    name: str
    description: str
    assumption: str
    magnitudes: tuple[float, float, float, float]
    applies: Applies
    apply: Apply

    def magnitude(self, level: str) -> float:
        return self.magnitudes[STRESS_LEVELS.index(level)]


def _own(scenario: Scenario, perspective: str) -> list[dict[str, Any]]:
    return [e for e in scenario["entities"] if e.get("faction") == perspective]


def _enemies(scenario: Scenario, perspective: str) -> list[dict[str, Any]]:
    return [
        e
        for e in scenario["entities"]
        if e.get("faction") is not None and e.get("faction") != perspective
    ]


def _has_capability(entities: list[dict[str, Any]], key: str) -> bool:
    return any(key in entity.get("capabilities", {}) for entity in entities)


def _needs(key: str, side: Callable[[Scenario, str], list[dict[str, Any]]], who: str):
    def applies(scenario: Scenario, perspective: str) -> tuple[bool, str]:
        if _has_capability(side(scenario, perspective), key):
            return True, ""
        return False, f"no {who} entity has the capability {key!r}"

    return applies


def _needs_resources(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    stock = scenario["world_contract"].get("resource_state", {})
    if any(amount > 0 for amount in stock.values()):
        return True, ""
    return False, "the world holds no resources"


def _needs_own_hp(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if any("hp" in e.get("state", {}) for e in _own(scenario, perspective)):
        return True, ""
    return False, "no own entity has hp"


def _always(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if _own(scenario, perspective):
        return True, ""
    return False, "the perspective faction has no entities"


def _scale_capability(key: str, side, magnitudes, as_int: bool = False) -> Apply:
    def apply(scenario: Scenario, level: str, perspective: str) -> Scenario:
        factor = magnitudes[STRESS_LEVELS.index(level)]
        for entity in side(scenario, perspective):
            capabilities = entity.get("capabilities", {})
            if key in capabilities:
                value = capabilities[key] * factor
                capabilities[key] = int(value) if as_int else round(value, 4)
        return scenario

    return apply


def _everyone(scenario: Scenario, perspective: str) -> list[dict[str, Any]]:
    return [e for e in scenario["entities"]]


def _enemy_accuracy(scenario: Scenario, level: str, perspective: str) -> Scenario:
    bonus = ENEMY_BONUS[STRESS_LEVELS.index(level)]
    for entity in _enemies(scenario, perspective):
        capabilities = entity.get("capabilities", {})
        if "accuracy" in capabilities:
            capabilities["accuracy"] = round(
                min(1.0, capabilities["accuracy"] + bonus), 4
            )
    return scenario


def _scale_resources(magnitudes) -> Apply:
    def apply(scenario: Scenario, level: str, perspective: str) -> Scenario:
        factor = magnitudes[STRESS_LEVELS.index(level)]
        stock = scenario["world_contract"]["resource_state"]
        for resource_id in stock:
            stock[resource_id] = round(stock[resource_id] * factor, 4)
        return scenario

    return apply


def _own_hp(scenario: Scenario, level: str, perspective: str) -> Scenario:
    factor = HP_FACTORS[STRESS_LEVELS.index(level)]
    for entity in _own(scenario, perspective):
        state = entity.get("state", {})
        if "hp" in state:
            state["hp"] = max(1, int(state["hp"] * factor))
    return scenario


def _drop_orders(scenario: Scenario, level: str, perspective: str) -> Scenario:
    rate = DROP_RATES[STRESS_LEVELS.index(level)]
    rules = scenario["world_contract"].setdefault("rule_set", {})
    faults = dict(rules.get("faults", {}))
    faults["drop_actions"] = {"faction": perspective, "rate": rate}
    rules["faults"] = faults
    return scenario


ACCURACY_FACTORS = (0.9, 0.75, 0.6, 0.4)
DAMAGE_FACTORS = (0.9, 0.75, 0.5, 0.25)
HP_FACTORS = (0.9, 0.75, 0.6, 0.4)
DROP_RATES = (0.1, 0.25, 0.5, 0.8)
ENEMY_BONUS = (0.05, 0.1, 0.2, 0.35)
DELAY_FACTORS = (0.9, 0.75, 0.5, 0.25)
SHORTAGE_FACTORS = (0.75, 0.5, 0.25, 0.0)


FAILURE_VARIABLES: dict[str, FailureVariable] = {
    variable.name: variable
    for variable in (
        FailureVariable(
            "supply_delay",
            "Supplies arrive late: less of every world resource is on hand",
            "resource_model",
            DELAY_FACTORS,
            _needs_resources,
            _scale_resources(DELAY_FACTORS),
        ),
        FailureVariable(
            "sensor_failure",
            "Own sensors degrade: own accuracy drops",
            "combat_resolution",
            ACCURACY_FACTORS,
            _needs("accuracy", _own, "own"),
            _scale_capability("accuracy", _own, ACCURACY_FACTORS),
        ),
        FailureVariable(
            "communication_failure",
            "Orders do not get through: own actions fail before they start",
            "actor_policy",
            DROP_RATES,
            _always,
            _drop_orders,
        ),
        FailureVariable(
            "weather_degradation",
            "Weather worsens for everyone: all accuracy drops",
            "combat_resolution",
            ACCURACY_FACTORS,
            _needs("accuracy", _everyone, "any"),
            _scale_capability("accuracy", _everyone, ACCURACY_FACTORS),
        ),
        FailureVariable(
            "enemy_reaction_speed",
            "The enemy reacts faster: enemy accuracy rises",
            "combat_resolution",
            ENEMY_BONUS,
            _needs("accuracy", _enemies, "enemy"),
            _enemy_accuracy,
        ),
        FailureVariable(
            "equipment_overheat",
            "Own weapons overheat: own attack damage drops",
            "combat_resolution",
            DAMAGE_FACTORS,
            _needs("attack_damage", _own, "own"),
            _scale_capability("attack_damage", _own, DAMAGE_FACTORS, as_int=True),
        ),
        FailureVariable(
            "civilian_pressure",
            "Civilian pressure diverts and wears own forces: own starting hp drops",
            "force_availability",
            HP_FACTORS,
            _needs_own_hp,
            _own_hp,
        ),
        FailureVariable(
            "resource_shortage",
            "Resources run short: world resources shrink, down to none",
            "resource_model",
            SHORTAGE_FACTORS,
            _needs_resources,
            _scale_resources(SHORTAGE_FACTORS),
        ),
    )
}


def apply_stress(
    scenario: Scenario, variables: dict[str, str], perspective: str
) -> Scenario:
    """
    The scenario with each variable applied at its level, as a new version.

    Important:
    The input is never changed. The result is a version of the original:
    scenario_version "<original>+<variable>:<level>[+...]", version_control
    pointing back at the original, and changed_from_previous computed by
    compare_scenarios, so the record of what was stressed cannot drift from
    what was actually changed.

    A variable that does not apply raises ValueError; ask applies() first.
    """
    stressed = copy.deepcopy(scenario)
    for name, level in variables.items():
        variable = FAILURE_VARIABLES[name]
        if level not in STRESS_LEVELS:
            raise ValueError(f"unknown stress level {level!r}")
        applicable, reason = variable.applies(stressed, perspective)
        if not applicable:
            raise ValueError(f"{name} does not apply: {reason}")
        stressed = variable.apply(stressed, level, perspective)

    label = "+".join(f"{name}:{level}" for name, level in variables.items())
    return child_version(scenario, stressed, label, f"Failure exploration: {label}")
