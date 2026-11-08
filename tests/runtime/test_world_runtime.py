"""Phase 2 acceptance: create a world, place entities, advance time, update
state, record events — on grid, graph and network worlds alike."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_event, validate_scenario
from skyvault.entity import Entity
from skyvault.runtime import (
    EntityRegistry,
    EventDrivenClock,
    GraphSpace,
    GridSpace,
    NetworkSpace,
    PhaseClock,
    ResourceState,
    RuleSet,
    TickClock,
)
from skyvault.runtime.world import create_world, entity_from_record
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return validate_scenario(json.load(file))


def make_entity(entity_id: str, hp: int = 10) -> Entity:
    return Entity(
        entity_id=entity_id,
        name=entity_id,
        entity_type="unit",
        faction="BLUE",
        position="A",
        state={"hp": hp, "status": "active"},
        capabilities={},
        tags=[],
    )


# ── acceptance 1: create a world from its contract ───────────────────────────


def test_reference_scenario_builds_a_grid_world_on_a_tick_clock():
    world = create_world(load_scenario(REFERENCE_SCENARIO))

    assert isinstance(world.space, GridSpace)
    assert (world.space.width, world.space.height) == (10, 10)
    assert isinstance(world.clock, TickClock)
    assert world.tick == 0
    assert world.resources.snapshot() == {}
    assert len(world.rules) == 0


def test_graph_scenario_builds_a_graph_world_on_an_event_driven_clock():
    world = create_world(fixture("scenario_graph"))

    assert isinstance(world.space, GraphSpace)
    assert not isinstance(world.space, NetworkSpace)
    assert isinstance(world.clock, EventDrivenClock)
    assert world.space.distance("A", "D") == 3
    assert world.space.distance("A", "F") == float("inf")
    assert world.resources.snapshot() == {"fuel": 100.0, "supply": 20.0}
    assert world.rules.require("max_convoy_size") == 3


def test_network_scenario_builds_a_weighted_world_on_a_phase_clock():
    world = create_world(fixture("scenario_network"))

    assert isinstance(world.space, NetworkSpace)
    assert isinstance(world.clock, PhaseClock)
    # depot -> north -> city costs 4 + 3, cheaper than the direct road of 10
    assert world.space.distance("depot", "city") == 7


def test_snapshot_records_the_space_type_and_resources():
    snapshot = create_world(fixture("scenario_network")).snapshot()

    assert snapshot["space"]["type"] == "network"
    assert snapshot["resources"] == {"supply": 50.0}


# ── acceptance 2: place entities ─────────────────────────────────────────────


def test_graph_entities_stand_on_node_ids():
    world = create_world(fixture("scenario_graph"))

    assert world.get_entity("convoy_1").position == "A"
    assert world.get_entity("depot_1").position == "C"
    assert world.is_occupied("C")
    assert not world.is_occupied("B")


def test_grid_positions_become_tuples_and_node_ids_stay_strings():
    grid = entity_from_record(
        {"entity_id": "g", "name": "g", "entity_type": "u", "position": [2, 3]}
    )
    node = entity_from_record(
        {"entity_id": "n", "name": "n", "entity_type": "u", "position": "depot"}
    )

    assert grid.position == (2, 3)
    assert node.position == "depot"
    assert node.snapshot()["position"] == "depot"


def test_create_world_refuses_an_entity_outside_the_space():
    scenario = fixture("scenario_graph")
    scenario["entities"][0]["position"] = "Z"

    with pytest.raises(ValueError, match="outside the world's space"):
        create_world(scenario)


def test_registry_refuses_a_duplicate_id():
    registry = EntityRegistry([make_entity("u1")])

    with pytest.raises(ValueError, match="duplicate entity_id"):
        registry.add(make_entity("u1"))


def test_registry_raises_for_an_unknown_id():
    with pytest.raises(KeyError, match="Unknown entity_id: ghost"):
        EntityRegistry().require("ghost")


def test_registry_keeps_destroyed_entities_but_lists_only_the_living():
    alive, dead = make_entity("alive"), make_entity("dead", hp=0)
    dead.state["status"] = "destroyed"
    registry = EntityRegistry([alive, dead])

    assert set(registry) == {"alive", "dead"}
    assert registry.active() == [alive]


# ── acceptance 3: advance time ───────────────────────────────────────────────


def test_world_tick_follows_a_phase_clock():
    world = create_world(fixture("scenario_network"))

    for _ in range(3):
        world.advance_time()

    # phase_length 6 in hours: each step is one six-hour phase
    assert world.tick == 18
    assert world.clock.phase == 3  # type: ignore[attr-defined]


def test_world_time_jumps_to_the_next_scheduled_happening():
    world = create_world(fixture("scenario_graph"))
    world.clock.schedule(5, "convoy_departs")  # type: ignore[attr-defined]
    world.clock.schedule(12, "convoy_arrives")  # type: ignore[attr-defined]

    assert world.advance_time() == 5
    assert world.clock.due() == ["convoy_departs"]  # type: ignore[attr-defined]
    assert world.advance_time() == 12


# ── acceptance 4 and 5: update state and record the event ───────────────────


def test_resource_change_updates_the_stock_and_records_an_event():
    world = create_world(fixture("scenario_graph"))

    event = world.change_resource("fuel", -30, actor_id="convoy_1")

    assert world.resources.amount("fuel") == 70.0
    assert world.event_memory == [event]
    recorded = event.to_dict()
    validate_event(recorded)
    assert recorded["event_type"] == "RESOURCE_CHANGED"
    assert recorded["affected"]["resources"] == ["fuel"]
    assert recorded["before_state"] == {"resource_id": "fuel", "amount": 100.0}
    assert recorded["after_state"] == {"resource_id": "fuel", "amount": 70.0}
    assert recorded["evaluation_relevance"]["affects_cost"] is True
    assert recorded["data"]["delta"] == -30


def test_a_resource_never_goes_below_zero_and_nothing_is_recorded():
    world = create_world(fixture("scenario_graph"))

    with pytest.raises(ValueError, match="cannot apply"):
        world.change_resource("supply", -21)

    assert world.resources.amount("supply") == 20.0
    assert world.event_memory == []


def test_an_unknown_resource_is_refused():
    with pytest.raises(KeyError, match="Unknown resource: water"):
        ResourceState({"fuel": 1}).change("water", 1)


def test_a_resource_cannot_start_negative():
    with pytest.raises(ValueError, match="cannot start negative"):
        ResourceState({"fuel": -1})


def test_resource_snapshot_is_a_copy():
    resources = ResourceState({"fuel": 5})
    snapshot = resources.snapshot()
    resources.change("fuel", -5)

    assert snapshot == {"fuel": 5.0}
    assert "fuel" in resources


def test_entity_state_change_is_recorded_with_full_snapshots():
    world = create_world(fixture("scenario_graph"))
    event = world.update_entity_state("convoy_1", {"status": "loading"})

    assert world.get_entity("convoy_1").state["status"] == "loading"
    recorded = event.to_dict()
    validate_event(recorded)
    assert recorded["event_type"] == "ENTITY_STATE_CHANGED"
    assert recorded["before_state"]["state"]["status"] == "active"
    assert recorded["after_state"]["state"]["status"] == "loading"
    assert recorded["after_state"]["position"] == "A"
    assert recorded["affected"]["entities"] == ["convoy_1"]


def test_rule_set_is_read_only_and_raises_for_a_missing_rule():
    rules = RuleSet({"max_convoy_size": 3})

    assert dict(rules) == {"max_convoy_size": 3}
    assert rules.as_dict() == {"max_convoy_size": 3}
    with pytest.raises(KeyError, match="Missing rule: speed"):
        rules.require("speed")
    with pytest.raises(TypeError):
        rules["speed"] = 1  # type: ignore[index]


def test_world_snapshot_still_validates_inside_a_result_package():
    from skyvault.engine import SkyVaultTacticalReferenceEngine

    package = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO)).run()

    assert package["initial_world_state"]["space"]["type"] == "grid"
    assert package["final_world_state"]["resources"] == {}
    assert package["evaluation_result"]["winner_or_result"] == "RED_survived"
    assert package["evaluation_result"]["event_count"] == 97


def test_tactical_engine_refuses_a_world_it_cannot_run():
    from skyvault.engine import SkyVaultTacticalReferenceEngine

    with pytest.raises(ValueError, match="grid"):
        SkyVaultTacticalReferenceEngine(fixture("scenario_graph"))


def test_a_recorded_event_keeps_node_id_locations_whole():
    world = create_world(fixture("scenario_graph"))

    event = world.mutate_entity(
        "convoy_1",
        {"position": "B"},
        "MOVE",
        affected_locations=["A", "B"],
    )

    assert event.to_dict()["affected"]["locations"] == ["A", "B"]
    assert event.to_dict()["after_state"]["position"] == "B"
