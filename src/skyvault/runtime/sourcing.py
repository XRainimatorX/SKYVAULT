"""Event sourcing = rebuild the world at any time from event memory alone."""

import copy
from typing import Any


def rebuild_world(
    start_state: dict[str, Any],
    event_memory: list[dict[str, Any]],
    at_time: int | None = None,
) -> dict[str, Any]:
    """
    The world snapshot at at_time, rebuilt from a starting snapshot and events.

    Important:
    This is a pure function. It reads plain dicts, imports nothing from the
    rest of the project and never mutates its inputs.

    start_state is a snapshot taken at the end of its tick: the initial world
    state, or one kept by a SnapshotStore. Only events after that tick are
    applied, so a rebuild from a mid-run snapshot and a rebuild from time zero
    arrive at the same world.

    Each event is applied by its after_state:

    entity event        after_state carries entity_id; it replaces that entity
    RESOURCE_CHANGED    after_state is {resource_id, amount}; it sets the stock
    anything else       nothing to apply (SCENARIO_END holds a whole-world
                        summary, not a change)

    Applying an after_state is idempotent, so replaying an event the starting
    snapshot already contains would do no harm; skipping them is only speed.

    at_time None means "after the last event". The rebuilt tick is at_time, or
    the time of the last event applied.
    """
    world = copy.deepcopy(start_state)
    world.setdefault("resources", {})
    start_tick = world["tick"]
    tick = start_tick

    for event in event_memory:
        time = event["time"]

        if time <= start_tick:
            continue
        if at_time is not None and time > at_time:
            break

        tick = time
        after_state = event["after_state"]
        if event["event_type"] == "RESOURCE_CHANGED":
            world["resources"][after_state["resource_id"]] = after_state["amount"]
        elif "entity_id" in after_state:
            world["entities"][after_state["entity_id"]] = copy.deepcopy(after_state)

    world["tick"] = at_time if at_time is not None else tick
    return world
