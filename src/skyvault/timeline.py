# # Output a text file listing the timeline of events for reading purposes
from pathlib import Path
import json

# Define a function which writes a single event into sentence
# Parameter 1 takes in the current time
# Parameter 2 takes in the dictionary which stores the names of actors corresponding to their id
# Parameter 3 takes the whole list of events carried out in the same tick
# Returns a whole list of sentences to be written in the text file
def write_event(time, actor_dict, events_in_same_tick):

    # A list to collect sentences generated
    sentence_list = []

    # Write in first sentence to start a tick
    tick_header = f"\nTick {time}" # \n in front to start an extra new line
    sentence_list.append(tick_header)

    # Event types:
    # 1. ACTION_SELECTED
    # 2. ACTION_REJECTED
    # 3. MOVE
    # 4. ATTACK
    # 5. MISS
    # 6. ENTITY_DESTROYED
    # 7. NO_ACTION
    # 8. SCENARIO_END

    # # Declare the required variables for writing sentences (Optional)

    # For ACTION_SELECTED section
    actor_id = ""
    actor_name = ""
    event_type = "" # Store the uppercase version of the action selected by the actor

    # For ACTION_REJECTED section
    reject_reason = ""

    # For MOVE section
    pos_before = () # The position of the actor before
    pos_after = () # The position of the actor after

    # For ACTION_SELECTED section when the actor selected ATTACK
    target_id = "" # Record id of target for ATTACK and MISS
    target_name = ""

    # For ATTACK section
    hp_before = 0
    hp_after = 0
    damage = 0

    # For ENTITY_DESTROYED section
    faction = ""

    # For NO_ACTION section
    no_action_reason = ""

    # For SCENARIO_END section
    termination_reason = ""
    winner_or_result = ""
    event_count = 0
    destroyed_entities = 0

    # Loop through the events in the same tick
    for event in events_in_same_tick:

        sentence = ""
        
        # Action 1: ACTION_SELECTED
        if event["event_type"] == "ACTION_SELECTED":

            # Record the name of actor to write sentences
            actor_id = event["actor_id"]
            actor_name = actor_dict[actor_id]

            # Extract the action_type selected by the actor and write into sentences
            event_type = event["data"]["action_type"].upper()

            # Specified sentence formatting for ATTACK at current stage
            if event_type == "ATTACK":

                # Record the name of target that the actor chose
                target_id = event["target_entity_id"]
                target_name = actor_dict[target_id]

                sentence = f"\n- {actor_name} selected {event_type} against {target_name}"

            else :

                sentence = f"\n- {actor_name} selected {event_type}"

            sentence_list.append(sentence)

        # Action 2: ACTION_REJECTED (Currently unavailable)
        elif event["event_type"] == "ACTION_REJECTED":

            # Currently unavailable so left blank
            reject_reason = ""

            # Write sentence for ACTION_REJECTED
            sentence = f"{actor_name} attempted {event_type} but was rejected: {reject_reason}"
            sentence_list.append(sentence)

        # Action 3: MOVE
        elif event["event_type"] == "MOVE":

            # Record positions before and after to write into sentence
            pos_before = tuple(event["data"]["from"])
            pos_after = tuple(event["data"]["to"])

            # Write sentence for MOVE
            sentence = f"- {actor_name} moved from {pos_before} to {pos_after}."
            sentence_list.append(sentence)

        # Action 4: ATTACK
        elif event["event_type"] == "ATTACK":

            hp_before = event["data"]["hp_before"]
            hp_after = event["data"]["hp_after"]
            damage = event["data"]["damage"]

            # Eliminate any negative hp
            if hp_after <= 0:
                
                hp_after = 0
                damage = hp_before - hp_after

            # Write sentence for ATTACK
            sentence = f"- {actor_name} successfully attacked {target_name}: HP {hp_before} -> {hp_after} (damage = {damage})"
            sentence_list.append(sentence)

        # Action 5: MISS
        elif event["event_type"] == "MISS":

            # Write a specified sentence for MISS
            sentence = f"- {actor_name} attacked {target_name} but missed."
            sentence_list.append(sentence)

        # Action 6: ENTITY_DESTROYED
        elif event["event_type"] == "ENTITY_DESTROYED":

            # Extract the value for faction from the destroyed entity
            faction = event["after_state"]["faction"] 

            # Write sentence for ENTITY_DESTROYED
            sentence = f"- {target_name} in the {faction} faction was destroyed by {actor_name}"
            sentence_list.append(sentence)

        # Action 7: NO_ACTION (Currently unavailable)
        elif event["event_type"] == "NO_ACTION":

            # Currently unavailable so left blank
            no_action_reason = ""

            # Write sentence for NO_ACTION
            sentence = f"{actor_name} took no action: {no_action_reason}"
            sentence_list.append(sentence)

        # Action 8: SCENARIO_END
        elif event["event_type"] == "SCENARIO_END":

            # Extract required values to write the sentence
            termination_reason = event["data"]["termination_reason"]
            winner_or_result = event["data"]["winner_or_result"]
            event_count = event["data"]["event_count"]
            destroyed_entities = event["data"]["destroyed_entities"]

            # Write sentences for SCENARIO_END
            sentence = f"\nScenario Ended: {termination_reason}"
            sentence_list.append(sentence)

            sentence = f"- Result: {winner_or_result}"
            sentence_list.append(sentence)

            sentence = f"- Number of events recorded: {event_count}"
            sentence_list.append(sentence)

            sentence = f"- Number of destroyed entities: {destroyed_entities}"
            sentence_list.append(sentence)

    return sentence_list

# Finds the absolute folder directory where this current script resides
REPO_ROOT = Path(__file__).resolve().parents[1] # Now parallel with src: so .. brings out to the whole file

# Safely joins paths independent of the terminal's current working directory
event_path = REPO_ROOT / ".." / "output" / "event_memory.json"

# # Open the event_memory file to read data
# event_path = Path("output/event_memory.json")

with open(event_path, "r") as f:

    # Extract event_memory as a list
    event_memory_list = json.loads(f.read()) 

# # Check length of list
# print(len(event_memory_list))

# Extract the scenario id when the scenario ends
scenario_id = ""

for event in event_memory_list:

    if event["event_type"] == "SCENARIO_END":

        scenario_id = event["after_state"]["scenario_id"]

# The header to be written in first
header = f"SKYVAULT Tactical Reference Timeline\nScenario: {scenario_id}\n"

# Extract all the data, separating them by each tick
# Each item in the timeline_list is a list of dictionaries containing events that happened in the very same tick
# E.g., timeline_list[1] contains the events for every actors at "time" = 1
timeline_list = [{}] # Add in an empty dict so it starts at 1

# Figure out the number of ticks in the whole run
# Done in a general way so it is flexible to any changes in the output
time_list = []

# Extract all the times in the whole list and look for the greatest number
for event in event_memory_list:
    time = event["time"]
    time_list.append(time)

no_of_ticks = max(time_list)
# print(time_list)

# Loop through the whole event_memory_list, extracting lists of events for each tick
for count in range(no_of_ticks):

    current_time = count + 1 # count starts from 0 so add 1 to match to time
    event_list = [] # Create a temporary list which can be written into the main list

    for event in event_memory_list:

        if event["time"] == current_time:

            event_list.append(event)

    timeline_list.append(event_list)

# print(timeline_list[1])

# Extract all the actor_id and its corresponding name and write it into a dictionary
actor_dict = {}

# Use the events in first tick since no one has started interact and slained yet
for event in timeline_list[1]:

    actor_id = event["actor_id"]
    actor_name = event["before_state"]["name"]

    if actor_id not in actor_dict:

        actor_dict[actor_id] = actor_name

# print(actor_dict)

# Writing section starts here

# Set up path to write data in
# Safely joins paths independent of the terminal's current working directory
timeline_path = REPO_ROOT / ".." / "output" / "timeline.txt"

# timeline_path = Path("output/timeline.txt")

# Open the textfile to write sentences into
with open(timeline_path, "w") as g:

    # First write in the header
    g.write(header)

    # Loop through the timeline_list and return lists of sentence to write into textfile
    for time, events_in_same_tick in enumerate(timeline_list):

        # Resets the list every time the sentences have been written into the textfile
        sentence_list = []

        # For time = 0 the sentence list is empty so skip
        if time != 0:

            sentence_list = write_event(time, actor_dict, events_in_same_tick)

        # Loop through the list that contains sentences for the same tick
        for sentence in sentence_list:

            g.write(sentence+"\n")