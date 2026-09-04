import copy
from typing import Any


def build_record(
    time: int,
    event_type: str,
    role_in_event: str,
    event_id: str | None = None,
    source_action_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    History record = one line in one entity's life story.

    Important:
    Every record carries the same nine keys, whatever produced it.

    INITIAL_STATE and SCENARIO_END have no originating event, so they keep the
    shape and leave the event fields empty rather than dropping them.
    """
    return {
        "time": time,
        "event_type": event_type,
        "role_in_event": role_in_event,
        "event_id": event_id,
        "source_action_id": source_action_id,
        "before_state": before_state or {},
        "after_state": after_state or {},
        "data": data or {},
        "tags": list(tags or []),
    }


# Define a function to collect the history of every entity
# Parameter 1 takes in the world state the run started from
# Parameter 2 takes in the list of events from event memory
def build_entity_history(
    initial_world_state: dict[str, Any],
    event_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Entity history = every event each entity took part in, in order.

    Important:
    This is a derived output. It reads event memory and never mutates it.

    An entity is recorded when it is the actor, when it is the target, and when
    it appears in affected_entities, so nothing that touched it is missing.

    Everything comes from the result package, never from the scenario file, so
    the history can only ever show what the run actually recorded.
    """
    # Write all data into this master dictionary
    master_dict: dict[str, Any] = {}

    # A dictionary set up for saving down states of actors for writing data correctly
    actor_state_dict: dict[str, dict[str, Any]] = {}

    # Initiate the master dictionary by setting up a format
    for entity in initial_world_state["entities"].values():

        # Initial data: 1. entity_id 2. name 3. faction 4. history
        entity_id = entity["entity_id"]

        # Start with making a key from each entity_id, then basic details
        master_dict[entity_id] = {
            "entity_id": entity_id,
            "name": entity["name"],
            "faction": entity["faction"],
            "history": [], # A huge list of events for each entity
        }

        # Finally adds in the initial state for each entity
        initial_state = copy.deepcopy(entity.get("state", {}))

        master_dict[entity_id]["history"].append(
            build_record(
                time=0,
                event_type="INITIAL_STATE",
                role_in_event="initial_state",
                after_state=initial_state,
            )
        )

    # Loop through the event_list to write data into the master dict
    for event in event_list:

        time = event["time"]
        event_type = event["event_type"]

        # Data to be extracted regardless of the ending of a scenario
        event_id = event["event_id"]
        source_action_id = event["source_action_id"]
        tags = event["tags"]

        # Tracks who already has a record for this event, so the affected pass
        # below never files a second copy of the same event
        recorded: set[str] = set()

        # If the scenario ends, record all states for the entities
        if event_type == "SCENARIO_END":

            # Extract dictionary in order to obtain the final state for entities
            end_entity_dict = event["after_state"]["entities"]

            # Loop through the scenario end event and obtain final states
            # for all entities
            for (end_entity_id, end_entity_data) in end_entity_dict.items():

                if end_entity_id not in master_dict:
                    continue

                final_state = copy.deepcopy(end_entity_data.get("state", {}))

                record = build_record(
                    time=time,
                    event_type=event_type,
                    role_in_event="final_state",
                    event_id=event_id,
                    source_action_id=source_action_id,
                    after_state=final_state,
                    tags=tags,
                )

                record["final_state"] = final_state

                master_dict[end_entity_id]["history"].append(record)
                recorded.add(end_entity_id)

            continue

        # Data to be extracted regardless of the presence of a target
        actor_id = event["actor_id"]
        target_entity_id = event["target_entity_id"]
        before_state = event["before_state"]
        after_state = event["after_state"]
        data = event["data"]

        # Default value for roles as the actor
        role_in_event = "actor"

        # If there isn't a target in this event or if event_type == "ACTION_SELECTED"
        # Since both of the states are correct about the actor
        if target_entity_id is None or event_type == "ACTION_SELECTED":

            # Save down the states of the actor only when there is no target
            actor_state_dict[actor_id] = {
                "before_state": before_state,
                "after_state": after_state,
            }

            actor_before = before_state
            actor_after = after_state

        # IMPORTANT: before_state and after_state has to be replaced by the actor's
        # own states. This is because in event memory, the before_state and
        # after_state stored in an event with a target is about the target.
        # The states stored in ACTION_SELECTED are about the actor so can be kept.
        else:

            # First case: If the actor misses the target
            if event_type == "MISS":

                # Set the role as target as not affected from any damage
                target_role = "target"

            # Second case: If the actor attacks the target successfully
            elif event_type == "ATTACK":

                # Set the role as being affected
                target_role = "affected" # Since actual damage is dealt

            # Third case: If the actor destroyed the target
            elif event_type == "ENTITY_DESTROYED":

                # Set the role as the entities' final state
                target_role = "final_state"

            else:

                target_role = "target"

            if target_entity_id in master_dict:

                master_dict[target_entity_id]["history"].append(
                    build_record(
                        time=time,
                        event_type=event_type,
                        role_in_event=target_role,
                        event_id=event_id,
                        source_action_id=source_action_id,
                        before_state=before_state,
                        after_state=after_state,
                        data=data,
                        tags=tags,
                    )
                )

                recorded.add(target_entity_id)

            # Fall back to the event's own states when the actor has no cached
            # snapshot yet, so a missing ACTION_SELECTED can never raise here
            cached = actor_state_dict.get(actor_id, {})

            actor_before = cached.get("before_state", before_state)
            actor_after = cached.get("after_state", after_state)

        # Write the actor's own record into its history
        if actor_id in master_dict:

            master_dict[actor_id]["history"].append(
                build_record(
                    time=time,
                    event_type=event_type,
                    role_in_event=role_in_event,
                    event_id=event_id,
                    source_action_id=source_action_id,
                    before_state=actor_before,
                    after_state=actor_after,
                    data=data,
                    tags=tags,
                )
            )

            recorded.add(actor_id)

        # Anyone named in affected_entities who has no record for this event yet
        for affected_id in event["affected_entities"]:

            if affected_id in recorded or affected_id not in master_dict:
                continue

            master_dict[affected_id]["history"].append(
                build_record(
                    time=time,
                    event_type=event_type,
                    role_in_event="affected",
                    event_id=event_id,
                    source_action_id=source_action_id,
                    before_state=before_state,
                    after_state=after_state,
                    data=data,
                    tags=tags,
                )
            )

            recorded.add(affected_id)

    return master_dict
