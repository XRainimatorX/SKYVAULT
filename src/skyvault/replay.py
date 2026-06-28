import copy
import json

#reading from these to get scenario id and entities at each tick
with open("../../data/scenarios/tactical_reference_001.json", "r") as tr:
    tactical_reference = json.load(tr)
with open("../../output/event_memory.json", "r") as em:
    event_memory = json.load(em)
with open("../../output/final_state.json", "r") as fs:
    final_state = json.load(fs)

#scenario id from tr
scenario_id = tactical_reference["scenario_id"]

#stores the latest known state of every entity
current_entities = {
    entity["entity_id"]: copy.deepcopy(entity)
    for entity in tactical_reference["entities"]
}

#initial tick
replay_state_at_tick = {
    "scenario_id": scenario_id,
    "states": {
        "0": {
            "description": "initial state",
            "world_state": copy.deepcopy(current_entities)
        }
    }
}

#tracks the previous tick so we know when we've finished processing a tick
previous_tick = None

#process every event and build a snapshot of the world after each tick
for event in event_memory:
    tick = event["time"]
    after_state = event["after_state"]

    #an if statement to check if all events in the tick have finished running
    if previous_tick is not None and tick != previous_tick:
        #if the previous tick not equal to the coming tick it will take a snapshot of the latest known state of all entities after the previous tick
        replay_state_at_tick["states"][str(previous_tick)] = {
            "description": f"after tick {previous_tick}",
            "world_state": copy.deepcopy(current_entities)
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
        "world_state": copy.deepcopy(current_entities)
    }

#replay final state
replay_state_at_tick["states"]["final"] = {
    "description": "final state",
    "world_state": final_state["entities"]
}

#write json
with open("../../output/replay_state_at_tick.json", "w") as f:
    json.dump(replay_state_at_tick, f, indent=4)