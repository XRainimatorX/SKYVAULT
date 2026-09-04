import copy
from typing import Any


def build_replay_state_at_tick(
    scenario: dict[str, Any],
    event_memory: list[dict[str, Any]],
    final_world_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Replay state = what the world looked like at the end of every tick.

    Important:
    This is a derived output. It reads event memory and never mutates it.

    Everything it needs is passed in, so importing this module has no side
    effects and the caller decides where the result is written.
    """
    scenario_id = scenario["scenario_id"]

    #stores the latest known state of every entity
    current_entities = {
        entity["entity_id"]: copy.deepcopy(entity)
        for entity in scenario["entities"]
    }

    #initial tick
    replay_state_at_tick = {
        "scenario_id": scenario_id,
        "states": {
            "0": {
                "description": "initial state",
                "world_state": copy.deepcopy(current_entities),
            }
        },
    }

    #tracks the previous tick so we know when we've finished processing a tick
    previous_tick = None

    #process every event and build a snapshot of the world after each tick
    for event in event_memory:
        tick = event["time"]
        after_state = event["after_state"]

        #an if statement to check if all events in the tick have finished running
        if previous_tick is not None and tick != previous_tick:
            #if the previous tick not equal to the coming tick it will take a
            #snapshot of the latest known state of all entities after the previous tick
            replay_state_at_tick["states"][str(previous_tick)] = {
                "description": f"after tick {previous_tick}",
                "world_state": copy.deepcopy(current_entities),
            }

        #update the latest known state of the entity using this event's after_state.
        if "entity_id" in after_state:
            entity_id = after_state["entity_id"]
            current_entities[entity_id] = copy.deepcopy(after_state)

        previous_tick = tick

    #since a tick is only saved when the next tick begins,
    #save the final tick after the loop finishes
    if previous_tick is not None:
        replay_state_at_tick["states"][str(previous_tick)] = {
            "description": f"after tick {previous_tick}",
            "world_state": copy.deepcopy(current_entities),
        }

    #replay final state
    replay_state_at_tick["states"]["final"] = {
        "description": "final state",
        "world_state": copy.deepcopy(final_world_state["entities"]),
    }

    return replay_state_at_tick
