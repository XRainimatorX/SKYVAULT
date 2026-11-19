"""The scenario compiler = Formal Spec section 4, step 2 (Compile Scenario)."""

import copy
import json

import pytest
from conftest import REPO_ROOT

from skyvault.compiler import (
    author_scenario,
    author_world,
    compile_scenario,
    load_world,
    overlay,
    publish,
)
from skyvault.contracts import ContractError
from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario

FIXTURES = REPO_ROOT / "tests" / "fixtures"
DATA = REPO_ROOT / "data"


def document(name: str = "scenario_valid") -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def urban(version: str = "v0.2") -> dict:
    path = DATA / "scenarios" / "military_urban_001" / f"{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def errors(caught: pytest.ExceptionInfo) -> str:
    return " | ".join(caught.value.errors)


# ── binding ──────────────────────────────────────────────────────────────────


def test_a_scenario_binds_to_the_world_it_names():
    compiled = compile_scenario(document())

    assert compiled["world_contract"]["world_id"] == "fixture_world_001"
    assert compiled["world_binding"]["world_contract_id"] == "fixture_world_001"
    assert compiled["world_contract"]["profiles"] is None


def test_a_scenario_bound_to_no_known_world_is_refused():
    scenario = document()
    scenario["world_binding"]["world_contract_id"] = "atlantis"

    with pytest.raises(ContractError, match="no world contract 'atlantis'"):
        compile_scenario(scenario)


def test_a_world_handed_over_must_be_the_one_named():
    world = load_world("fixture_graph_world")

    with pytest.raises(ContractError, match="but the world is 'fixture_graph_world'"):
        compile_scenario(document(), world)


def test_a_rule_profile_is_laid_over_the_world():
    compiled = compile_scenario(urban("v0.2+overwatch"))
    baseline = compile_scenario(urban("v0.2"))

    factions = compiled["world_contract"]["rule_set"]["military"]["factions"]
    assert factions["RED"]["doctrine"] == "overwatch"
    assert baseline["world_contract"]["rule_set"]["military"]["factions"]["RED"][
        "doctrine"
    ] == ("aggressive")
    # the rest of the rules are the world's own
    assert factions["BLUE"] == (
        baseline["world_contract"]["rule_set"]["military"]["factions"]["BLUE"]
    )


@pytest.mark.parametrize("field", ["environment_profile", "rule_profile"])
def test_a_profile_the_world_does_not_declare_is_refused(field):
    scenario = urban()
    scenario["world_binding"][field] = "night_raid"

    with pytest.raises(ContractError, match=f"world_binding.{field}: 'night_raid'"):
        compile_scenario(scenario)


def test_starting_resources_replace_the_world_s_own_and_must_exist():
    scenario = document("scenario_logistics")
    world = load_world(scenario["world_binding"]["world_contract_id"])
    resource = next(iter(world["resource_state"]))
    scenario["initial_conditions"]["resources"] = {resource: 3.0}

    assert (
        compile_scenario(scenario)["world_contract"]["resource_state"][resource] == 3.0
    )

    scenario["initial_conditions"]["resources"] = {"unobtainium": 1.0}
    with pytest.raises(ContractError, match="holds no 'unobtainium'"):
        compile_scenario(scenario)


# ── execution settings ───────────────────────────────────────────────────────


def test_time_mode_must_be_the_world_s_clock():
    scenario = document()
    scenario["execution_settings"]["time_mode"] = "event_driven"

    with pytest.raises(ContractError, match="the world runs on 'tick'"):
        compile_scenario(scenario)


@pytest.mark.parametrize("limit, steps", [(12, 12), ("12_ticks", 12)])
def test_a_duration_limit_counts_steps(limit, steps):
    scenario = document()
    scenario["execution_settings"]["duration_limit"] = limit

    assert compile_scenario(scenario)["runtime"]["max_ticks"] == steps


def test_a_duration_in_days_counts_phases():
    scenario = document("scenario_network")
    world = load_world(scenario["world_binding"]["world_contract_id"])
    world["time_model"] = {"type": "phase_event_hybrid", "phase_length": "6_hours"}
    scenario["execution_settings"]["time_mode"] = "phase_event_hybrid"
    scenario["execution_settings"]["duration_limit"] = "14_days"

    # section 2.3: six-hour phases over fourteen days
    assert compile_scenario(scenario, world)["runtime"]["max_ticks"] == 56


def test_a_duration_in_hours_needs_a_phased_world():
    scenario = document()
    scenario["execution_settings"]["duration_limit"] = "6_hours"

    with pytest.raises(ContractError, match="needs a phased world"):
        compile_scenario(scenario)


def test_a_stochastic_run_cannot_promise_a_replay():
    scenario = document()
    scenario["execution_settings"]["random_seed_policy"] = "stochastic"

    with pytest.raises(ContractError, match="cannot be replayed"):
        compile_scenario(scenario)

    scenario["output"]["replay_required"] = False
    assert compile_scenario(scenario)["runtime"]["random_seed_policy"] == "stochastic"


# ── participants ─────────────────────────────────────────────────────────────


def test_slots_become_the_run_s_policies_and_orders():
    scenario = document()
    first, second = (
        e["entity_id"] for e in scenario["initial_conditions"]["entities"][:2]
    )
    scenario["participants"] = {
        "human_decision_slots": [
            {
                "slot_id": "commander",
                "orders": [
                    {"tick": 1, "actor_id": first, "action_type": "wait", "target": {}}
                ],
            }
        ],
        "ai_agent_slots": [
            {"slot_id": "default", "policy": {"name": "noop"}},
            {
                "slot_id": "TAC_ANGEL",
                "policy": {"name": "noop", "params": {"x": 1}},
                "controls": {"entity_ids": [second]},
            },
        ],
        "system_slots": [
            {
                "slot_id": "STARTX",
                "orders": [
                    {"tick": 2, "actor_id": first, "action_type": "wait", "target": {}}
                ],
            }
        ],
        "equipment_profiles": [],
    }

    runtime = compile_scenario(scenario)["runtime"]

    assert runtime["policy"] == {"name": "noop", "params": {}}
    assert runtime["participants"] == [
        {
            "participant_id": "TAC_ANGEL",
            "policy": {"name": "noop", "params": {"x": 1}},
            "controls": {"factions": [], "entity_ids": [second]},
        }
    ]
    assert [(o["tick"], o["system_id"]) for o in runtime["scheduled_actions"]] == [
        (1, "commander"),
        (2, "STARTX"),
    ]


# ── failure exploration ──────────────────────────────────────────────────────


def test_an_enabled_exploration_becomes_the_explorer_s_request():
    explored = compile_scenario(urban())["failure_exploration"]

    assert explored["stress_levels"] == ["mild", "moderate", "severe", "collapse"]
    assert explored["run_policy"]["branch_comparison"] is True
    assert explored["alternatives"] == ["v0.2+overwatch", "v0.2+defensive"]
    assert compile_scenario(urban("v0.1"))["failure_exploration"] is None


def test_magnitudes_given_for_a_level_are_carried_to_the_explorer():
    scenario = urban()
    scenario["failure_exploration"]["stress_levels"] = {
        "moderate": {"sensor_failure": 0.5},
        "collapse": {},
    }

    explored = compile_scenario(scenario)["failure_exploration"]

    assert explored["stress_levels"] == ["moderate", "collapse"]
    assert explored["magnitudes"] == {"moderate": {"sensor_failure": 0.5}}


def test_exploring_a_failure_the_world_cannot_suffer_is_refused():
    scenario = urban()
    scenario["failure_exploration"]["failure_variables"] = ["civilian_pressure"]

    with pytest.raises(ContractError, match="not among the world contract"):
        compile_scenario(scenario)


# ── author and publish ───────────────────────────────────────────────────────


def test_authoring_a_compiled_scenario_compiles_back_to_it():
    compiled = load_scenario(DATA / "scenarios" / "military_urban_001" / "v0.2.json")
    world = author_world(compiled["world_contract"])

    assert compile_scenario(author_scenario(compiled), world) == compiled


def test_publish_writes_profiles_for_what_versions_change():
    base = load_scenario(DATA / "scenarios" / "military_squad_001" / "v0.1.json")
    variant = copy.deepcopy(base)
    variant["scenario_version"] = "v0.1+night"
    variant["version_control"] = None
    variant["world_contract"]["environment_state"]["light"] = "night"
    variant["world_contract"]["resource_state"]["ammo"] = 5.0

    files = publish({"a/v0.1.json": base, "a/v0.1+night.json": variant})

    world = files["worlds/military_squad_001_world.json"]
    assert world["profiles"]["environment"] == {"night": {"light": "night"}}
    night = files["scenarios/a/v0.1+night.json"]
    assert night["world_binding"]["environment_profile"] == "night"
    assert night["initial_conditions"]["resources"] == {"ammo": 5.0}
    assert compile_scenario(night, world)["world_contract"]["environment_state"][
        "light"
    ] == ("night")


def test_publish_refuses_versions_that_are_different_worlds():
    base = load_scenario(DATA / "scenarios" / "military_squad_001" / "v0.1.json")
    other = copy.deepcopy(base)
    other["world_contract"]["space_model"]["width"] += 1

    with pytest.raises(ValueError, match="space_model differs"):
        publish({"a/v0.1.json": base, "a/v0.2.json": other})


def test_overlay_merges_nested_keys_and_replaces_the_rest():
    assert overlay({"a": {"b": 1, "c": 2}, "d": [1]}, {"a": {"b": 9}, "d": [2]}) == {
        "a": {"b": 9, "c": 2},
        "d": [2],
    }


# ── allowed actions ──────────────────────────────────────────────────────────


def test_an_action_the_scenario_does_not_allow_is_rejected_with_a_reason():
    scenario = urban("v0.1")
    scenario["allowed_actions"] = {
        "action_types": ["move", "observe"],
        "actor_permissions": {},
    }

    package = SkyVaultEngine(compile_scenario(scenario)).run()

    reasons = {
        e["data"]["reason"]
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
    }
    assert "Not allowed in this scenario: attack" in reasons
    assert not any(e["event_type"] == "ATTACK" for e in package["event_memory"])


def test_a_faction_permission_narrows_what_its_units_may_do():
    scenario = urban("v0.1")
    scenario["allowed_actions"] = {
        "action_types": [],
        "actor_permissions": {"BLUE": ["move", "observe", "supply"]},
    }

    package = SkyVaultEngine(compile_scenario(scenario)).run()

    refused = [
        e
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
        and e["data"]["reason"].endswith("may not attack in this scenario")
    ]
    assert refused and all(e["source"]["actor_id"].startswith("blue") for e in refused)


# ── the fourteen steps ───────────────────────────────────────────────────────


def test_every_result_package_traces_the_fourteen_steps_of_section_4_2():
    package = SkyVaultEngine(
        load_scenario(DATA / "scenarios" / "military_urban_001" / "v0.2.json")
    ).run()

    steps = package["execution_protocol"]
    assert [s["name"] for s in steps] == [
        "receive_task",
        "compile_scenario",
        "instantiate_world",
        "register_participants",
        "generate_observations",
        "receive_actions",
        "validate_actions",
        "resolve_consequences",
        "mutate_world_state",
        "record_events",
        "evaluate_current_state",
        "explore_failure_branches",
        "continue_branch_terminate",
        "generate_result_package",
    ]
    assert steps[1]["detail"].startswith("military_urban_001/v0.2 bound to")
    assert steps[9]["detail"] == f"{len(package['event_memory'])} events recorded"
    assert steps[11]["status"] == "separate_job"


def test_who_asked_for_a_run_does_not_change_its_output_hash():
    scenario = load_scenario(DATA / "scenarios" / "military_squad_001" / "v0.1.json")
    direct = SkyVaultEngine(copy.deepcopy(scenario)).run()
    engine = SkyVaultEngine(copy.deepcopy(scenario))
    engine.task_source = "NEXUS job job_000001 (scenario_run)"
    asked = engine.run()

    assert asked["execution_protocol"][0]["detail"].startswith("NEXUS")
    assert asked["reproducibility"]["output_hash"] == (
        direct["reproducibility"]["output_hash"]
    )
