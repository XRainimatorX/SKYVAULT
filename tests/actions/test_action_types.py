"""The ten action types, each accepted and refused, on the logistics fixture.

Map: depot — junction — front — outpost, one hop apart.
truck_1 (BLUE, depot), squad_1 (BLUE, junction, hp 8/20), reserve_1 (BLUE,
off the map, in reserve), scout_red (RED, outpost). Stock: fuel 50,
spare_parts 4. rule_set: repair costs 1 spare_parts.
"""

import copy
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.action import Action, ActionTarget
from skyvault.actions import CORE_HANDLERS, ActionContext, ActionResolver
from skyvault.contracts import validate_scenario
from skyvault.runtime import rebuild_world
from skyvault.runtime.world import create_world


def world():
    with (FIXTURES / "scenario_logistics.json").open(encoding="utf-8") as file:
        return create_world(validate_scenario(json.load(file)))


def resolver() -> ActionResolver:
    return ActionResolver(CORE_HANDLERS, ActionContext(random.Random(0), "test"))


def act(actor, action_type, entity=None, location=None, **fields) -> Action:
    return Action(
        f"action_{action_type}",
        actor,
        action_type,
        ActionTarget(entity_id=entity, location=location),
        **fields,
    )


def run(state, action):
    consequence = resolver().execute(state, action)
    return consequence, [event.to_dict() for event in state.event_memory]


ACCEPTED = [
    act("squad_1", "move", location="front"),
    act("truck_1", "observe", entity="squad_1"),
    act("truck_1", "scan"),
    act("squad_1", "wait"),
    act("truck_1", "repair", entity="squad_1"),
    act("truck_1", "supply", entity="squad_1", required_resources={"fuel": 10}),
    act("squad_1", "deploy", entity="reserve_1", location="front"),
    act("squad_1", "withdraw"),
    act("truck_1", "communicate", entity="squad_1", metadata={"message": "hold"}),
]


def test_all_ten_action_types_have_a_core_handler():
    assert sorted(CORE_HANDLERS) == sorted(
        [
            "move",
            "attack",
            "observe",
            "wait",
            "repair",
            "supply",
            "deploy",
            "withdraw",
            "scan",
            "communicate",
        ]
    )


@pytest.mark.parametrize("action", ACCEPTED, ids=lambda action: action.action_type)
def test_resolving_reads_the_world_and_changes_nothing(action):
    state = world()
    before = copy.deepcopy(state.snapshot())
    handler = CORE_HANDLERS[action.action_type]
    context = ActionContext(random.Random(0))

    assert handler.validate(state, action, context).valid
    handler.resolve(state, action, context)

    assert state.snapshot() == before
    assert state.event_memory == []


@pytest.mark.parametrize("action", ACCEPTED, ids=lambda action: action.action_type)
def test_every_event_is_one_effect_and_names_the_action(action):
    state = world()

    consequence, events = run(state, action)

    assert consequence.accepted
    assert len(events) == len(consequence.effects) + len(consequence.chain_reactions)
    assert {event["source"]["action_id"] for event in events} == {action.action_id}
    assert {event["source"]["actor_id"] for event in events} == {action.actor_id}


def test_a_day_of_actions_rebuilds_from_its_events_alone():
    state = world()
    initial = state.snapshot()
    day = [
        act("truck_1", "observe", entity="squad_1"),
        act("truck_1", "scan"),
        act("squad_1", "wait"),
        act("truck_1", "repair", entity="squad_1"),
        act("truck_1", "supply", entity="squad_1", required_resources={"fuel": 10}),
        act("truck_1", "communicate", entity="squad_1", intent="hold"),
        act("squad_1", "deploy", entity="reserve_1", location="front"),
        act("squad_1", "withdraw"),
        act("reserve_1", "move", location="junction"),
    ]

    for action in day:
        consequence = resolver().execute(state, action)
        assert consequence.accepted, (action.action_type, consequence.reason)

    events = [event.to_dict() for event in state.event_memory]
    assert len(events) == 11  # nine actions, two of them charged a resource
    assert rebuild_world(initial, events) == state.snapshot()


# ── move ─────────────────────────────────────────────────────────────────────


def test_move_steps_along_one_link():
    state = world()

    _, [event] = run(state, act("squad_1", "move", location="front"))

    assert state.get_entity("squad_1").position == "front"
    assert event["data"] == {"from": "junction", "to": "front"}


@pytest.mark.parametrize(
    ("location", "reason"),
    [
        ("front", "Move target out of range: distance=2, range=1"),
        ("nowhere", "Move target outside world boundary"),
        ("junction", "Move target occupied"),
    ],
)
def test_move_refusals(location, reason):
    assert (
        resolver().execute(world(), act("truck_1", "move", location=location)).reason
        == reason
    )


# ── observe ──────────────────────────────────────────────────────────────────


def test_observe_records_what_was_seen_and_changes_nothing():
    state = world()

    _, [event] = run(state, act("truck_1", "observe", entity="squad_1"))

    assert event["event_type"] == "OBSERVE"
    assert event["data"]["observed_state"]["hp"] == 8
    assert event["data"]["distance"] == 1
    assert event["before_state"] == event["after_state"]


@pytest.mark.parametrize(
    ("entity", "reason"),
    [
        ("scout_red", "Observe target out of range: distance=3, range=2"),
        ("reserve_1", "Actor or target has no position"),
        (None, "Observe action missing target_entity_id"),
    ],
)
def test_observe_refusals(entity, reason):
    assert (
        resolver().execute(world(), act("truck_1", "observe", entity=entity)).reason
        == reason
    )


# ── scan ─────────────────────────────────────────────────────────────────────


def test_scan_lists_living_entities_within_range():
    state = world()

    _, [event] = run(state, act("truck_1", "scan"))

    assert event["data"] == {"detected": ["squad_1"], "scan_range": 1.0}
    assert event["affected"]["entities"] == ["truck_1", "squad_1"]


def test_scan_needs_a_position():
    state = world()
    state.get_entity("reserve_1").state["status"] = "active"

    assert (
        resolver().execute(state, act("reserve_1", "scan")).reason
        == "Actor has no position"
    )


# ── wait ─────────────────────────────────────────────────────────────────────


def test_wait_records_one_event_and_changes_nothing():
    state = world()

    _, [event] = run(state, act("squad_1", "wait"))

    assert event["event_type"] == "WAIT"
    assert event["before_state"] == event["after_state"]


def test_an_entity_in_reserve_cannot_act():
    assert (
        resolver().execute(world(), act("reserve_1", "wait")).reason
        == "Actor is not active"
    )


# ── repair ───────────────────────────────────────────────────────────────────


def test_repair_spends_a_spare_part_then_restores_hp():
    state = world()

    _, events = run(state, act("truck_1", "repair", entity="squad_1"))

    assert [event["event_type"] for event in events] == ["RESOURCE_CHANGED", "REPAIR"]
    assert events[0]["after_state"] == {"resource_id": "spare_parts", "amount": 3.0}
    assert events[1]["data"] == {
        "hp_before": 8,
        "hp_after": 13,
        "repaired_by": "truck_1",
    }
    assert state.get_entity("squad_1").state["hp"] == 13


def test_repair_stops_at_max_hp():
    state = world()
    state.get_entity("squad_1").state["hp"] = 18

    run(state, act("truck_1", "repair", entity="squad_1"))

    assert state.get_entity("squad_1").state["hp"] == 20


@pytest.mark.parametrize(
    ("actor", "entity", "setup", "reason"),
    [
        ("squad_1", "squad_1", None, "Actor cannot repair"),
        (
            "truck_1",
            "scout_red",
            None,
            "Repair target out of range: distance=3, range=1",
        ),
        ("truck_1", None, None, "Repair target has no hp"),
        ("truck_1", "squad_1", ("hp", 20), "Repair target already at full health"),
        ("truck_1", "squad_1", ("status", "destroyed"), "Repair target is not active"),
    ],
)
def test_repair_refusals(actor, entity, setup, reason):
    state = world()
    if setup:
        state.get_entity("squad_1").state[setup[0]] = setup[1]

    consequence = resolver().execute(state, act(actor, "repair", entity=entity))

    assert consequence.reason == reason
    assert state.event_memory == []


def test_repair_without_spare_parts_is_refused():
    state = world()
    state.resources.change("spare_parts", -4)

    consequence = resolver().execute(state, act("truck_1", "repair", entity="squad_1"))

    assert consequence.reason == "Insufficient spare_parts: have 0.0, need 1.0"
    assert state.get_entity("squad_1").state["hp"] == 8


# ── supply ───────────────────────────────────────────────────────────────────


def test_supply_moves_stock_from_the_world_to_the_unit():
    state = world()

    consequence, events = run(
        state,
        act("truck_1", "supply", entity="squad_1", required_resources={"fuel": 10}),
    )

    assert [event["event_type"] for event in events] == ["RESOURCE_CHANGED", "SUPPLY"]
    assert state.resources.amount("fuel") == 40.0
    assert state.get_entity("squad_1").state["fuel"] == 10.0
    assert consequence.to_dict()["secondary_effects"]["logistical_changes"] == [
        {"entity_id": "squad_1", "delivered": {"fuel": 10.0}}
    ]


@pytest.mark.parametrize(
    ("entity", "resources", "reason"),
    [
        ("squad_1", {}, "Supply action carries no resources"),
        ("scout_red", {"fuel": 1}, "Supply target out of range: distance=3, range=1"),
        (None, {"fuel": 1}, "Supply action missing target_entity_id"),
        ("squad_1", {"fuel": 99}, "Insufficient fuel: have 50.0, need 99.0"),
    ],
)
def test_supply_refusals(entity, resources, reason):
    state = world()

    consequence = resolver().execute(
        state, act("truck_1", "supply", entity=entity, required_resources=resources)
    )

    assert consequence.reason == reason
    assert state.resources.amount("fuel") == 50.0


# ── deploy ───────────────────────────────────────────────────────────────────


def test_deploy_puts_a_reserve_unit_on_the_map():
    state = world()

    _, [event] = run(
        state, act("squad_1", "deploy", entity="reserve_1", location="front")
    )

    unit = state.get_entity("reserve_1")
    assert unit.position == "front"
    assert unit.is_active()
    assert event["before_state"]["position"] is None
    assert event["data"] == {"to": "front"}


@pytest.mark.parametrize(
    ("actor", "entity", "location", "reason"),
    [
        ("squad_1", "scout_red", "front", "Deploy target is not in reserve"),
        ("squad_1", "reserve_1", "depot", "Deploy location occupied"),
        ("squad_1", "reserve_1", "nowhere", "Deploy location outside world boundary"),
        (
            "truck_1",
            "reserve_1",
            "front",
            "Deploy location out of range: distance=2, range=1",
        ),
        ("squad_1", "reserve_1", None, "Deploy action missing target location"),
    ],
)
def test_deploy_refusals(actor, entity, location, reason):
    action = act(actor, "deploy", entity=entity, location=location)

    assert resolver().execute(world(), action).reason == reason


def test_deploying_the_other_sides_reserve_is_refused():
    state = world()
    state.get_entity("reserve_1").faction = "RED"

    action = act("squad_1", "deploy", entity="reserve_1", location="front")

    assert resolver().execute(state, action).reason == (
        "Deploy target belongs to another faction"
    )


# ── withdraw ─────────────────────────────────────────────────────────────────


def test_withdraw_takes_the_unit_off_the_map_but_keeps_it():
    state = world()

    _, [event] = run(state, act("squad_1", "withdraw"))

    unit = state.get_entity("squad_1")
    assert unit.position is None
    assert unit.state["status"] == "withdrawn"
    assert "squad_1" in state.entities
    assert unit not in state.active_entities()
    assert event["data"] == {"from": "junction"}


@pytest.mark.parametrize(
    ("entity", "reason"),
    [
        ("scout_red", "Withdraw target belongs to another faction"),
        ("reserve_1", "Withdraw target is not active"),
    ],
)
def test_withdraw_refusals(entity, reason):
    assert (
        resolver().execute(world(), act("truck_1", "withdraw", entity=entity)).reason
        == reason
    )


# ── communicate ──────────────────────────────────────────────────────────────


def test_communicate_leaves_the_message_with_the_recipient():
    state = world()

    run(
        state,
        act("truck_1", "communicate", entity="squad_1", metadata={"message": "hold"}),
    )

    assert state.get_entity("squad_1").state["last_message"] == "hold"
    assert state.get_entity("squad_1").state["last_message_from"] == "truck_1"


def test_communicate_falls_back_to_the_intent():
    state = world()

    run(state, act("truck_1", "communicate", entity="squad_1", intent="regroup"))

    assert state.get_entity("squad_1").state["last_message"] == "regroup"


def test_without_comm_range_distance_does_not_matter():
    state = world()

    consequence = resolver().execute(
        state, act("squad_1", "communicate", entity="scout_red")
    )

    assert consequence.accepted


@pytest.mark.parametrize(
    ("entity", "comm_range", "reason"),
    [
        ("scout_red", 2, "Communicate target out of range: distance=3, range=2"),
        ("reserve_1", 3, "Communicate target is not active"),
        (None, 3, "Communicate action missing target_entity_id"),
    ],
)
def test_communicate_refusals(entity, comm_range, reason):
    state = world()
    state.get_entity("truck_1").capabilities["comm_range"] = comm_range

    assert (
        resolver().execute(state, act("truck_1", "communicate", entity=entity)).reason
        == reason
    )
