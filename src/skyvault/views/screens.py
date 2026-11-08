"""View models = what each screen shows, derived from the run outputs.

Important:
Pure functions over plain dicts. They import only the standard library and
the exporters (which are themselves pure), never the engine: a screen can
only show what the run recorded. Every list comes out in an order fixed by
the input, so the same workspace always gives the same screens.
"""

import math
from typing import Any

from ..causal_chain import build_causal_chain
from ..replay import build_replay_state_at_tick
from ..timeline import build_entity_names, write_event

STRESS_ORDER = ("mild", "moderate", "severe", "collapse")

PACKAGE_LABELS = {
    "scenario_id": "Scenario",
    "scenario_version": "Scenario version",
    "initial_world_state": "World at the start",
    "final_world_state": "World at the end",
    "event_memory": "Everything that happened",
    "evaluation_result": "Judgement",
    "score_breakdown": "Why each axis scored what it did",
    "anti_gaming_report": "Was the score gamed",
    "tradeoff_report": "What was gained and what it cost",
    "reproducibility": "How to reproduce this run",
}


def overview_view(package: dict[str, Any]) -> dict[str, Any]:
    """The run on one screen: result, verdict, axis scores, findings, losses."""
    evaluation = package["evaluation_result"]
    events = package["event_memory"]
    return {
        "scenario_id": package["scenario_id"],
        "scenario_version": package["scenario_version"],
        "result": evaluation["winner_or_result"],
        "verdict": evaluation["overall_judgement"]["status"],
        "confidence": evaluation["overall_judgement"]["confidence"],
        "score": evaluation["overall_score"],
        "profile_id": evaluation["profile_id"],
        "perspective": evaluation["perspective"],
        "event_count": len(events),
        "ticks": max((event["time"] for event in events), default=0),
        "scores": dict(evaluation["scores"]),
        "key_findings": list(evaluation["key_findings"]),
        "failure_causes": list(evaluation["failure_causes"]),
        "recommended_next_tests": list(evaluation["recommended_next_tests"]),
        "flagged_behaviors": list(evaluation["anti_gaming"]["flagged_behaviors"]),
        "losses": losses(package),
    }


def losses(package: dict[str, Any]) -> list[dict[str, Any]]:
    """
    What each faction lost, in the order factions first appear.

    Each loss names the unit, the tick and who destroyed it, in the order
    the run recorded the destructions.
    """
    entities = package["initial_world_state"]["entities"]
    names = _names(package)
    factions: dict[str, dict[str, Any]] = {}
    for entity in entities.values():
        faction = factions.setdefault(
            entity["faction"], {"faction": entity["faction"], "units": 0, "lost": []}
        )
        faction["units"] += 1
    for event in package["event_memory"]:
        if event["event_type"] != "ENTITY_DESTROYED":
            continue
        target = event["target_entity_id"]
        by = event["source"]["actor_id"]
        factions[entities[target]["faction"]]["lost"].append(
            {
                "entity_id": target,
                "name": names.get(target, target),
                "tick": event["time"],
                "by": by,
                "by_name": names.get(by, by),
            }
        )
    return list(factions.values())


def timeline_view(package: dict[str, Any]) -> dict[str, Any]:
    """
    The run tick by tick, in the timeline exporter's own sentences.

    Each tick lists its sentences and the units destroyed in it.
    """
    events = package["event_memory"]
    names = _names(package)
    ticks = []
    for tick in range(1, max((e["time"] for e in events), default=0) + 1):
        in_tick = [event for event in events if event["time"] == tick]
        ticks.append(
            {
                "tick": tick,
                "lines": _sentences(tick, names, in_tick),
                "destroyed": [
                    {
                        "entity_id": event["target_entity_id"],
                        "name": names.get(
                            event["target_entity_id"], event["target_entity_id"]
                        ),
                        "by": event["source"]["actor_id"],
                        "by_name": names.get(
                            event["source"]["actor_id"], event["source"]["actor_id"]
                        ),
                    }
                    for event in in_tick
                    if event["event_type"] == "ENTITY_DESTROYED"
                ],
            }
        )
    return {"scenario_id": package["scenario_id"], "ticks": ticks}


def map_view(package: dict[str, Any]) -> dict[str, Any]:
    """
    The space and one frame per tick: where every unit was and its hp.

    Important:
    Frames come from the replay exporter (tick 0 is the start). hp below 0
    is shown as 0, as the timeline exporter shows it. A graph or
    network space gets node coordinates on a circle, in the order the space
    lists its nodes, so the drawing never changes between loads.
    """
    initial = package["initial_world_state"]
    replay = build_replay_state_at_tick(
        initial, package["event_memory"], package["final_world_state"]
    )
    timeline = {tick["tick"]: tick["lines"] for tick in timeline_view(package)["ticks"]}
    start_hp = {
        entity_id: entity["state"].get("hp")
        for entity_id, entity in initial["entities"].items()
    }
    frames = []
    for key, state in replay["states"].items():
        if not key.isdigit():
            continue
        tick = int(key)
        frames.append(
            {
                "tick": tick,
                "units": [
                    {
                        "entity_id": entity_id,
                        "name": entity.get("name", entity_id),
                        "faction": entity["faction"],
                        "position": entity["position"],
                        "hp": _display_hp(entity["state"].get("hp")),
                        "max_hp": start_hp.get(entity_id),
                        "status": entity["state"].get("status", "active"),
                    }
                    for entity_id, entity in state["world_state"].items()
                ],
                "lines": timeline.get(tick, []),
            }
        )
    return {"space": _space(initial["space"]), "frames": frames}


def causal_view(package: dict[str, Any]) -> dict[str, Any]:
    """Every action with the events it caused, named for a person to read."""
    events = {event["event_id"]: event for event in package["event_memory"]}
    names = _names(package)
    chains = []
    for chain in build_causal_chain(package["scenario_id"], package["event_memory"])[
        "chains"
    ]:
        first = events[chain["events"][0]]
        actor = first["source"]["actor_id"]
        target = first.get("target_entity_id")
        chains.append(
            {
                "action_id": chain["source_action_id"],
                "tick": first["time"],
                "actor": names.get(actor, actor),
                "target": names.get(target, target) if target else None,
                "event_types": list(chain["event_types"]),
                "events": list(chain["events"]),
                "summary": chain["summary"],
            }
        )
    return {"scenario_id": package["scenario_id"], "chains": chains}


def failure_view(workspace: dict[str, Any]) -> dict[str, Any] | None:
    """
    The failure map as a table: survival per variable and stress level.

    None when the workspace has no failure exploration.
    """
    failure_map = workspace.get("failure_map")
    if failure_map is None:
        return None
    seen = {
        level["level"]
        for variable in failure_map["variables"]
        for level in variable["levels"]
    }
    levels = [level for level in STRESS_ORDER if level in seen]
    rows = []
    for variable in failure_map["variables"]:
        by_level = {level["level"]: level for level in variable["levels"]}
        rows.append(
            {
                "variable": variable["variable"],
                "applicable": variable["applicable"],
                "reason": variable["reason"],
                "assumption": variable["assumption"],
                "survival": [
                    by_level[level]["survival_rate"] if level in by_level else None
                    for level in levels
                ],
                "breaking_level": variable["breaking_level"],
                "sensitivity": variable["sensitivity"],
            }
        )
    conditions = workspace.get("survival_conditions") or {}
    return {
        "scenario_version": failure_map["scenario_version"],
        "repeat_count": failure_map["repeat_count"],
        "survival_threshold": failure_map["survival_threshold"],
        "baseline_survival": failure_map["baseline"]["survival_rate"],
        "fails_without_stress": failure_map["baseline"]["fails_without_stress"],
        "levels": levels,
        "rows": rows,
        "crushing_variable": failure_map["crushing_variable"],
        "crushing_assumption": failure_map["crushing_assumption"],
        "failure_points": list(failure_map["failure_points"]),
        "failure_causes": list(failure_map["failure_causes"]),
        "how_fast": dict(failure_map["how_fast"]),
        "alternatives": list(failure_map["alternatives"]),
        "best_alternative": failure_map["best_alternative"],
        "collapse_sequence": workspace.get("collapse_sequence"),
        "conditions": list(conditions.get("conditions", [])),
        "recommendations": workspace.get("recommended_modifications"),
    }


def comparison_view(workspace: dict[str, Any]) -> dict[str, Any] | None:
    """
    The batch side by side, with the conflict package when there was one.

    None when the workspace has no batch. Individual runs are left out: the
    screen compares variants, and the run records stay in batch_result.json.
    """
    batch = workspace.get("batch_result")
    if batch is None:
        return None
    comparison = workspace.get("branch_comparison") or {}
    return {
        "batch_id": batch["batch_id"],
        "scenario_id": batch["scenario_id"],
        "base_version": batch["base_version"],
        "profile_id": batch["profile_id"],
        "perspective": batch["perspective"],
        "repeat_count": batch["repeat_count"],
        "total_runs": batch["total_runs"],
        "variants": list(batch["variants"]),
        "metrics": dict(comparison.get("metrics", {})),
        "best": dict(comparison.get("best", {})),
        "ranking": list(comparison.get("ranking", [])),
        "conflict_package": workspace.get("conflict_package"),
    }


def package_view(package: dict[str, Any]) -> dict[str, Any]:
    """Every top-level part of the result package with a label and a summary."""
    return {
        "sections": [
            {
                "key": key,
                "label": PACKAGE_LABELS.get(key, key),
                "summary": _summary(key, value),
                "raw": value,
            }
            for key, value in package.items()
        ]
    }


def _names(package: dict[str, Any]) -> dict[str, str]:
    names = {
        entity_id: entity.get("name", entity_id)
        for entity_id, entity in package["initial_world_state"]["entities"].items()
    }
    names.update(build_entity_names(package["event_memory"]))
    return names


def _sentences(
    tick: int, names: dict[str, str], events: list[dict[str, Any]]
) -> list[str]:
    """The timeline exporter's lines for one tick, without the header."""
    lines = write_event(tick, names, events)[1:]
    return [line.strip().removeprefix("- ") for line in lines if line.strip()]


def _display_hp(hp: Any) -> Any:
    """hp as the timeline shows it: a killing blow reads 0, not below."""
    if isinstance(hp, int | float) and hp < 0:
        return 0
    return hp


def _space(space: dict[str, Any]) -> dict[str, Any]:
    if space["type"] == "grid":
        return {"type": "grid", "width": space["width"], "height": space["height"]}
    nodes = list(space.get("nodes", []))
    count = max(len(nodes), 1)
    return {
        "type": space["type"],
        "nodes": [
            {
                "id": node,
                # + 0.0 turns -0.0 into 0.0
                "x": round(math.cos(2 * math.pi * index / count), 4) + 0.0,
                "y": round(math.sin(2 * math.pi * index / count), 4) + 0.0,
            }
            for index, node in enumerate(nodes)
        ],
        "edges": [list(edge) for edge in space.get("edges", [])],
    }


def _summary(key: str, value: Any) -> str:
    if key == "event_memory":
        return f"{len(value)} events"
    if key in ("initial_world_state", "final_world_state"):
        active = sum(
            1
            for entity in value["entities"].values()
            if entity["state"].get("status", "active") == "active"
        )
        return f"tick {value['tick']}: {len(value['entities'])} units, {active} active"
    if key == "evaluation_result":
        judgement = value["overall_judgement"]
        return (
            f"{value['winner_or_result']}; {judgement['status']} "
            f"(score {value['overall_score']:.2f})"
        )
    if key == "score_breakdown":
        return f"{len(value)} axes"
    if key == "anti_gaming_report":
        flagged = value.get("flagged_behaviors", [])
        if not flagged:
            return "nothing flagged"
        return f"{len(flagged)} flagged behaviour" + ("s" if len(flagged) > 1 else "")
    if key == "tradeoff_report":
        return f"{len(value.get('tradeoffs', []))} trade-offs"
    if key == "reproducibility":
        return f"run {value['run_id']}, output {value['output_hash'][:12]}"
    return str(value)
