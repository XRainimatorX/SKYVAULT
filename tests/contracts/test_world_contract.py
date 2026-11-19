"""World Contract = Formal Spec section 2, field by field."""

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
WORLDS = FIXTURES / "worlds"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import ContractError, validate_event, validate_world_contract
from skyvault.contracts.world import parse_duration

# Formal Spec section 2.2: the thirteen elements every world must declare
SECTION_2_2 = [
    "world_scope",
    "space_model",
    "time_model",
    "entity_model",
    "environment_state",
    "resource_state",
    "rule_set",
    "actor_slots",
    "event_memory",
    "evaluation_targets",
    "assumption_registry",
    "data_provenance",
    "failure_variables",
]


def world(name: str = "fixture_graph_world") -> dict:
    return json.loads((WORLDS / f"{name}.json").read_text(encoding="utf-8"))


def error_text(caught: pytest.ExceptionInfo) -> str:
    return " | ".join(caught.value.errors)


def section_2_3() -> dict:
    """The section 2.3 example world, as the spec writes it."""
    return {
        "world_id": "urban_crisis_test_001",
        "world_scope": "city_environment",
        "purpose": ["crisis_response", "system_stress_test", "governance_recovery"],
        "space_model": {
            "type": "district_network",
            "units": ["district", "road_node", "facility", "supply_point"],
            "nodes": ["north", "centre", "depot"],
            "edges": [["north", "centre", 2.0], ["centre", "depot", 1.0]],
            "node_units": {
                "north": "district",
                "centre": "district",
                "depot": "supply_point",
            },
        },
        "time_model": {
            "type": "phase_event_hybrid",
            "phase_length": "6_hours",
            "max_duration": "14_days",
        },
        "entity_model": {
            "humans": True,
            "vehicles": True,
            "infrastructure": True,
            "resources": True,
            "ai_systems": True,
        },
        "environment_state": {
            "power_grid": "unstable",
            "public_order": "low",
            "weather": "heavy_rain",
            "communication": "degraded",
        },
        "resource_state": {},
        "rule_set": {},
        "actor_slots": [
            "NEXUS",
            "STARTX",
            "TAC_ANGEL",
            "EIDEN_01",
            "AEROGRID",
            "HADES",
        ],
        "event_memory": {"format": "event_sourcing"},
        "evaluation_targets": [
            "stability_recovery",
            "resource_cost",
            "civilian_pressure",
            "system_performance",
            "risk_growth",
        ],
        "assumption_registry": {
            "public_order_decay_rate": "medium",
            "supply_delay_model": "regional_disruption",
            "civilian_pressure_model": "high_sensitivity",
            "infrastructure_recovery_speed": "slow",
        },
        "data_provenance": {
            "source_type": "mixed_input",
            "source_quality": "medium",
            "timestamp": "",
            "version": "",
        },
        "failure_variables": [
            "supply_delay",
            "communication_failure",
            "public_order_collapse",
            "weather_degradation",
        ],
    }


# ── section 2.2 and 2.3 ──────────────────────────────────────────────────────


def test_the_section_2_3_example_world_is_a_valid_world_contract():
    assert validate_world_contract(section_2_3())["world_id"] == "urban_crisis_test_001"


@pytest.mark.parametrize("field", SECTION_2_2)
def test_a_world_without_any_section_2_2_element_is_rejected(field):
    broken = world()
    del broken[field]

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert field in error_text(caught)


def test_empty_elements_are_allowed_when_declared():
    empty = world("fixture_world_001")

    for field in ["entity_model", "environment_state", "resource_state", "rule_set"]:
        assert empty[field] == {}
    validate_world_contract(empty)


def test_world_provenance_has_the_section_2_3_shape():
    broken = world()
    broken["data_provenance"] = {"sources": []}

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert "data_provenance.source_type" in error_text(caught)


def test_a_negative_resource_stock_is_rejected():
    broken = world()
    broken["resource_state"]["fuel"] = -1

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert "resource_state.fuel" in error_text(caught)


def test_an_unknown_failure_variable_is_rejected():
    broken = world()
    broken["failure_variables"] = ["meteor"]

    with pytest.raises(ContractError):
        validate_world_contract(broken)


# ── space model ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"type": "hexgrid"}, "space_model.type"),
        ({"edges": None}, "needs nodes and edges"),
        ({"edges": [["a", "nowhere"]]}, "unknown node"),
        ({"nodes": ["a", "a"]}, "unique"),
        ({"edges": [["a", "b", 2]]}, "has 2 items"),
    ],
)
def test_a_broken_graph_space_is_rejected(change, expected):
    broken = world()
    broken["space_model"] = {
        "type": "graph",
        "nodes": ["a", "b"],
        "edges": [["a", "b"]],
        **change,
    }

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert expected in error_text(caught)


@pytest.mark.parametrize("weight", [0, -3])
def test_a_network_edge_needs_a_positive_weight(weight):
    broken = world("fixture_network_world")
    broken["space_model"]["edges"][0][2] = weight

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert "positive weight" in error_text(caught)


def test_a_district_network_names_its_kinds_of_node():
    broken = section_2_3()
    del broken["space_model"]["units"]
    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)
    assert "names its units" in error_text(caught)

    strange = section_2_3()
    strange["space_model"]["node_units"]["depot"] = "castle"
    with pytest.raises(ContractError) as caught:
        validate_world_contract(strange)
    assert "castle" in error_text(caught)


# ── time model ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "time_model, expected",
    [
        ({"type": "phase"}, "needs phase_length"),
        ({"type": "phase_event_hybrid"}, "needs phase_length"),
        ({"type": "long_duration", "phase_length": "1_days"}, "needs max_duration"),
        ({"type": "continuous"}, "time_model.type"),
        ({"type": "phase", "phase_length": "6_fortnights"}, "not a duration"),
        ({"type": "phase", "phase_length": 0}, "must be positive"),
    ],
)
def test_a_broken_time_model_is_rejected(time_model, expected):
    broken = world()
    broken["time_model"] = time_model

    with pytest.raises(ContractError) as caught:
        validate_world_contract(broken)

    assert expected in error_text(caught)


def test_durations_are_written_as_the_spec_writes_them():
    assert parse_duration("6_hours") == (6, "hours")
    assert parse_duration("14_days") == (14, "days")
    assert parse_duration(40) == (40, None)


# ── profiles ─────────────────────────────────────────────────────────────────


def test_a_world_may_name_profiles_but_not_baseline():
    named = world()
    named["profiles"] = {"rules": {"strict": {"limit": 1}}, "environment": {}}
    assert validate_world_contract(named)["profiles"]["rules"] == {
        "strict": {"limit": 1}
    }

    named["profiles"] = {"environment": {"baseline": {"weather": "rain"}}}
    with pytest.raises(ContractError) as caught:
        validate_world_contract(named)
    assert "baseline" in error_text(caught)


# ── events ───────────────────────────────────────────────────────────────────


def test_a_resource_changed_event_validates_with_a_node_location():
    event = json.loads((FIXTURES / "event_valid.json").read_text(encoding="utf-8"))
    event = copy.deepcopy(event)
    event["event_type"] = "RESOURCE_CHANGED"
    event["affected"]["locations"] = ["depot"]
    event["affected"]["resources"] = ["fuel"]

    assert validate_event(event)["affected"]["locations"] == ["depot"]
