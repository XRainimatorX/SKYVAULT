from typing import Any


def build_entity_names(event_memory: list[dict[str, Any]]) -> dict[str, str]:
    """
    Entity names = entity_id to the human name that reads well in a timeline.

    Important:
    A name is only ever taken from the snapshot that entity_id belongs to.

    SCENARIO_END carries every entity at once, so it is read first; any entity
    missing from it is filled in from the snapshots events carry.
    """
    entity_names: dict[str, str] = {}

    for event in event_memory:

        if event["event_type"] != "SCENARIO_END":
            continue

        entities = event["after_state"].get("entities", {})

        for entity_id, entity in entities.items():
            entity_names[entity_id] = entity.get("name", entity_id)

    for event in event_memory:

        for state in (event["before_state"], event["after_state"]):

            entity_id = state.get("entity_id")

            if entity_id is None or entity_id in entity_names:
                continue

            entity_names[entity_id] = state.get("name", entity_id)

    return entity_names


# Define a function which writes a single event into sentence
# Parameter 1 takes in the current time
# Parameter 2 takes in the dictionary which stores the names of entities
# corresponding to their id
# Parameter 3 takes the whole list of events carried out in the same tick
# Returns a whole list of sentences to be written in the text file
def write_event(
    time: int,
    entity_names: dict[str, str],
    events_in_same_tick: list[dict[str, Any]],
) -> list[str]:

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

    # Loop through the events in the same tick
    for event in events_in_same_tick:

        sentence = ""

        # Every branch resolves its own actor and target from the event itself,
        # so no sentence can inherit a name left over from an earlier event
        actor_name = entity_names.get(event["actor_id"], event["actor_id"])
        target_name = entity_names.get(
            event["target_entity_id"],
            event["target_entity_id"],
        )

        # Action 1: ACTION_SELECTED
        if event["event_type"] == "ACTION_SELECTED":

            # Extract the action_type selected by the actor and write into sentences
            event_type = event["data"]["action_type"].upper()

            # Specified sentence formatting for ATTACK at current stage
            if event_type == "ATTACK":

                sentence = (
                    f"\n- {actor_name} selected {event_type} "
                    f"against {target_name}"
                )

            else :

                sentence = f"\n- {actor_name} selected {event_type}"

            sentence_list.append(sentence)

        # Action 2: ACTION_REJECTED
        elif event["event_type"] == "ACTION_REJECTED":

            # Both the attempted action and why it was refused are on the event
            attempted = event["data"].get("action_type", "action").upper()
            reject_reason = event["data"].get("reason", "no reason recorded")

            # Write sentence for ACTION_REJECTED
            sentence = (
                f"- {actor_name} attempted {attempted} "
                f"but was rejected: {reject_reason}"
            )
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
            sentence = (
                f"- {actor_name} successfully attacked {target_name}: "
                f"HP {hp_before} -> {hp_after} (damage = {damage})"
            )
            sentence_list.append(sentence)

        # Action 5: MISS
        elif event["event_type"] == "MISS":

            # Write a specified sentence for MISS
            sentence = f"- {actor_name} attacked {target_name} but missed."
            sentence_list.append(sentence)

        # Action 6: ENTITY_DESTROYED
        elif event["event_type"] == "ENTITY_DESTROYED":

            # Extract the value for faction from the destroyed entity
            faction = event["after_state"].get("faction", "unknown")

            # Write sentence for ENTITY_DESTROYED
            sentence = (
                f"- {target_name} in the {faction} faction "
                f"was destroyed by {actor_name}"
            )
            sentence_list.append(sentence)

        # Action 7: NO_ACTION
        elif event["event_type"] == "NO_ACTION":

            # The policy records why it declined to act
            no_action_reason = event["data"].get("reason", "no reason recorded")

            # Write sentence for NO_ACTION
            sentence = f"- {actor_name} took no action: {no_action_reason}"
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


def render_timeline(
    scenario_id: str,
    event_memory: list[dict[str, Any]],
) -> str:
    """
    Timeline = event memory retold as something a person can read start to end.

    Important:
    This is a derived output. It reads event memory and never mutates it.

    It returns the finished text rather than writing it, so importing this
    module has no side effects and the caller decides where the text goes.
    """
    # The header to be written in first
    header = f"SKYVAULT Tactical Reference Timeline\nScenario: {scenario_id}\n"

    entity_names = build_entity_names(event_memory)

    # Extract all the data, separating them by each tick
    # Each item in the timeline_list is a list of dictionaries containing events
    # that happened in the very same tick
    # E.g., timeline_list[1] contains the events for every actors at "time" = 1
    timeline_list: list[list[dict[str, Any]]] = [[]] # Empty list so it starts at 1

    # Figure out the number of ticks in the whole run
    # Done in a general way so it is flexible to any changes in the output
    time_list = [event["time"] for event in event_memory]

    no_of_ticks = max(time_list) if time_list else 0

    # Loop through the whole event_memory, extracting lists of events for each tick
    for count in range(no_of_ticks):

        current_time = count + 1 # count starts from 0 so add 1 to match to time

        timeline_list.append(
            [event for event in event_memory if event["time"] == current_time]
        )

    lines = [header]

    # Loop through the timeline_list and collect the sentences for every tick
    for time, events_in_same_tick in enumerate(timeline_list):

        # For time = 0 the sentence list is empty so skip
        if time == 0:
            continue

        for sentence in write_event(time, entity_names, events_in_same_tick):
            lines.append(sentence + "\n")

    return "".join(lines)
