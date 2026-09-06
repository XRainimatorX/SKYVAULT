"""Causal chain = which events each action produced."""

from typing import Any


def build_causal_chain(
    scenario_id: str,
    event_memory: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Causal chain = the events one action produced, grouped by that action.

    Important:
    This is a derived output. It reads event memory and never mutates it.

    Grouping is by source_action_id only. Events the engine did not resolve
    from an action, such as NO_ACTION and SCENARIO_END, carry no action id and
    are never forced into a chain.
    """
    # dictionary containing events sorted by source_action_id
    grouped_events: dict[str, list[dict[str, Any]]] = {}

    scenario_end = None

    # creating one list for each unique source_action_id in grouped_events dictionary
    for event in event_memory:

        if event["event_type"] == "SCENARIO_END":
            scenario_end = event
            continue

        source_action_id = event["source_action_id"]

        if source_action_id is None:
            continue

        if source_action_id not in grouped_events:
            grouped_events[source_action_id] = []

        grouped_events[source_action_id].append(event)

    # the dictionary that contains each chain of actions happened under
    # each source_action_id
    causal_chain: dict[str, Any] = {
        "scenario_id": scenario_id,
        "chains": [],
    }

    for source_action_id, events in grouped_events.items():
        # sort events in grouped_events by their time
        events.sort(key=lambda event: event["time"])

        # list of events happened under the same source_action_id sorted by time
        event_ids = []
        event_types = []

        # append event IDs and event types into the list above
        for event in events:

            event_ids.append(event["event_id"])

            # exclude action selected to be appended to event_type although its
            # event_id is remained kept
            if event["event_type"] != "ACTION_SELECTED":
                event_types.append(event["event_type"])

        # a dictionary containing the chain for each source_action_id
        chain = {
            "source_action_id": source_action_id,
            "events": event_ids,
            "event_types": event_types,
            "summary": f"Action {source_action_id} caused {' and '.join(event_types)}.",
        }

        # append the chains created to the chains list
        causal_chain["chains"].append(chain)

    # create a separate dictionary for scenario end to the causal chain
    if scenario_end is not None:
        causal_chain["scenario_end"] = {
            "event_id": scenario_end["event_id"],
            "event_type": scenario_end["event_type"],
            "summary": "Scenario ended.",
        }

    return causal_chain
