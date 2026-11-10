"""Phase 16 steps B and C: equipment in a mission, surrogate, STAR GUARD, outputs."""

import copy
import json
import random
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from skyvault.action import Action, ActionTarget
from skyvault.actions import ActionContext
from skyvault.domains.military.handlers import military_handlers
from skyvault.domains.military.policy import MilitaryBaselinePolicy
from skyvault.engine import SkyVaultEngine
from skyvault.interface.api import run_submission
from skyvault.interface.systems import to_request
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_scenario
from skyvault.virtualtest.profile import load_profile, load_rules
from skyvault.virtualtest.report import virtual_test_report
from skyvault.virtualtest.run import virtual_test
from skyvault.virtualtest.surrogate import fit, predict, variants
from skyvault.virtualtest.tactical import (
    logistics_burden,
    replaced_unit,
    tactical_usefulness,
    unit_changes,
)
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[2]
RULES = load_rules()
EXO = load_profile("exo_test_001")
PAX = load_profile("pax_test_001")
MSX = load_profile("msx_test_001")
ERX = load_profile("erx_test_001")
SQUAD = ROOT / "data" / "scenarios" / "military_squad_001" / "v0.1.json"
HANDLERS = military_handlers()


@cache
def full(name: str) -> dict:
    """A profile's full virtual test with the rules' own scenarios and seeds."""
    return virtual_test(load_profile(name))


# ── the profile as a military unit ───────────────────────────────────────────


def test_an_assault_profile_replaces_the_first_rifleman_of_its_side():
    scenario = load_scenario(SQUAD)
    assert replaced_unit(scenario, EXO, RULES)["entity_id"] == "red_02"
    assert replaced_unit(scenario, ERX, RULES) is None  # no logistics unit here
    assert replaced_unit(scenario, EXO, RULES, "blue_03")["entity_id"] == "blue_03"


def test_the_mapping_turns_physics_into_what_the_unit_can_do():
    scenario = load_scenario(SQUAD)
    rifleman = replaced_unit(scenario, EXO, RULES)
    exo = unit_changes(EXO, RULES, rifleman, 20)
    assert exo["name"] == "EXO_TEST_001"
    assert exo["state"]["hp"] == 30 * 1.5
    assert exo["capabilities"]["move_range"] == 2  # 7.3 W/kg: neither fast nor slow
    # tires slower than an unequipped infantryman: 0.6 × (1 + 0.02 × 3.33 h / 2)
    assert exo["capabilities"]["accuracy"] == pytest.approx(0.6 * (1 + 0.02 * 20 / 12))
    assert exo["capabilities"]["endurance_ticks"] == 24  # 4 h of 10-minute ticks
    assert "building" in exo["capabilities"]["terrain_access"]
    msx = unit_changes(MSX, RULES, rifleman, 20)
    assert msx["capabilities"]["move_range"] == 3  # 22 W/kg
    assert msx["capabilities"]["terrain_access"] == ["open", "road"]
    assert msx["capabilities"]["endurance_ticks"] == 9  # 600 kWh / 400 kW = 1.5 h
    assert msx["capabilities"]["accuracy"] < 0.6
    assert msx["capabilities"]["weapon"] == "rifle"  # what the profile does not say


def test_a_slow_heavy_design_loses_a_step_and_the_profile_can_override():
    rifleman = replaced_unit(load_scenario(SQUAD), EXO, RULES)
    slug = copy.deepcopy(EXO)
    slug["physical_parameters"]["power_requirement"] = 0.3  # 1.8 W/kg
    assert unit_changes(slug, RULES, rifleman, 20)["capabilities"]["move_range"] == 1
    slug["capabilities"] = {"move_range": 4}
    slug["state"] = {"hp": 99}
    forced = unit_changes(slug, RULES, rifleman, 20)
    assert forced["capabilities"]["move_range"] == 4 and forced["state"]["hp"] == 99


def test_logistics_burden_counts_transport_upkeep_deployment_and_supply():
    assert logistics_burden(EXO, RULES) == "low"
    assert logistics_burden(MSX, RULES) == "high"
    assert logistics_burden({"equipment_id": "X", "category": "EXO"}, RULES) == "low"


# ── the military pack's two new limits ───────────────────────────────────────


def military_world(**capabilities):
    world = create_world(load_scenario(SQUAD))
    world.get_entity("red_02").capabilities.update(capabilities)
    return world, ActionContext(rng=random.Random(1), system_id="test")


def order(world, actor, action_type, entity_id=None, location=None):
    return Action(
        action_id=world.ids.action(),
        actor_id=actor,
        action_type=action_type,
        target=ActionTarget(entity_id=entity_id, location=location),
    )


def test_a_unit_is_refused_terrain_it_cannot_enter_or_cross():
    world, context = military_world(terrain_access=["open", "road"], move_range=3)
    forest = (2, 2)  # row 2 is "..ff...ff.", and nobody stands there
    assert world.environment["terrain"]["rows"][2][2] == "f"
    refused = HANDLERS["move"].validate(
        world, order(world, "red_02", "move", location=forest), context
    )
    assert not refused.valid and refused.reason == (
        "Move target is impassable for this unit"
    )
    free, _ = military_world(move_range=3)
    assert (
        HANDLERS["move"]
        .validate(free, order(free, "red_02", "move", location=forest), context)
        .valid
    )


def test_a_unit_whose_endurance_is_spent_can_neither_move_nor_shoot():
    world, context = military_world(endurance_ticks=3)
    move = order(world, "red_02", "move", location=(1, 1))
    world.tick = 3
    assert HANDLERS["move"].validate(world, move, context).valid
    world.tick = 4
    refused = HANDLERS["move"].validate(world, move, context)
    assert not refused.valid and refused.reason.startswith("Insufficient endurance")
    shot = HANDLERS["attack"].validate(
        world, order(world, "red_02", "attack", entity_id="blue_02"), context
    )
    assert not shot.valid and shot.reason.startswith("Insufficient endurance")


def test_the_baseline_policy_holds_a_spent_unit_and_routes_around_closed_ground():
    scenario = load_scenario(SQUAD)
    policy = MilitaryBaselinePolicy(random.Random(1), scenario)
    world, _ = military_world(endurance_ticks=0)
    world.tick = 1
    assert policy.decide(world, world.get_entity("red_02")) is None
    world, _ = military_world(terrain_access=["open", "road"], move_range=3)
    for cell in policy.options(world, world.get_entity("red_02")):
        assert world.environment["terrain"]["rows"][cell[1]][cell[0]] in ".r"


def test_without_the_new_capabilities_the_run_is_what_it_was():
    scenario = load_scenario(SQUAD)
    before = SkyVaultEngine(copy.deepcopy(scenario)).run()
    open_everywhere = copy.deepcopy(scenario)
    unit = next(e for e in open_everywhere["entities"] if e["entity_id"] == "red_02")
    unit["capabilities"]["endurance_ticks"] = 1000
    after = SkyVaultEngine(open_everywhere).run()
    assert [e["event_type"] for e in after["event_memory"]] == [
        e["event_type"] for e in before["event_memory"]
    ]


# ── acceptance 4: value in a mission ─────────────────────────────────────────


def test_equipment_changes_the_mission_and_is_compared_with_the_baseline():
    found = tactical_usefulness(EXO, RULES, ["military_squad_001"], [42, 43])
    (context,) = found["contexts"]
    assert context["replaces"] == "red_02"
    assert context["equipped"] != context["baseline"]
    assert context["versus_baseline"] == {
        k: round(context["equipped"][k] - context["baseline"][k], 4)
        for k in context["equipped"]
    }
    assert found["unit"]["name"] == "EXO_TEST_001"


def test_a_scenario_without_a_unit_of_its_role_is_not_applicable():
    found = tactical_usefulness(ERX, RULES, ["military_squad_001"], [42])
    assert found["contexts"] == [
        {"scenario": "military_squad_001", "applicable": False}
    ]
    assert found["score"] is None and found["useful_contexts"] == []


def test_every_profile_has_contexts_where_it_helps_and_none_is_useful_everywhere():
    for name in ("exo_test_001", "pax_test_001", "msx_test_001"):
        tactical = full(name)["tactical_usefulness"]
        assert tactical["useful_contexts"], name
        applicable = [c for c in tactical["contexts"] if c["applicable"]]
        assert len(tactical["useful_contexts"]) < len(applicable), name


def test_a_machine_kept_to_roads_is_weak_in_the_mountains():
    tactical = full("msx_test_001")["tactical_usefulness"]
    assert "military_mountain_001" in tactical["weak_contexts"]
    assert tactical["unit"]["capabilities"]["terrain_access"] == ["open", "road"]


# ── the judgements of the four profiles ──────────────────────────────────────


def test_the_four_profiles_are_continue_continue_redesign_reject():
    statuses = {
        name: full(name)["final_judgement"]["status"]
        for name in ("exo_test_001", "erx_test_001", "pax_test_001", "msx_test_001")
    }
    assert statuses == {
        "exo_test_001": "continue",
        "erx_test_001": "continue",
        "pax_test_001": "redesign",
        "msx_test_001": "reject",
    }
    assert (
        "energy_capacity 15.0 → 18.0001"
        in full("pax_test_001")["final_judgement"]["reason"]
    )


def test_a_redesign_made_as_the_solver_says_is_no_longer_impossible():
    triggers = full("pax_test_001")["failure_exploration"]["redesign_triggers"]
    redesigned = copy.deepcopy(PAX)
    for trigger in triggers:
        redesigned["physical_parameters"][trigger["parameter"]] = trigger["required"]
    result = virtual_test(redesigned, tactical=False)
    assert result["physical_possibility"]["impossible_flags"] == []
    statuses = {
        c["check"]: c["status"] for c in result["physical_possibility"]["checks"]
    }
    # an impossible check is brought to the line (a warning), a warning past it
    assert statuses["energy"] == "warning"
    assert statuses["joint_load"] == statuses["heat"] == "pass"


def test_a_near_line_design_worth_building_is_sent_to_external_simulation():
    close = copy.deepcopy(EXO)
    close["physical_parameters"]["energy_capacity"] = 1.2 * 4 * 1.05  # 5 % to spare
    result = virtual_test(close, tactical=False)
    assert result["final_judgement"]["status"] == "require_external_simulation"
    assert result["require_external_simulation"]["adapter"]["status"] == "not_run"


# ── the surrogate ────────────────────────────────────────────────────────────


def test_the_surrogate_fits_a_linear_effect_exactly_and_flags_extrapolation():
    def measure(variant):
        p = variant["physical_parameters"]
        return 0.1 * p["mass"] / 165 - 0.3 * p["power_requirement"] / 1.2 + 0.05

    model = fit(EXO, measure)
    assert len(model["samples"]) == len(variants(EXO)) == 7
    assert model["r2"] == pytest.approx(1.0)
    assert model["coefficients"] == pytest.approx([0.1, -0.3, 0.0], abs=1e-6)
    assert model["intercept"] == pytest.approx(0.05, abs=1e-6)
    inside = copy.deepcopy(EXO)
    inside["physical_parameters"]["mass"] = 165 * 1.1
    assert predict(model, inside) == {
        "value": pytest.approx(0.1 * 1.1 - 0.3 + 0.05, abs=1e-6),
        "out_of_range": False,
    }
    outside = copy.deepcopy(EXO)
    outside["physical_parameters"]["mass"] = 165 * 2
    assert predict(model, outside)["out_of_range"] is True


def test_a_flat_measure_fits_perfectly_and_a_missing_feature_is_not_varied():
    model = fit({**EXO, "physical_parameters": {"mass": 165}}, lambda v: 0.2)
    assert model["r2"] == 1.0 and len(model["samples"]) == 3


def test_the_virtual_test_can_carry_the_surrogate_and_its_redesign_prediction():
    result = virtual_test(
        PAX, scenarios=["military_squad_001"], seeds=[42, 43], surrogate=True
    )
    surrogate = result["surrogate"]
    assert surrogate["scenario"] == "military_squad_001"
    assert len(surrogate["model"]["samples"]) == 7
    assert set(surrogate["redesign_prediction"]) == {"value", "out_of_range"}


def test_a_surrogate_for_a_role_no_scenario_has_measures_nothing():
    result = virtual_test(
        ERX, scenarios=["military_squad_001"], seeds=[42], surrogate=True
    )
    assert all(s["y"] == 0.0 for s in result["surrogate"]["model"]["samples"])


# ── STAR GUARD and the world service ─────────────────────────────────────────


def star_guard(profile: dict, repeat_count: int = 2) -> dict:
    return {
        "system": "STAR_GUARD",
        "kind": "equipment",
        "scenario": "military_squad_001/v0.1",
        "content": {
            "replace": "red_02",
            "repeat_count": repeat_count,
            "profile": profile,
        },
    }


def test_star_guard_submits_a_section_18_profile_and_gets_the_virtual_test():
    returned = run_submission(star_guard(PAX), SQLiteStore(), load_governance())[
        "returned"
    ]
    assert returned["gaps"] == []
    result = returned["virtual_test"]
    assert result["final_judgement"]["status"] == "redesign"
    (context,) = result["tactical_usefulness"]["contexts"]
    assert context["replaces"] == "red_02"
    # the virtual test ran the same seeds as the submission's own runs
    assert context["equipped"]["mean_score"] == (
        returned["tactical_usefulness"]["equipped"]["mean_score"]
    )
    # its battery runs out mid-mission: the unit is refused for lack of power
    reasons = {
        r["reason"] for r in returned["physical_feasibility"]["capability_limits"]
    }
    assert "Insufficient endurance: power spent" in reasons


def test_star_guard_maps_the_profile_onto_the_unit_it_replaces():
    request = to_request(star_guard(MSX))
    change = request["jobs"][0]["entity_changes"]["red_02"]
    assert change["name"] == "MSX_TEST_001"
    assert change["capabilities"]["terrain_access"] == ["open", "road"]
    assert change["state"]["hp"] == 240
    assert request["gaps"] == []


def test_an_old_style_profile_still_works_and_gets_no_virtual_test():
    returned = run_submission(
        star_guard({"name": "EXO-1", "state": {"hp": 50}}, 1),
        SQLiteStore(),
        load_governance(),
    )["returned"]
    assert "virtual_test" not in returned
    assert returned["supported"] is True


def test_a_field_outside_section_18_is_still_a_gap():
    request = to_request(star_guard({**EXO, "colour": "olive"}))
    assert request["gaps"] == [
        "equipment field 'colour' has no model (give section 18 groups: "
        "physical_parameters, engineering_parameters, operational_parameters)"
    ]


# ── the report and the script ────────────────────────────────────────────────


def test_the_report_does_not_round_a_shortfall_up_to_the_line():
    text = virtual_test_report([full("pax_test_001")])
    assert "| PAX_TEST_001 | PAX | 0.000 | 0.496 |" in text
    assert "to make it possible" in text and "to clear the warning" in text
    msx = virtual_test_report([full("msx_test_001")])
    assert "nothing new fails under: payload" in msx
    assert "External simulation: required" in msx


def test_run_virtual_test_writes_a_result_per_profile_and_the_report(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_virtual_test.py"),
            "--output",
            str(tmp_path),
            "--seeds",
            "1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "MSX_TEST_001" in done.stdout and "→ reject" in done.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ERX_TEST_001.json",
        "EXO_TEST_001.json",
        "MSX_TEST_001.json",
        "PAX_TEST_001.json",
        "virtual_test_report.md",
    ]
    pax = json.loads((tmp_path / "PAX_TEST_001.json").read_text())
    assert pax["final_judgement"]["status"] == "redesign"
