"""Explore failures = run a plan, and every stressed version of it, many times.

Important:
This module sits above the engine, next to verification: it builds engines.
It only collects what each run produced; turning that into a failure map is
failure.analysis, which reads plain data and runs nothing.
"""

import copy
from pathlib import Path
from typing import Any

from ..contracts import validate_failure_exploration
from ..engine import SkyVaultEngine
from ..scenario_loader import load_scenario, scenario_perspective
from ..verification import SCENARIO_DIR
from .analysis import sensitivity, survival_rate
from .variables import apply_stress, variable_for

BRANCH_LEVEL = "moderate"


def explore_failures(
    scenario: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any] | None = None,
    scenarios_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Stress a plan and its alternatives, and return every run's summary.

    A plan is a scenario judged under a profile from one perspective. config
    is the scenario's failure_exploration unless given. Each stressed version
    runs repeat_count times; with controlled_random the i-th repeat uses the
    scenario seed + i, with fixed every repeat uses the same seed.

    Returns plain data: the baseline runs, the runs per variable and level,
    the branch (the two most damaging variables at moderate together), and
    the same sweep for every alternative version named in config.
    """
    config = _with_defaults(
        validate_failure_exploration(config or scenario["failure_exploration"])
    )
    perspective = profile.get("perspective") or scenario_perspective(scenario)
    if perspective is None:
        raise ValueError("the plan has no perspective to judge failures from")
    seeds = _seeds(scenario, config)
    folder = (scenarios_dir or SCENARIO_DIR) / scenario["scenario_id"]

    def run_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [_run(plan, profile, seed, perspective) for seed in seeds]

    def sweep(plan: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in config["failure_variables"]:
            variable = variable_for(plan, name)
            applicable, reason = variable.applies(plan, perspective)
            levels = (
                {
                    level: run_plan(apply_stress(plan, {name: level}, perspective))
                    for level in config["stress_levels"]
                }
                if applicable
                else {}
            )
            result[name] = {
                "applicable": applicable,
                "reason": reason,
                "assumption": variable.assumption,
                "levels": levels,
            }
        return result

    baseline = run_plan(scenario)
    variables = sweep(scenario)

    branches = []
    if config["run_policy"]["branch_comparison"]:
        ranked = sorted(
            (
                (sensitivity(baseline, entry["levels"]), name)
                for name, entry in variables.items()
                if entry["applicable"]
            ),
            reverse=True,
        )
        pair = [name for value, name in ranked[:2] if value > 0]
        if len(pair) == 2:
            level = (
                BRANCH_LEVEL
                if BRANCH_LEVEL in config["stress_levels"]
                else (config["stress_levels"][0])
            )
            stressed = apply_stress(
                scenario, {name: level for name in pair}, perspective
            )
            branches.append(
                {"variables": pair, "level": level, "runs": run_plan(stressed)}
            )

    alternatives = []
    for version in config["alternatives"]:
        alternative = load_scenario(folder / f"{version}.json")
        alternatives.append(
            {
                "scenario_version": version,
                "baseline": run_plan(alternative),
                "variables": sweep(alternative),
            }
        )

    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_version": scenario["scenario_version"],
        "perspective": perspective,
        "profile_id": profile["profile_id"],
        "objective": config["objective"],
        "repeat_count": config["run_policy"]["repeat_count"],
        "seeds": seeds,
        "survival_threshold": config["survival_threshold"],
        "stress_levels": list(config["stress_levels"]),
        "baseline": baseline,
        "baseline_survival_rate": survival_rate(baseline),
        "variables": variables,
        "branches": branches,
        "alternatives": alternatives,
    }


def _with_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """
    The request with every optional field present.

    Important:
    Contract validation returns only the fields that were supplied, so the
    contract's defaults have to be restated where the request is used.
    """
    filled = {
        "objective": "find_weakness",
        "alternatives": [],
        "survival_threshold": 0.5,
        **config,
    }
    filled["run_policy"] = {"branch_comparison": False, **config["run_policy"]}
    return filled


def _seeds(scenario: dict[str, Any], config: dict[str, Any]) -> list[int]:
    seed = int(scenario["runtime"]["random_seed"])
    count = config["run_policy"]["repeat_count"]
    if config["run_policy"]["random_seed_policy"] == "fixed":
        return [seed] * count
    return [seed + offset for offset in range(count)]


def _run(
    scenario: dict[str, Any], profile: dict[str, Any], seed: int, perspective: str
) -> dict[str, Any]:
    """One run, reduced to what a failure map needs."""
    seeded = copy.deepcopy(scenario)
    seeded["runtime"]["random_seed"] = seed
    package = SkyVaultEngine(seeded, profile).run()
    verdict = package["evaluation_result"]
    factions = {
        entity_id: entity.get("faction")
        for entity_id, entity in package["initial_world_state"]["entities"].items()
    }
    losses = [
        {
            "tick": event["time"],
            "entity": event["target_entity_id"],
            "by": event["source"]["actor_id"],
        }
        for event in package["event_memory"]
        if event["event_type"] == "ENTITY_DESTROYED"
        and factions.get(event["target_entity_id"]) == perspective
    ]
    own = [
        entity_id for entity_id, faction in factions.items() if faction == perspective
    ]
    eliminated = len({loss["entity"] for loss in losses}) == len(own) and bool(own)
    return {
        "seed": seed,
        "scenario_version": scenario["scenario_version"],
        "status": verdict["overall_judgement"]["status"],
        "survived": verdict["overall_judgement"]["status"] != "fail",
        "score": verdict["overall_score"],
        "outcome": verdict["winner_or_result"],
        "event_count": verdict["event_count"],
        "losses": losses,
        "first_loss_tick": losses[0]["tick"] if losses else None,
        "elimination_tick": losses[-1]["tick"] if eliminated else None,
        "failure_causes": list(verdict["failure_causes"]),
        "output_hash": package["reproducibility"]["output_hash"],
    }
