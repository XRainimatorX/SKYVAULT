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


def _needs_public_order(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if any("public_order" in e.get("state", {}) for e in scenario["entities"]):
        return True, ""
    return False, "no entity has public order"


def _public_order(scenario: Scenario, level: str, perspective: str) -> Scenario:
    factor = ORDER_FACTORS[STRESS_LEVELS.index(level)]
    for entity in scenario["entities"]:
        state = entity.get("state", {})
        if "public_order" in state:
            state["public_order"] = round(float(state["public_order"]) * factor, 4)
    return scenario


def _drop_orders(scenario: Scenario, level: str, perspective: str) -> Scenario:
    rate = DROP_RATES[STRESS_LEVELS.index(level)]
    rules = scenario["world_contract"].setdefault("rule_set", {})
    faults = dict(rules.get("faults", {}))
    faults["drop_actions"] = {"faction": perspective, "rate": rate}
    rules["faults"] = faults
    return scenario


def _needs_state(key: str, side, who: str) -> Applies:
    def applies(scenario: Scenario, perspective: str) -> tuple[bool, str]:
        if any(key in e.get("state", {}) for e in side(scenario, perspective)):
            return True, ""
        return False, f"no {who} entity has {key}"

    return applies


def _scale_state(key: str, side, magnitudes, floor: float = 0.0) -> Apply:
    def apply(scenario: Scenario, level: str, perspective: str) -> Scenario:
        factor = magnitudes[STRESS_LEVELS.index(level)]
        for entity in side(scenario, perspective):
            state = entity.get("state", {})
            if key in state:
                state[key] = round(max(floor, float(state[key]) * factor), 4)
        return scenario

    return apply


def _enemy_hp(scenario: Scenario, level: str, perspective: str) -> Scenario:
    factor = UNDERESTIMATE[STRESS_LEVELS.index(level)]
    for entity in _enemies(scenario, perspective):
        state = entity.get("state", {})
        if "hp" in state:
            state["hp"] = int(round(state["hp"] * factor))
    return scenario


def _needs_enemy_hp(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if any("hp" in e.get("state", {}) for e in _enemies(scenario, perspective)):
        return True, ""
    return False, "no enemy entity has hp"


def _grid(scenario: Scenario) -> tuple[int, int] | None:
    space = scenario["world_contract"]["space_model"]
    if space.get("type", "grid") != "grid" or not space.get("width"):
        return None
    return int(space["width"]), int(space["height"])


def _centre(units: list[dict[str, Any]]) -> tuple[float, float]:
    xs = [u["position"][0] for u in units]
    ys = [u["position"][1] for u in units]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _needs_encirclement(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if _grid(scenario) is None:
        return False, "encirclement is measured on a grid"
    own = [u for u in _own(scenario, perspective) if u.get("position")]
    enemies = [u for u in _enemies(scenario, perspective) if u.get("position")]
    if not own or not enemies:
        return False, "both sides need units on the map"
    return True, ""


def _encircle(scenario: Scenario, level: str, perspective: str) -> Scenario:
    """
    A share of the enemy (by level) starts behind the perspective side: on
    the free, passable cells nearest the point as far behind its centre as
    the enemy is in front of it. The enemy's nearest units move first.
    """
    size = _grid(scenario)
    if size is None:  # pragma: no cover - applies refuses this
        raise ValueError("encirclement needs a grid")
    width, height = size
    own = [u for u in _own(scenario, perspective) if u.get("position")]
    enemies = [u for u in _enemies(scenario, perspective) if u.get("position")]
    ox, oy = _centre(own)
    ex, ey = _centre(enemies)
    rear = (
        min(width - 1.0, max(0.0, 2 * ox - ex)),
        min(height - 1.0, max(0.0, 2 * oy - ey)),
    )
    share = ENCIRCLED[STRESS_LEVELS.index(level)]
    moving = sorted(
        enemies,
        key=lambda u: (
            abs(u["position"][0] - ox) + abs(u["position"][1] - oy),
            u["entity_id"],
        ),
    )[: max(1, round(len(enemies) * share))]
    taken = {
        tuple(e["position"])
        for e in scenario["entities"]
        if e.get("position") and e not in moving
    } | _impassable(scenario)
    free = sorted(
        ((x, y) for x in range(width) for y in range(height) if (x, y) not in taken),
        key=lambda c: (abs(c[0] - rear[0]) + abs(c[1] - rear[1]), c),
    )
    for unit, cell in zip(moving, free, strict=False):
        unit["position"] = list(cell)
    return scenario


def _impassable(scenario: Scenario) -> set[tuple[int, int]]:
    """
    Cells no unit may stand on: map cells whose terrain has no move cost
    (environment_state.terrain with the domain's terrain table).
    """
    world = scenario["world_contract"]
    terrain = world.get("environment_state", {}).get("terrain")
    if not terrain:
        return set()
    table: dict[str, Any] = {}
    for group in world.get("rule_set", {}).values():
        if isinstance(group, dict) and isinstance(group.get("terrain"), dict):
            table = group["terrain"]
    return {
        (x, y)
        for y, row in enumerate(terrain["rows"])
        for x, mark in enumerate(row)
        if table.get(terrain["legend"][mark], {}).get("move_cost", 1) is None
    }


def _orders_wait(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    if not _own(scenario, perspective):
        return False, "the perspective faction has no entities"
    domain = scenario.get("domain")
    if domain:
        from ..domains import load_domain

        if "wait" not in load_domain(domain).action_types:
            return False, f"the {domain} domain has no wait order to hold units with"
    return True, ""


def _tempo(scenario: Scenario, level: str, perspective: str) -> Scenario:
    """The plan starts late: own units hold for the first ticks (by level)."""
    ticks = int(TEMPO_TICKS[STRESS_LEVELS.index(level)])
    runtime = scenario["runtime"]
    orders = list(runtime.get("scheduled_actions", []))
    busy = {(o["tick"], o["actor_id"]) for o in orders}
    for unit in sorted(_own(scenario, perspective), key=lambda u: u["entity_id"]):
        for tick in range(1, ticks + 1):
            if (tick, unit["entity_id"]) not in busy:
                orders.append(
                    {
                        "tick": tick,
                        "actor_id": unit["entity_id"],
                        "action_type": "wait",
                        "target": {},
                        "system_id": "failure_exploration",
                        "intent": "tempo_delay",
                    }
                )
    runtime["scheduled_actions"] = orders
    return scenario


def _needs_districts(scenario: Scenario, perspective: str) -> tuple[bool, str]:
    rules = scenario["world_contract"].get("rule_set", {})
    if "city" in rules and any(
        e.get("entity_type") == "district" for e in scenario["entities"]
    ):
        return True, ""
    return False, "public sentiment is modelled in a city's districts"


def _sentiment(scenario: Scenario, level: str, perspective: str) -> Scenario:
    """Every district starts under emotional pressure (the information model)."""
    pressure = SENTIMENT[STRESS_LEVELS.index(level)]
    city = scenario["world_contract"]["rule_set"]["city"]
    info = dict(city.get("information") or {})
    initial = dict(info.get("initial") or {})
    for entity in scenario["entities"]:
        if entity.get("entity_type") == "district":
            initial[entity["entity_id"]] = max(
                float(initial.get(entity["entity_id"], 0.0)), pressure
            )
    info["initial"] = initial
    city["information"] = info
    return scenario


def _only_in(what: str) -> Applies:
    def applies(scenario: Scenario, perspective: str) -> tuple[bool, str]:
        return False, f"{what}"

    return applies


def _unchanged(scenario: Scenario, level: str, perspective: str) -> Scenario:
    return scenario  # pragma: no cover - its applies always refuses


ACCURACY_FACTORS = (0.9, 0.75, 0.6, 0.4)
DAMAGE_FACTORS = (0.9, 0.75, 0.5, 0.25)
HP_FACTORS = (0.9, 0.75, 0.6, 0.4)
DROP_RATES = (0.1, 0.25, 0.5, 0.8)
ENEMY_BONUS = (0.05, 0.1, 0.2, 0.35)
DELAY_FACTORS = (0.9, 0.75, 0.5, 0.25)
SHORTAGE_FACTORS = (0.75, 0.5, 0.25, 0.0)
ORDER_FACTORS = (0.85, 0.65, 0.45, 0.25)
UNDERESTIMATE = (1.15, 1.3, 1.6, 2.0)
ENCIRCLED = (0.25, 0.5, 0.75, 1.0)
MORALE_FACTORS = (0.8, 0.6, 0.4, 0.2)
TEMPO_TICKS = (1.0, 2.0, 4.0, 8.0)
ADMIN_FACTORS = (0.75, 0.5, 0.25, 0.0)
SENTIMENT = (20.0, 35.0, 55.0, 80.0)
ENDURANCE_FACTORS = (0.75, 0.5, 0.25, 0.1)
ENERGY_FACTORS = (0.75, 0.5, 0.25, 0.1)


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
        FailureVariable(
            "public_order_collapse",
            "Public order collapses: every entity's public order falls",
            "public_order",
            ORDER_FACTORS,
            _needs_public_order,
            _public_order,
        ),
        # Formal Spec 14.2, row by row (FAILURE_TAXONOMY)
        FailureVariable(
            "encirclement",
            "Encircled: part of the enemy starts behind the side",
            "force_disposition",
            ENCIRCLED,
            _needs_encirclement,
            _encircle,
        ),
        FailureVariable(
            "intelligence_error",
            "Intelligence was wrong: the enemy is stronger than reported",
            "intelligence_estimate",
            UNDERESTIMATE,
            _needs_enemy_hp,
            _enemy_hp,
        ),
        FailureVariable(
            "formation_collapse",
            "Cohesion breaks: own units start with lower morale",
            "unit_cohesion",
            MORALE_FACTORS,
            _needs_state("morale", _own, "own"),
            _scale_state("morale", _own, MORALE_FACTORS),
        ),
        FailureVariable(
            "tempo_delay",
            "The plan starts late: own units hold for its first ticks",
            "plan_timing",
            TEMPO_TICKS,
            _orders_wait,
            _tempo,
        ),
        FailureVariable(
            "administration_collapse",
            "Administration breaks down: every administration falls, to none",
            "administration",
            ADMIN_FACTORS,
            _needs_state("administration", _everyone, "any"),
            _scale_state("administration", _everyone, ADMIN_FACTORS),
        ),
        FailureVariable(
            "public_sentiment_decline",
            "Public sentiment turns: every district starts under emotional pressure",
            "public_sentiment",
            SENTIMENT,
            _needs_districts,
            _sentiment,
        ),
        FailureVariable(
            "endurance_shortfall",
            "Endurance falls short: own equipment runs out sooner",
            "equipment_endurance",
            ENDURANCE_FACTORS,
            _needs("endurance_ticks", _own, "own"),
            _scale_capability("endurance_ticks", _own, ENDURANCE_FACTORS, as_int=True),
        ),
        FailureVariable(
            "energy_depletion",
            "Energy runs low: own units start with less energy",
            "energy_supply",
            ENERGY_FACTORS,
            _needs_state("energy", _own, "own"),
            _scale_state("energy", _own, ENERGY_FACTORS),
        ),
        *(
            FailureVariable(
                name,
                description,
                "airspace_model",
                (1.0, 1.0, 1.0, 1.0),
                _only_in(f"{name} is modelled in an airspace scenario"),
                _unchanged,
            )
            for name, description in (
                ("misidentification", "Tracks are misidentified more often"),
                ("reaction_delay", "The defence reacts later to every track"),
                ("target_saturation", "More threats than the defence was sized for"),
                ("collision", "Threats fly at the drones' altitude"),
                ("path_blocked", "Drone waypoints are closed to flight"),
            )
        ),
    )
}


def variable_for(scenario: Scenario, name: str) -> FailureVariable:
    """
    The failure variable name means in this scenario: the domain pack's own
    version when it offers one (failure_variables()), else the core one.

    Important:
    A city's supply_delay makes supplies arrive late; the core one only
    shrinks stock. The name, the levels and the place in a failure map stay
    the same (Phase 14).
    """
    if scenario.get("domain"):
        from ..domains import load_domain

        offered = getattr(load_domain(scenario["domain"]), "failure_variables", None)
        if offered is not None and name in offered():
            variable: FailureVariable = offered()[name]
            return variable
    return FAILURE_VARIABLES[name]


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
        variable = variable_for(stressed, name)
        if level not in STRESS_LEVELS:
            raise ValueError(f"unknown stress level {level!r}")
        applicable, reason = variable.applies(stressed, perspective)
        if not applicable:
            raise ValueError(f"{name} does not apply: {reason}")
        stressed = variable.apply(stressed, level, perspective)

    label = "+".join(f"{name}:{level}" for name, level in variables.items())
    return child_version(scenario, stressed, label, f"Failure exploration: {label}")
