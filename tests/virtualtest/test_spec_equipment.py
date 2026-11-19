"""Formal Spec 18.2 equipment_profile and 18.3 equipment_test_result, field by field."""

from skyvault.virtualtest.profile import load_profile
from skyvault.virtualtest.run import virtual_test

SECTION_18_2 = {
    "physical_parameters": {
        "mass",
        "height",
        "center_of_gravity",
        "joint_load",
        "power_requirement",
        "heat_output",
        "endurance",
    },
    "engineering_parameters": {
        "material_complexity",
        "maintenance_time",
        "part_replacement_difficulty",
        "supply_chain_risk",
        "repair_environment_required",
    },
    "operational_parameters": {
        "operator_fatigue",
        "terrain_accessibility",
        "transport_requirement",
        "deployment_time",
        "mission_role",
    },
}
SECTION_18_3 = {
    "physical_possibility": {"score", "warnings", "impossible_flags"},
    "engineering_feasibility": {"score", "bottlenecks", "maintenance_risks"},
    "tactical_usefulness": {
        "score",
        "useful_contexts",
        "weak_contexts",
        "logistics_burden",
    },
    "failure_exploration": {"failure_points", "collapse_sequence", "redesign_triggers"},
    "final_judgement": {"status", "reason"},
}


def test_the_reference_msx_profile_carries_every_section_18_2_field():
    profile = load_profile("msx_test_001")

    assert profile["equipment_id"] == "MSX_TEST_001" and profile["category"] == "MSX"
    for group, fields in SECTION_18_2.items():
        assert fields <= set(profile[group]), group
    assert {
        "movement_viability",
        "energy_burden",
        "maintenance_pressure",
        "mission_value",
    } <= set(profile["test_targets"])


def test_a_test_result_carries_every_section_18_3_field_and_a_spec_verdict():
    result = virtual_test(load_profile("exo_test_001"))

    assert result["equipment_id"] == "EXO_TEST_001"
    for group, fields in SECTION_18_3.items():
        assert fields <= set(result[group]), group
    assert result["final_judgement"]["status"] in {
        "continue",
        "redesign",
        "reject",
        "require_external_simulation",
    }
