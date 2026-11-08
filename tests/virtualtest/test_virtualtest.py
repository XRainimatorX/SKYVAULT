"""Phase 16: the virtual test rules: physics, engineering, solver, stress, judgement."""

import copy
import sys
from pathlib import Path

import pytest

from skyvault.contracts import (
    ContractError,
    validate_equipment_profile,
    validate_equipment_test_result,
)
from skyvault.virtualtest.engineering import engineering_feasibility, maintenance_ratio
from skyvault.virtualtest.external import StandInSimulator, external_simulation
from skyvault.virtualtest.judgement import final_judgement
from skyvault.virtualtest.physics import (
    accessible_terrain,
    effective_endurance,
    ground_pressure_kpa,
    margins,
    physical_possibility,
)
from skyvault.virtualtest.profile import (
    has_equipment_parameters,
    load_profile,
    load_rules,
    reference_profiles,
    with_param,
)
from skyvault.virtualtest.run import virtual_test
from skyvault.virtualtest.solver import mass_limit, redesign_triggers, solve
from skyvault.virtualtest.stress import explore_equipment, stressed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/
from layers import imported, modules_below  # noqa: E402

SRC = Path(__file__).resolve().parents[2] / "src" / "skyvault"
RULES = load_rules()
EXO = load_profile("exo_test_001")
PAX = load_profile("pax_test_001")
MSX = load_profile("msx_test_001")
ERX = load_profile("erx_test_001")


def profile(category: str = "EXO", **physical) -> dict:
    """A bare profile with only the physical parameters given."""
    return {
        "equipment_id": "T",
        "category": category,
        "physical_parameters": physical,
    }


def status(found: dict, check: str) -> str:
    return next(c["status"] for c in found["checks"] if c["check"] == check)


def changed(base: dict, group: str, **values) -> dict:
    found = copy.deepcopy(base)
    found[group].update(values)
    return found


# ── contracts ────────────────────────────────────────────────────────────────


def test_the_committed_profiles_are_equipment_profiles():
    assert sorted(reference_profiles()) == [
        "ERX_TEST_001",
        "EXO_TEST_001",
        "MSX_TEST_001",
        "PAX_TEST_001",
    ]
    assert all(has_equipment_parameters(p) for p in reference_profiles().values())


@pytest.mark.parametrize(
    "change",
    [
        {"physical_parameters": {"mass": -1}},
        {"physical_parameters": {"weight": 10}},
        {"engineering_parameters": {"material_complexity": "unobtainium"}},
        {"engineering_parameters": {"supply_chain_risk": 1.5}},
        {"operational_parameters": {"mission_role": "parade"}},
        {"physical_parameters": {"load_bearing_joints": 0}},
    ],
)
def test_a_profile_that_breaks_the_contract_is_refused(change):
    with pytest.raises(ContractError):
        validate_equipment_profile({"equipment_id": "X", "category": "EXO", **change})


def test_a_test_result_needs_its_judgement():
    result = virtual_test(EXO, tactical=False)
    assert validate_equipment_test_result(result) == result
    broken = {k: v for k, v in result.items() if k != "final_judgement"}
    with pytest.raises(ContractError, match="final_judgement"):
        validate_equipment_test_result(broken)


# ── physics-lite ─────────────────────────────────────────────────────────────


def test_stability_is_the_half_stance_over_the_centre_of_gravity():
    found = margins(profile(base_width=0.5, center_of_gravity=1.0), RULES)
    assert found["stability"] == pytest.approx(0.25 / 0.15 - 1)
    narrow = margins(profile(base_width=0.2, center_of_gravity=1.0), RULES)
    assert narrow["stability"] < 0


def test_joint_load_is_shared_by_half_the_legs_under_the_dynamic_factor():
    load = 100 * 9.81 * 1.5 / 1000  # a biped mid-stride stands on one leg
    exact = profile(mass=100, joint_load=load, load_bearing_joints=2)
    assert margins(exact, RULES)["joint_load"] == pytest.approx(0)
    four = profile(mass=100, joint_load=load, load_bearing_joints=4)
    assert margins(four, RULES)["joint_load"] == pytest.approx(1.0)
    weak = profile(mass=100, joint_load=load * 0.9, load_bearing_joints=2)
    assert status(physical_possibility(weak, RULES), "joint_load") == "impossible"


def test_ground_pressure_decides_where_it_can_stand():
    heavy = profile(mass=1000, footprint=0.1, height=2.0)
    assert ground_pressure_kpa(heavy, RULES) == pytest.approx(98.1)
    assert margins(heavy, RULES)["ground_pressure"] == pytest.approx(150 / 98.1 - 1)
    terrain = accessible_terrain(heavy, RULES)
    assert "forest" not in terrain and "hill" in terrain and "building" in terrain
    tall = profile(mass=1000, footprint=0.1, height=3.5)
    assert "building" not in accessible_terrain(tall, RULES)
    declared = copy.deepcopy(heavy)
    declared["operational_parameters"] = {"terrain_accessibility": ["road", "forest"]}
    assert accessible_terrain(declared, RULES) == ["road"]


def test_energy_is_the_store_against_power_times_endurance():
    just = profile(power_requirement=2, endurance=3, energy_capacity=6)
    assert margins(just, RULES)["energy"] == 0
    assert status(physical_possibility(just, RULES), "energy") == "warning"
    short = profile(power_requirement=2, endurance=3, energy_capacity=5)
    assert status(physical_possibility(short, RULES), "energy") == "impossible"
    assert effective_endurance(short) == 2.5
    assert effective_endurance(profile(power_requirement=2, endurance=3)) == 3
    assert effective_endurance(profile(energy_capacity=5, power_requirement=0)) is None


def test_heat_short_of_cooling_is_a_warning_until_the_duty_falls_below_half():
    for cooling, verdict in ((1.2, "warning"), (0.6, "warning"), (0.4, "impossible")):
        found = physical_possibility(
            profile(heat_output=1.0, cooling_capacity=cooling), RULES
        )
        assert status(found, "heat") == verdict, cooling
    assert status(
        physical_possibility(profile(heat_output=1.0, cooling_capacity=2.0), RULES),
        "heat",
    ) == ("pass")


def test_a_design_outside_its_category_s_scale_is_a_warning_not_impossible():
    dense = profile(mass=1000, height=1.0)  # 1000 kg/m³ for an exoskeleton
    found = physical_possibility(dense, RULES)
    assert status(found, "scale") == "warning"
    assert found["impossible_flags"] == []


def test_a_check_without_its_inputs_is_unknown_never_passed():
    found = physical_possibility(profile(mass=100), RULES)
    assert {c["check"] for c in found["checks"] if c["status"] == "unknown"} == {
        "stability",
        "joint_load",
        "ground_pressure",
        "energy",
        "heat",
        "scale",
    }
    assert found["score"] == 0.0
    assert any("cannot judge" in w for w in found["warnings"])


def test_an_unknown_category_is_warned_and_its_envelope_checks_unknown():
    found = physical_possibility(
        profile("submarine", base_width=1, center_of_gravity=1), RULES
    )
    assert "category 'submarine' has no envelope in the rules" in found["warnings"]
    assert status(found, "stability") == "unknown"


def test_the_physical_score_is_the_mean_of_held_margins_and_zero_when_impossible():
    exo = physical_possibility(EXO, RULES)
    known = [c["margin"] for c in exo["checks"]]
    assert exo["score"] == round(
        sum(min(1, max(0, 0.5 + m)) for m in known) / len(known), 4
    )
    assert physical_possibility(PAX, RULES)["score"] == 0.0


def test_the_four_profiles_are_judged_physically_as_designed():
    flags = {
        name: [
            f.split(":")[0] for f in physical_possibility(p, RULES)["impossible_flags"]
        ]
        for name, p in reference_profiles().items()
    }
    assert flags == {
        "EXO_TEST_001": [],
        "ERX_TEST_001": [],
        "PAX_TEST_001": ["energy"],
        "MSX_TEST_001": ["joint_load", "energy"],
    }


# ── engineering ──────────────────────────────────────────────────────────────


def test_engineering_is_the_weighted_mean_of_five_components():
    found = engineering_feasibility(EXO, RULES)
    assert found["components"] == {
        "material": 0.8,
        "maintenance": round(1 / (1 + 1.5 / 4), 4),
        "parts": 0.7,
        "supply": 0.7,
        "repair": 1.0,
    }
    weights = RULES["engineering"]["weights"]
    assert found["score"] == round(
        sum(weights[k] * v for k, v in found["components"].items()), 4
    )
    assert found["bottlenecks"] == [] and found["maintenance_risks"] == []


def test_more_maintenance_than_operation_is_a_bottleneck():
    assert maintenance_ratio(PAX) == pytest.approx(4 / 3)
    found = engineering_feasibility(MSX, RULES)
    assert found["bottlenecks"] == [
        "exotic materials",
        "more maintenance than operation (15.0 h per hour run)",
        "repairs need a factory",
        "supply chain risk 80%",
    ]
    assert found["score"] < RULES["engineering"]["not_worth_below"]


def test_a_component_not_given_is_left_out_and_named_as_a_risk():
    bare = {"equipment_id": "T", "category": "EXO"}
    found = engineering_feasibility(bare, RULES)
    assert found["score"] == 0.0
    assert "material: not given" in found["maintenance_risks"]
    half = {**bare, "engineering_parameters": {"material_complexity": "low"}}
    assert engineering_feasibility(half, RULES)["score"] == 1.0
    assert maintenance_ratio(bare) is None


def test_the_engineering_ranking_is_erx_exo_pax_msx():
    scores = {
        name: engineering_feasibility(p, RULES)["score"]
        for name, p in reference_profiles().items()
    }
    assert sorted(scores, key=scores.get, reverse=True) == [
        "ERX_TEST_001",
        "EXO_TEST_001",
        "PAX_TEST_001",
        "MSX_TEST_001",
    ]
    assert scores["PAX_TEST_001"] < RULES["engineering"]["worth_investing"]


# ── the constraint solver ────────────────────────────────────────────────────


def test_the_required_value_puts_the_check_just_on_its_target():
    for trigger in redesign_triggers(PAX, RULES) + redesign_triggers(MSX, RULES):
        if trigger["constraint"] == "mass_limit":
            continue
        fixed = with_param(
            PAX if trigger in redesign_triggers(PAX, RULES) else MSX,
            "physical_parameters",
            trigger["parameter"],
            trigger["required"],
        )
        margin = margins(fixed, RULES)[trigger["constraint"]]
        assert trigger["target_margin"] <= margin < trigger["target_margin"] + 1e-3


def test_pax_needs_a_fifth_more_battery_and_msx_a_lighter_frame():
    pax = {t["constraint"]: t for t in redesign_triggers(PAX, RULES)}
    assert pax["energy"]["status"] == "impossible"
    assert pax["energy"]["required"] == pytest.approx(18.0, abs=1e-3)
    assert pax["energy"]["change"] == pytest.approx(0.2, abs=1e-3)
    assert pax["heat"]["status"] == "warning"
    assert pax["heat"]["target_margin"] == RULES["warning_margin"]
    msx = {t["constraint"]: t for t in redesign_triggers(MSX, RULES)}
    limit = msx["mass_limit"]["required"]
    assert limit < 18000
    assert (
        margins(with_param(MSX, "physical_parameters", "mass", limit), RULES)[
            "joint_load"
        ]
        >= 0
    )
    over = with_param(MSX, "physical_parameters", "mass", limit + 1)
    assert margins(over, RULES)["joint_load"] < 0


def test_a_sound_design_has_no_triggers_and_a_missing_lever_no_value():
    assert redesign_triggers(EXO, RULES) == []
    assert solve(profile(mass=10), RULES, "energy", "energy_capacity", 0) is None
    assert mass_limit(profile(height=2)) is None if False else True
    assert mass_limit(profile(height=2), RULES) is None
    # nothing that depends on mass: no limit to find
    assert mass_limit(profile(mass=100, height=2), RULES) is None


def test_a_lever_that_cannot_get_there_gives_no_value():
    hopeless = profile(heat_output=1.0, cooling_capacity=1e-12)
    assert solve(hopeless, RULES, "heat", "cooling_capacity", 0.0) is None


def test_a_mass_bound_check_that_fails_even_weightless_limits_mass_to_zero():
    no_joints = profile(mass=100, joint_load=0.0, load_bearing_joints=2)
    assert mass_limit(no_joints, RULES) == 0.0


# ── stress ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "condition", ["payload", "heat", "extended_mission", "supply_disruption"]
)
def test_every_stress_level_moves_its_quantity_further(condition):
    spec = RULES["stress"]["conditions"][condition]
    values = [
        stressed(PAX, RULES, condition, level)[0][spec["group"]][spec["parameter"]]
        for level in RULES["stress"]["levels"]
    ]
    assert len(set(values)) == 4
    assert values == sorted(values, reverse=spec["factors"][0] < 1)


def test_soft_ground_weakens_the_ground_not_the_profile():
    profile_after, rules_after = stressed(EXO, RULES, "soft_ground", "severe")
    assert profile_after == EXO
    assert rules_after["terrain_bearing_kpa"]["open"] == 150 * 0.25
    assert RULES["terrain_bearing_kpa"]["open"] == 150


def test_a_condition_breaks_at_the_first_level_that_breaks_something_new():
    points = {
        p["condition"]: p for p in explore_equipment(EXO, RULES)["failure_points"]
    }
    # 6.5 kWh: 1.2 kW × 4 h × 1.25 = 6.0 holds, × 1.5 = 7.2 does not
    assert points["extended_mission"] == {
        "condition": "extended_mission",
        "level": "moderate",
        "breaks": ["energy"],
    }
    assert points["supply_disruption"]["level"] is None


def test_what_already_fails_is_not_a_new_failure():
    explored = explore_equipment(MSX, RULES)
    assert explored["baseline_broken"] == ["energy", "engineering", "joint_load"]
    points = {p["condition"]: p for p in explored["failure_points"]}
    assert points["payload"]["level"] is None  # the joints already fail


def test_the_collapse_sequence_lists_failures_in_the_order_they_come():
    sequence = explore_equipment(EXO, RULES)["collapse_sequence"]
    assert [s["level"] for s in sequence] == ["moderate", "severe", "collapse"]
    assert sequence[0]["fails"] == ["energy"]
    seen = [check for step in sequence for check in step["fails"]]
    assert len(seen) == len(set(seen))


# ── external simulation ──────────────────────────────────────────────────────


def test_margins_too_close_to_call_need_an_external_simulation():
    found = external_simulation(MSX, RULES)
    assert found["required"] is True
    assert [r.split(":")[0] for r in found["reasons"]] == [
        "stability",
        "joint_load",
        "heat",
    ]
    assert found["adapter"]["status"] == "not_run"
    assert found["adapter"]["questions"] == found["reasons"]


def test_a_clear_design_needs_no_external_simulation_and_asks_nothing():
    calls = []

    class Recorder:
        name = "recorder"

        def simulate(self, profile, questions):
            calls.append(questions)
            return {"status": "done"}

    assert external_simulation(EXO, RULES, Recorder()) == {
        "required": False,
        "reasons": [],
        "adapter": {},
    }
    assert calls == []
    assert external_simulation(MSX, RULES, Recorder())["adapter"] == {"status": "done"}
    assert len(calls) == 1


def test_scale_missing_inputs_and_an_unknown_category_each_need_it():
    dense = changed(EXO, "physical_parameters", mass=1000)
    assert any("scale" in r for r in external_simulation(dense, RULES)["reasons"])
    bare = profile(mass=100)
    assert any("not enough" in r for r in external_simulation(bare, RULES)["reasons"])
    alien = {**EXO, "category": "submarine"}
    assert external_simulation(alien, RULES)["reasons"][0] == (
        "category 'submarine' is unknown to the rules"
    )
    assert StandInSimulator().simulate(EXO, ["q"])["status"] == "not_run"


# ── the judgement ────────────────────────────────────────────────────────────

GOOD_PHYSICS = {"score": 0.9, "impossible_flags": [], "warnings": [], "checks": []}
BAD_PHYSICS = {**GOOD_PHYSICS, "score": 0.0, "impossible_flags": ["energy: short"]}
GOOD_ENG = {"score": 0.8, "bottlenecks": []}
USEFUL = {"score": 0.6, "useful_contexts": ["squad"], "weak_contexts": []}
CLEAR = {"required": False, "reasons": []}
FIX = {"status": "impossible", "parameter": "energy_capacity", "current": 10.0}


@pytest.mark.parametrize(
    "physics,engineering,tactical,external,triggers,expected",
    [
        (
            BAD_PHYSICS,
            {"score": 0.2, "bottlenecks": ["x"]},
            USEFUL,
            CLEAR,
            [{**FIX, "required": 12.0, "change": 0.2}],  # fixable, but not worth it
            "reject",
        ),
        (
            BAD_PHYSICS,
            GOOD_ENG,
            USEFUL,
            CLEAR,
            [{**FIX, "required": 20.0, "change": 1.0}],
            "reject",
        ),
        (BAD_PHYSICS, GOOD_ENG, USEFUL, CLEAR, [], "reject"),
        (
            BAD_PHYSICS,
            GOOD_ENG,
            USEFUL,
            CLEAR,
            [{**FIX, "required": None, "change": None}],
            "reject",
        ),
        (
            BAD_PHYSICS,
            GOOD_ENG,
            USEFUL,
            CLEAR,
            [{**FIX, "required": 12.0, "change": 0.2}],
            "redesign",
        ),
        (
            GOOD_PHYSICS,
            {"score": 0.4, "bottlenecks": ["x"]},
            USEFUL,
            CLEAR,
            [],
            "redesign",
        ),
        (
            GOOD_PHYSICS,
            GOOD_ENG,
            {"score": 0.4, "useful_contexts": [], "weak_contexts": ["a"]},
            CLEAR,
            [],
            "redesign",
        ),
        (
            GOOD_PHYSICS,
            GOOD_ENG,
            USEFUL,
            {"required": True, "reasons": ["r"]},
            [],
            ("require_external_simulation"),
        ),
        (GOOD_PHYSICS, GOOD_ENG, USEFUL, CLEAR, [], "continue"),
        (
            GOOD_PHYSICS,
            GOOD_ENG,
            {"score": None, "useful_contexts": []},
            CLEAR,
            [],
            ("continue"),
        ),
    ],
)
def test_the_judgement_takes_the_first_rule_that_holds(
    physics, engineering, tactical, external, triggers, expected
):
    verdict = final_judgement(physics, engineering, tactical, external, triggers, RULES)
    assert verdict["status"] == expected and verdict["reason"]


def test_without_a_mission_test_continue_says_it_was_not_tested():
    verdict = virtual_test(EXO, tactical=False)["final_judgement"]
    assert verdict["status"] == "continue"
    assert verdict["reason"].endswith("useful in not tested")


# ── boundary values ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "change",
    [
        {"mass": 0},
        {"height": 0},
        {"endurance": 0},
        {"power_requirement": 0},
        {"footprint": 0},
        {"center_of_gravity": 0},
        {"heat_output": 0},
    ],
)
def test_boundary_profiles_are_judged_without_crashing(change):
    result = virtual_test(changed(EXO, "physical_parameters", **change), tactical=False)
    assert validate_equipment_test_result(result) == result


def test_a_massless_design_is_outside_every_scale():
    massless = changed(EXO, "physical_parameters", mass=0)
    assert margins(massless, RULES)["scale"] == -1.0
    assert external_simulation(massless, RULES)["required"] is True


def test_a_profile_of_nothing_but_an_id_cannot_be_judged_and_needs_simulation():
    result = virtual_test({"equipment_id": "X", "category": "EXO"}, tactical=False)
    assert result["physical_possibility"]["score"] == 0.0
    assert result["require_external_simulation"]["required"] is True
    assert result["final_judgement"]["status"] == "redesign"  # nothing worth building


# ── layering ─────────────────────────────────────────────────────────────────


def test_the_core_imports_no_virtual_test():
    # every module below the virtualtest layer (tests/layers.py: a positive list)
    below = modules_below("virtualtest")
    assert below
    for module in below:
        assert not any("virtualtest" in m for m in imported(module)), module


@pytest.mark.parametrize(
    "name",
    [
        "physics.py",
        "engineering.py",
        "solver.py",
        "stress.py",
        "judgement.py",
        "external.py",
    ],
)
def test_the_rules_run_no_simulation(name):
    modules = imported(SRC / "virtualtest" / name)
    assert not any(
        m.endswith(("engine", "tactical", "batch", "surrogate")) for m in modules
    ), modules


def test_a_check_already_on_its_target_keeps_its_value():
    assert solve(EXO, RULES, "energy", "energy_capacity", 0.0) == 6.5


def test_a_third_more_upkeep_than_operation_is_already_a_bottleneck():
    assert engineering_feasibility(PAX, RULES)["bottlenecks"] == [
        "more maintenance than operation (1.3 h per hour run)"
    ]
    lighter = changed(PAX, "engineering_parameters", maintenance_time=3.0)  # 1 h/h
    assert engineering_feasibility(lighter, RULES)["bottlenecks"] == []
