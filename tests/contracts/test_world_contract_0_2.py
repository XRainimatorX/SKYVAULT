"""The World Contract rules schema 0.2 brought in, still in force."""

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import (
    ContractError,
    validate_event,
    validate_scenario,
    validate_world_contract,
)


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def error_text(caught: pytest.ExceptionInfo) -> str:
    return " | ".join(caught.value.errors)


# ── versioning ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("version", ["0.1", "0.2"])
def test_a_scenario_written_for_an_older_schema_is_rejected(version):
    scenario = fixture("scenario_valid")
    scenario["schema_version"] = version

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "schema_version" in error_text(caught)


@pytest.mark.parametrize(
    "name",
    ["scenario_valid", "scenario_graph", "scenario_network", "scenario_logistics"],
)
def test_the_scenario_fixtures_validate_unchanged(name):
    scenario = fixture(name)

    assert validate_scenario(scenario) == scenario


# ── the four elements ADR 004 promised ───────────────────────────────────────


@pytest.mark.parametrize(
    "field", ["entity_model", "environment_state", "resource_state", "rule_set"]
)
def test_world_contract_without_a_phase_2_element_is_rejected(field):
    world = fixture("scenario_graph")["world_contract"]
    del world[field]

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert field in error_text(caught)


def test_empty_phase_2_elements_are_allowed():
    world = fixture("scenario_valid")["world_contract"]

    for field in ["entity_model", "environment_state", "resource_state", "rule_set"]:
        assert world[field] == {}
    validate_world_contract(world)


def test_a_negative_resource_stock_is_rejected():
    world = fixture("scenario_graph")["world_contract"]
    world["resource_state"]["fuel"] = -1

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "resource_state.fuel" in error_text(caught)


# ── space model ──────────────────────────────────────────────────────────────


def test_an_unknown_space_type_is_rejected():
    world = fixture("scenario_valid")["world_contract"]
    world["space_model"]["type"] = "hexgrid"

    with pytest.raises(ContractError):
        validate_world_contract(world)


def test_a_graph_without_edges_is_rejected():
    world = fixture("scenario_graph")["world_contract"]
    del world["space_model"]["edges"]

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "needs nodes and edges" in error_text(caught)


def test_an_edge_to_an_unknown_node_is_rejected():
    world = fixture("scenario_graph")["world_contract"]
    world["space_model"]["edges"].append(["A", "Z"])

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "unknown node" in error_text(caught)


def test_duplicate_nodes_are_rejected():
    world = fixture("scenario_graph")["world_contract"]
    world["space_model"]["nodes"].append("A")

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "unique" in error_text(caught)


def test_a_graph_edge_with_a_weight_is_rejected():
    world = fixture("scenario_graph")["world_contract"]
    world["space_model"]["edges"][0] = ["A", "B", 2]

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "graph edge has 2 items" in error_text(caught)


@pytest.mark.parametrize("weight", [0, -3])
def test_a_network_edge_needs_a_positive_weight(weight):
    world = fixture("scenario_network")["world_contract"]
    world["space_model"]["edges"][0][2] = weight

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "positive weight" in error_text(caught)


# ── entity placement ─────────────────────────────────────────────────────────


def test_a_graph_entity_must_stand_on_a_known_node():
    scenario = fixture("scenario_graph")
    scenario["entities"][0]["position"] = "Z"

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "outside the graph space" in error_text(caught)


def test_a_graph_entity_cannot_use_a_grid_cell():
    scenario = fixture("scenario_graph")
    scenario["entities"][0]["position"] = [0, 0]

    with pytest.raises(ContractError):
        validate_scenario(scenario)


def test_a_grid_entity_must_stand_inside_the_grid():
    scenario = fixture("scenario_valid")
    width = scenario["world_contract"]["space_model"]["width"]
    scenario["entities"][0]["position"] = [width, 0]

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert "outside the grid space" in error_text(caught)


def test_a_grid_entity_cannot_use_a_node_id():
    scenario = fixture("scenario_valid")
    scenario["entities"][0]["position"] = "A"

    with pytest.raises(ContractError):
        validate_scenario(scenario)


# ── time model ───────────────────────────────────────────────────────────────


def test_a_phase_clock_without_phase_length_is_rejected():
    world = fixture("scenario_network")["world_contract"]
    del world["time_model"]["phase_length"]

    with pytest.raises(ContractError) as caught:
        validate_world_contract(world)

    assert "phase_length" in error_text(caught)


def test_an_unknown_time_type_is_rejected():
    world = fixture("scenario_valid")["world_contract"]
    world["time_model"]["type"] = "realtime"

    with pytest.raises(ContractError):
        validate_world_contract(world)


# ── events ───────────────────────────────────────────────────────────────────


def test_a_resource_changed_event_validates_with_a_node_location():
    event = fixture("event_valid")
    event = copy.deepcopy(event)
    event["event_type"] = "RESOURCE_CHANGED"
    event["affected"]["locations"] = ["depot"]
    event["affected"]["resources"] = ["fuel"]

    assert validate_event(event)["affected"]["locations"] == ["depot"]
