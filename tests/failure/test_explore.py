"""Exploring failures on the real engine: baseline, sweep, branch, alternatives."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
SCENARIOS = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_failure_map
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.failure import (
    build_collapse_sequence,
    build_failure_map,
    build_survival_conditions,
    explore_failures,
    render_recommended_modifications,
)
from skyvault.reproducibility import output_hash
from skyvault.scenario_loader import default_evaluation_profile, load_scenario

SMALL = {
    "objective": "find_weakness",
    "failure_variables": [
        "communication_failure",
        "weather_degradation",
        "equipment_overheat",
        "enemy_reaction_speed",
    ],
    "stress_levels": ["mild", "collapse"],
    "run_policy": {
        "repeat_count": 3,
        "random_seed_policy": "controlled_random",
        "branch_comparison": True,
    },
    "alternatives": ["v0.1-support-rear", "v0.1-spread"],
    "survival_threshold": 0.5,
}


def plan() -> dict:
    return load_scenario(SCENARIOS / "v0.1.json")


@pytest.fixture(scope="module")
def exploration():
    scenario = plan()
    return explore_failures(scenario, default_evaluation_profile(scenario), SMALL)


@pytest.fixture(scope="module")
def failure_map(exploration):
    return validate_failure_map(build_failure_map(exploration))


# ── acceptance 1: given a plan ───────────────────────────────────────────────


def test_the_plan_is_a_scenario_version_a_profile_and_a_perspective(exploration):
    assert exploration["scenario_version"] == "v0.1"
    assert exploration["profile_id"] == "balanced"
    assert exploration["perspective"] == "RED"
    assert exploration["seeds"] == [42, 43, 44]


def test_every_variable_runs_at_every_level_with_every_seed(exploration):
    for name in SMALL["failure_variables"]:
        entry = exploration["variables"][name]
        assert entry["applicable"]
        assert list(entry["levels"]) == ["mild", "collapse"]
        for level, runs in entry["levels"].items():
            assert [run["seed"] for run in runs] == [42, 43, 44]
            assert {run["scenario_version"] for run in runs} == {f"v0.1+{name}:{level}"}


def test_a_run_summary_matches_a_direct_engine_run(exploration):
    first = exploration["baseline"][0]
    package = SkyVaultTacticalReferenceEngine(plan()).run()

    assert first["seed"] == 42
    assert first["outcome"] == package["evaluation_result"]["winner_or_result"]
    assert first["output_hash"] == output_hash(package)
    assert first["losses"] == [{"tick": 6, "entity": "red_003", "by": "blue_002"}]


def test_the_default_request_is_the_scenarios_own():
    scenario = plan()
    scenario["failure_exploration"]["run_policy"]["repeat_count"] = 1
    scenario["failure_exploration"]["failure_variables"] = ["weather_degradation"]
    scenario["failure_exploration"]["stress_levels"] = ["mild"]
    scenario["failure_exploration"]["alternatives"] = []

    result = explore_failures(scenario, default_evaluation_profile(scenario))

    assert list(result["variables"]) == ["weather_degradation"]
    assert result["seeds"] == [42]


def test_fixed_seeds_repeat_the_same_run():
    scenario = plan()
    fixed = {**SMALL, "failure_variables": ["weather_degradation"], "alternatives": []}
    fixed["run_policy"] = {"repeat_count": 2, "random_seed_policy": "fixed"}

    result = explore_failures(scenario, default_evaluation_profile(scenario), fixed)

    first, second = result["baseline"]
    assert first["seed"] == second["seed"] == 42
    assert first["output_hash"] == second["output_hash"]


def test_a_variable_with_nothing_to_stress_is_reported_not_run():
    scenario = plan()
    scenario["world_contract"]["failure_variables"].append("supply_delay")
    request = {**SMALL, "failure_variables": ["supply_delay"], "alternatives": []}

    result = explore_failures(scenario, default_evaluation_profile(scenario), request)

    assert result["variables"]["supply_delay"] == {
        "applicable": False,
        "reason": "the world holds no resources",
        "assumption": "resource_model",
        "levels": {},
    }


# ── acceptance 2–5 on the failure map ────────────────────────────────────────


def test_the_map_says_where_the_plan_fails(failure_map):
    assert failure_map["failure_points"]
    assert all(
        "red_" in point and "lost at tick" in point
        for point in failure_map["failure_points"]
    )


def test_the_map_says_why_the_plan_fails(exploration, failure_map):
    failed = sum(
        not run["survived"]
        for entry in exploration["variables"].values()
        for runs in entry["levels"].values()
        for run in runs
    ) + sum(not run["survived"] for run in exploration["baseline"])
    failed += sum(not run["survived"] for run in exploration["branches"][0]["runs"])

    # In this exploration every failed run had mission_success at zero
    assert f"mission_success too low in {failed} of {failed} failed runs" in (
        failure_map["failure_causes"]
    )


def test_the_map_names_the_crushing_variable_and_its_assumption(failure_map):
    crushing = next(
        v
        for v in failure_map["variables"]
        if v["variable"] == failure_map["crushing_variable"]
    )

    assert crushing["sensitivity"] == max(
        v["sensitivity"] for v in failure_map["variables"]
    )
    assert crushing["sensitivity"] > 0
    assert failure_map["crushing_assumption"] == crushing["assumption"]


def test_the_branch_combines_the_two_most_damaging_variables(exploration, failure_map):
    [branch] = failure_map["branches"]
    ranked = sorted(
        failure_map["variables"], key=lambda v: v["sensitivity"], reverse=True
    )

    assert set(branch["variables"]) == {ranked[0]["variable"], ranked[1]["variable"]}
    assert branch["level"] == "mild"  # moderate is not among the tested levels
    assert len(exploration["branches"][0]["runs"]) == 3


def test_the_map_compares_both_alternatives(failure_map):
    versions = [a["scenario_version"] for a in failure_map["alternatives"]]

    assert versions == ["v0.1-support-rear", "v0.1-spread"]
    for alternative in failure_map["alternatives"]:
        assert set(alternative["breaking_levels"]) == set(SMALL["failure_variables"])
        assert alternative["verdict"] in {
            "holds_longer",
            "breaks_sooner",
            "mixed",
            "same",
        }


def test_every_output_is_built_from_the_exploration(exploration, failure_map):
    conditions = build_survival_conditions(failure_map)
    sequence = build_collapse_sequence(exploration)
    text = render_recommended_modifications(failure_map, conditions)

    assert set(conditions["per_variable"]) == set(SMALL["failure_variables"])
    assert sequence["scenario_id"] == "tactical_reference_001"
    assert text.startswith(
        "# Recommended modifications — tactical_reference_001 v0.1\n"
    )
    assert "## Must change before acting" in text
