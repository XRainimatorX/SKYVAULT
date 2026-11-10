"""History = the units tick by tick, and the observations of a finished run.

Important:
The engine keeps the same history while it runs (units at the end of every
tick, the start as tick 0). After a run it is rebuilt from the result
package through the replay exporter, so both paths see the same world.
"""

from collections.abc import Callable
from typing import Any

from ..actions import MILITARY_ACTION_TYPES
from ..domains import load_domain
from ..replay import build_replay_state_at_tick
from .observe import History, observe


def history_from_package(package: dict[str, Any]) -> History:
    """
    {tick: units} for every tick from 0 to the last, from the package alone.

    Important:
    A tick in which nothing happened keeps the units of the tick before it.
    The last tick is the final world state.
    """
    states = build_replay_state_at_tick(
        package["initial_world_state"],
        package["event_memory"],
        package["final_world_state"],
    )["states"]
    recorded = {
        int(key): value["world_state"] for key, value in states.items() if key.isdigit()
    }
    last = int(package["final_world_state"]["tick"])
    recorded[last] = package["final_world_state"]["entities"]
    history: History = {}
    for tick in range(last + 1):
        history[tick] = recorded.get(tick, history.get(tick - 1, recorded[0]))
    return history


def concealment_for(scenario: dict[str, Any]) -> Callable[[Any], float] | None:
    """The domain pack's concealment of a cell, when the scenario has one."""
    if not scenario.get("domain"):
        return None
    hook = getattr(load_domain(scenario["domain"]), "concealment", None)
    if hook is None:
        return None
    return lambda cell: float(hook(scenario, cell))


def available_actions(scenario: dict[str, Any]) -> list[str]:
    """The action types a decision may name: the domain pack's, else the core line."""
    if scenario.get("domain"):
        return sorted(load_domain(scenario["domain"]).action_types)
    return sorted(MILITARY_ACTION_TYPES)


def context_for(
    scenario: dict[str, Any], faction: str, resources: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Everything an observation needs that units do not carry.

    Important:
    The mission is the domain pack's mission for the faction when it offers
    one (mission_goal), else the world's stated purpose.
    """
    world = scenario["world_contract"]
    max_ticks = int(scenario["runtime"].get("max_ticks", 10))
    mission: Any = world.get("purpose")
    if scenario.get("domain"):
        hook = getattr(load_domain(scenario["domain"]), "mission_goal", None)
        if hook is not None:
            mission = hook(scenario, faction)
    return {
        "max_ticks": max_ticks,
        "resources": dict(resources or {}),
        "available_actions": available_actions(scenario),
        "mission": mission,
        "constraints": [f"max_ticks={max_ticks}"],
        "concealment": concealment_for(scenario),
        "space": world["space_model"],
    }


def observations_for_run(
    package: dict[str, Any],
    scenario: dict[str, Any],
    profile: dict[str, Any],
    viewpoint: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    One observation per tick of a finished run, from tick 0 to the last.

    Important:
    resources_visible is the world's resource ledger at the end of the run:
    the package keeps no ledger per tick.
    """
    history = history_from_package(package)
    context = context_for(
        scenario,
        viewpoint["faction"],
        package["final_world_state"].get("resources"),
    )
    return [observe(history, tick, profile, viewpoint, context) for tick in history]
