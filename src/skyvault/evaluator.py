from typing import Any

from .world_state import WorldState


def build_evaluation_summary(
    world: WorldState,
    termination_reason: str,
) -> dict[str, Any]:
    """
    Evaluation summary = the minimum verdict a finished scenario has to report.

    Important:
    This is not the Phase 7 evaluation engine.

    It only produces the fields that the SCENARIO_END event, result_package.json
    and the timeline final summary need. It does not score, weigh or rank
    anything, and it never mutates the world.
    """
    active_entities = world.active_entities()
    destroyed_entities = [
        entity
        for entity in world.entities.values()
        if entity.state.get("status") == "destroyed"
    ]

    active_factions = world.active_factions()

    if len(active_factions) == 0:
        winner_or_result = "draw_all_destroyed"
    elif len(active_factions) == 1:
        winner_or_result = f"{next(iter(active_factions))}_survived"
    else:
        winner_or_result = "no_winner_duration_limit"

    return {
        "termination_reason": termination_reason,
        "event_count": len(world.event_memory),
        "active_entities": len(active_entities),
        "destroyed_entities": len(destroyed_entities),
        "active_factions": sorted(active_factions),
        "winner_or_result": winner_or_result,
        "key_findings": [
            f"Scenario ended because: {termination_reason}",
            f"Events recorded: {len(world.event_memory)}",
            f"Destroyed entities: {len(destroyed_entities)}",
        ],
        "failure_points": [
            "Entity destroyed"
            for _ in destroyed_entities
        ],
    }
