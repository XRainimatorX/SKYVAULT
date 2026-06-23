import sys
from pathlib import Path
import json

# Add in the relative src folder path to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2] # Redirect root to SKYVAULT
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Define a function to write data into a json
# Parameter 1 takes in the list of entities
# Parameter 2 takes in the list of events from event_memory.json
def write_history(entity_list: list, event_list: list):

    # Write all data into this master dictionary
    master_dict = {}

    # # Declare variables to be used within this function (optional)

    # For initial formatting
    time: int
    event_type: str
    role_in_event : str
    initial_state: dict
    temp_dict: dict

    # All other variables required in the "history" section
    event_id: str
    target_entity_id: str
    source_action_id: str
    before_state: dict
    after_state: dict
    data: dict
    tags: list
    target_dict: dict

    # A dictionary set up for saving down states of actors for writing data correctly
    actor_state_dict = {}

    # Initiate the master dictionary by setting up a format
    for entity in entity_list:
        
        # Initial data: 1. entity_id 2. name 3. faction 4. history
        entity_id = entity["entity_id"]
        name = entity["name"]
        faction = entity["faction"]
        initial_state = entity["state"]

        # Start with making a key from each entity_id
        master_dict[entity_id] = {}

        # Then add in basic details for each entity
        master_dict[entity_id]["entity_id"] = entity_id
        master_dict[entity_id]["name"] = name
        master_dict[entity_id]["faction"] = faction
        master_dict[entity_id]["history"] = [] # A huge list of events for each entity

        # Finally adds in the initial state for each entity
        time = 0
        event_type = "INITIAL_STATE"
        role_in_event = "initial_state"

        temp_dict = {
            "time": time,
            "event": event_type,
            "role_in_event": role_in_event,
            "initial_state": initial_state
        }

        # Write in the initial state for each entity at the end
        master_dict[entity_id]["history"].append(temp_dict)

    # # Loop through from time 1 to 10 and write data in
    # for count in range(max_ticks): # max_ticks is defined globally so does not need to be passed in

    #     time = count + 1 # Increment time so that it matches the scenario

    # Loop through the event_list to write data into the master dict
    for event in event_list:

        time = event["time"]
        event_type = event["event_type"]

        # Default value for roles as the actor
        role_in_event = "actor"

        # Data to be extracted regardless of the ending of a scenario
        event_id = event["event_id"]
        source_action_id = event["source_action_id"]
        tags = event["tags"]

        # actor_id = event["actor_id"]
        # role_in_event = "actor"
        # event_id = event["event_id"]
        # target_entity_id = event["target_entity_id"]
        # source_action_id = event["source_action_id"]
        # before_state = event["before_state"]
        # after_state = event["after_state"]
        # data = event["data"]
        # tags = event["tags"]

        # If the scenario hasn't ended
        if event_type != "SCENARIO_END":

            # Data to be extracted regardless of the presence of a target
            actor_id = event["actor_id"]
            target_entity_id = event["target_entity_id"]
            before_state = event["before_state"]
            after_state = event["after_state"]
            data = event["data"]

            # Writes a format regardless of the presence of a target
            temp_dict = {
                "time": time,
                "event_type": event_type,
                "role_in_event": role_in_event,
                "event_id": event_id,
                "source_action_id": source_action_id,
                "before_state": before_state,
                "after_state": after_state,
                "data": data,
                "tags": tags
            }

            # # Write the data stored in temp_dict into the corresponding entities' history
            # master_dict[actor_id]["history"].append(temp_dict)

            # If there isn't a target in this event or if event_type == "ACTION_SELECTED"
            # Since both of the states are correct about the actor
            if target_entity_id == None or event_type == "ACTION_SELECTED":

                # Save down the states of the actor only when there is no target
                # Initiate dictionaries inside the actor_state_dict if the actor is not in it
                if actor_id not in actor_state_dict:

                    actor_state_dict[actor_id] = {}

                # Update the states for the actor into the dictionary
                actor_state_dict[actor_id]["before_state"] = before_state
                actor_state_dict[actor_id]["after_state"] = after_state

            ### IMPORTANT: before_state and after_state has to be replaced by the actor's own states
            ### This is because in event_memory.json, the before_state and after_state stored in an event is about the target
            ### However the states stored in the event ACTION_SELECTED is about the actor so can be kept
                
            # Extra data to be written in if there IS a target in this event
            # No extra data has to be written for the ACTION_SELECTED event
            else: # Same as elif target_entity_id != None and event_type != "ACTION_SELECTED":

                # Write a base format for the target_dict, and change the data in each of the selection branch
                target_dict = {
                    "time": time,
                    "event_type": event_type,
                    "role_in_event": role_in_event,
                    "event_id": event_id,
                    "source_action_id": source_action_id,
                    "before_state": before_state,
                    "after_state": after_state,
                    "data": data,
                    "tags": tags
                }

                # First case: If the actor misses the target
                if event_type == "MISS":

                    # Set the role as target as not affected from any damage
                    role_in_event = "target"

                # Second case: If the actor attacks the target successfully
                elif event_type == "ATTACK":

                    # Set the role as being affected
                    role_in_event = "affected" # Since actual damage is dealt

                # Third case: If the actor destroyed the target
                elif event_type == "ENTITY_DESTROYED":

                    # Set the role as the entities' final state
                    role_in_event = "final_state"

                # Replace states for actor and write into the master_dict
                temp_dict["before_state"] = actor_state_dict[actor_id]["before_state"]
                temp_dict["after_state"] = actor_state_dict[actor_id]["after_state"]

                # Change the role for the target in the target_dict
                target_dict["role_in_event"] = role_in_event

                master_dict[target_entity_id]["history"].append(target_dict)

            # Write the data stored in temp_dict into the corresponding entities' history
            master_dict[actor_id]["history"].append(temp_dict)

        # If the scenario ends, record all states for the entities
        else:

            # Set role as final state as the scenario has ended
            role_in_event = "final_state"

            # An extra "end" is added to the start of variables to not mix variables up
            # Extract dictionary in order to obtain the final state for entities
            end_entity_dict = event["after_state"]["entities"]

            # Loop through the scenario end event and obtain final states for all entities
            for (end_entity_id, end_entity_data) in end_entity_dict.items():

                # Unique format for scenario end
                temp_dict = {
                    "time": time,
                    "event_type": event_type,
                    "role_in_event": role_in_event,
                    "event_id": event_id,
                    "source_action_id": source_action_id,
                    "final_state": {},
                    "tags": tags
                }

                # Extract final state for each entity
                final_state = end_entity_data["state"]
                temp_dict["final_state"] = final_state

                master_dict[end_entity_id]["history"].append(temp_dict)

    return master_dict

# Declare paths for future use
tactical_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json" # Used for initial states
event_path = REPO_ROOT / "output" / "event_memory.json" # Most data can be accessed here so is used more
result_path = REPO_ROOT / "output" / "result_package.json"

# Collect data from tactical_reference_001.json
tactical_dict: dict

with open(tactical_path, "r") as f_tac: # file pointer to tactical_ref... = f_tac

    tactical_dict = json.loads(f_tac.read())

# Extract a collection of entities as a list of dictionaries to start with
entity_list = tactical_dict["entities"]

# Extract value for max number of ticks in this model
max_ticks = tactical_dict["world_contract"]["time_model"]["max_ticks"]

# Collect data from event_memory.json
event_list: list

with open(event_path, "r") as f_eve: # file pointer to event_mem... = f_eve

    event_list = json.loads(f_eve.read())

# Put data into json format and output to entity_history.json
master_dict = write_history(entity_list, event_list)

# Open a file in the output folder to write data in
entity_path = REPO_ROOT / "output" / "entity_history.json"

with open(entity_path, "w") as f_ent: # file pointer to entity_his... = f_ent

    json.dump(master_dict, f_ent, indent=2)

# # Testing output
# for entity in master_dict.values():
#     print(entity)
#     print("==============================")

# for entity in actor_state_dict.values():
#     print(entity)
#     print("==============================")