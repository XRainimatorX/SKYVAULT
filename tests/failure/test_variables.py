"""Failure variables, stress levels and the communication fault."""

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SCENARIOS = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001"

for path in (SRC_PATH, REPO_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from reference_trace import trace  # noqa: E402

from skyvault.contracts import (
    FAILURE_VARIABLE_NAMES,
    ContractError,
    validate_failure_exploration,
    validate_scenario,
)
from skyvault.engine import SkyVaultEngine
from skyvault.failure.variables import FAILURE_VARIABLES, STRESS_LEVELS, apply_stress
from skyvault.scenario_loader import load_scenario


def plan() -> dict:
    return load_scenario(SCENARIOS / "v0.1.json")


def logistics() -> dict:
    with (FIXTURES / "scenario_logistics.json").open(encoding="utf-8") as file:
        return validate_scenario(json.load(file))


def entity(scenario, entity_id):
    return next(e for e in scenario["entities"] if e["entity_id"] == entity_id)


def stressed(name, level, scenario=None, perspective="RED"):
    return apply_stress(scenario or plan(), {name: level}, perspective)


def test_the_engine_knows_the_eight_plan_variables_and_four_levels():
    assert tuple(FAILURE_VARIABLES) == FAILURE_VARIABLE_NAMES
    assert STRESS_LEVELS == ("mild", "moderate", "severe", "collapse")


# ── each variable at each level (red_001: accuracy 0.8, hp 35; red_002 damage 16;
#    blue_001: accuracy 0.8) ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("level", "factor"), list(zip(STRESS_LEVELS, (0.9, 0.75, 0.6, 0.4), strict=True))
)
def test_sensor_failure_lowers_only_own_accuracy(level, factor):
    result = stressed("sensor_failure", level)

    assert entity(result, "red_001")["capabilities"]["accuracy"] == round(
        0.8 * factor, 4
    )
    assert entity(result, "blue_001")["capabilities"]["accuracy"] == 0.8


@pytest.mark.parametrize(
    ("level", "factor"), list(zip(STRESS_LEVELS, (0.9, 0.75, 0.6, 0.4), strict=True))
)
def test_weather_lowers_everyones_accuracy(level, factor):
    result = stressed("weather_degradation", level)

    for entity_id in ("red_001", "blue_001"):
        assert entity(result, entity_id)["capabilities"]["accuracy"] == round(
            0.8 * factor, 4
        )


@pytest.mark.parametrize(
    ("level", "expected"), list(zip(STRESS_LEVELS, (0.85, 0.9, 1.0, 1.0), strict=True))
)
def test_enemy_reaction_raises_enemy_accuracy_up_to_one(level, expected):
    result = stressed("enemy_reaction_speed", level)

    assert entity(result, "blue_001")["capabilities"]["accuracy"] == expected
    assert entity(result, "red_001")["capabilities"]["accuracy"] == 0.8


@pytest.mark.parametrize(
    ("level", "expected"), list(zip(STRESS_LEVELS, (14, 12, 8, 4), strict=True))
)
def test_overheat_cuts_own_damage_to_whole_points(level, expected):
    result = stressed("equipment_overheat", level)

    assert entity(result, "red_002")["capabilities"]["attack_damage"] == expected
    assert entity(result, "blue_002")["capabilities"]["attack_damage"] == 16


@pytest.mark.parametrize(
    ("level", "expected"), list(zip(STRESS_LEVELS, (31, 26, 21, 14), strict=True))
)
def test_civilian_pressure_cuts_own_starting_hp(level, expected):
    result = stressed("civilian_pressure", level)

    assert entity(result, "red_001")["state"]["hp"] == expected
    assert entity(result, "blue_001")["state"]["hp"] == 35


@pytest.mark.parametrize(
    ("level", "rate"), list(zip(STRESS_LEVELS, (0.1, 0.25, 0.5, 0.8), strict=True))
)
def test_communication_failure_injects_a_drop_rate_for_own_orders(level, rate):
    result = stressed("communication_failure", level)

    assert result["world_contract"]["rule_set"]["faults"] == {
        "drop_actions": {"faction": "RED", "rate": rate}
    }


@pytest.mark.parametrize("name", ["supply_delay", "resource_shortage"])
def test_resource_variables_do_not_apply_to_a_world_without_resources(name):
    applicable, reason = FAILURE_VARIABLES[name].applies(plan(), "RED")

    assert not applicable
    assert reason == "the world holds no resources"
    with pytest.raises(ValueError, match="does not apply"):
        stressed(name, "mild")


@pytest.mark.parametrize(
    ("name", "level", "fuel"),
    [
        ("supply_delay", "mild", 45.0),
        ("supply_delay", "collapse", 12.5),
        ("resource_shortage", "moderate", 25.0),
        ("resource_shortage", "collapse", 0.0),
    ],
)
def test_resource_variables_shrink_the_world_stock(name, level, fuel):
    result = stressed(name, level, logistics(), "BLUE")

    assert result["world_contract"]["resource_state"]["fuel"] == fuel


# ── a stressed scenario is a new version ─────────────────────────────────────


def test_a_stressed_scenario_is_a_valid_child_version_and_the_input_is_untouched():
    original = plan()
    before = copy.deepcopy(original)

    result = apply_stress(
        original, {"weather_degradation": "severe", "equipment_overheat": "mild"}, "RED"
    )

    assert original == before
    assert result["scenario_version"] == (
        "v0.1+weather_degradation:severe+equipment_overheat:mild"
    )
    control = result["version_control"]
    assert control["parent_version"] == "v0.1"
    assert control["version"] == result["scenario_version"]
    assert "entities[red_002].capabilities.attack_damage: 16 -> 14" in (
        control["changed_from_previous"]["data_changed"]
    )
    validate_scenario(result)


def test_an_injected_fault_is_recorded_as_a_rules_change():
    control = stressed("communication_failure", "severe")["version_control"]

    assert control["changed_from_previous"]["rules_changed"] == [
        "world_contract.rule_set.faults: absent -> "
        "{'drop_actions': {'faction': 'RED', 'rate': 0.5}}"
    ]


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError, match="unknown stress level"):
        stressed("weather_degradation", "apocalypse")


# ── the communication fault in real runs ─────────────────────────────────────


def run(scenario):
    return SkyVaultEngine(scenario).run()


def test_dropped_orders_match_the_rate_and_only_hit_the_stressed_side():
    rejected, selected = 0, 0
    for seed in range(42, 52):
        scenario = stressed("communication_failure", "severe")
        scenario["runtime"]["random_seed"] = seed
        events = run(scenario)["event_memory"]
        red = [e for e in events if (e["source"]["actor_id"] or "").startswith("red")]
        selected += sum(e["event_type"] == "ACTION_SELECTED" for e in red)
        rejected += sum(
            e["event_type"] == "ACTION_REJECTED"
            and e["data"]["reason"] == "Communication failure: order not received"
            for e in red
        )
        blue_rejected = [
            e
            for e in events
            if e["event_type"] == "ACTION_REJECTED"
            and e["source"]["actor_id"].startswith("blue")
        ]
        assert blue_rejected == []

    assert selected > 100
    assert 0.4 < rejected / selected < 0.6


def test_a_zero_rate_fault_never_shifts_the_battle():
    quiet = plan()
    quiet["world_contract"]["rule_set"]["faults"] = {
        "drop_actions": {"faction": "RED", "rate": 0.0}
    }

    assert trace(run(quiet)) == trace(run(plan()))


# ── the contracts ────────────────────────────────────────────────────────────


def test_the_plans_exploration_request_is_valid():
    request = plan()["failure_exploration"]

    assert validate_failure_exploration(request) == request
    assert request["run_policy"]["repeat_count"] == 10
    assert request["alternatives"] == ["v0.1-support-rear", "v0.1-spread"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda s: s["failure_exploration"].update(
                {"failure_variables": ["supply_delay"]}
            ),
            "does not list in failure_variables",
        ),
        (
            lambda s: s["failure_exploration"].update(
                {"stress_levels": ["mild", "mild"]}
            ),
            "must not repeat",
        ),
        (
            lambda s: s["world_contract"].update({"failure_variables": ["meteor"]}),
            "Input should be",
        ),
        (lambda s: s.update({"schema_version": "0.5"}), "schema_version"),
    ],
)
def test_a_broken_failure_declaration_is_rejected(change, message):
    scenario = plan()
    change(scenario)

    with pytest.raises(ContractError) as caught:
        validate_scenario(scenario)

    assert message in " | ".join(caught.value.errors)
