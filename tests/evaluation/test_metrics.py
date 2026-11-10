"""The eleven evaluation axes and the evaluation profile contract."""

import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
PROFILES = REPO_ROOT / "data" / "evaluation_profiles"

for path in (SRC_PATH, REPO_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from reference_trace import reference_package  # noqa: E402

from skyvault.action import Action, ActionTarget
from skyvault.actions import CORE_HANDLERS, ActionContext, ActionResolver
from skyvault.contracts import (
    METRIC_NAMES,
    ContractError,
    validate_evaluation_profile,
    validate_scenario,
)
from skyvault.evaluation import METRIC_REGISTRY, EvaluationContext
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_evaluation_profile


@pytest.fixture(scope="module")
def package():
    return reference_package()


def scores(package, perspective):
    context = EvaluationContext.build(
        package["initial_world_state"],
        package["event_memory"],
        package["final_world_state"],
        perspective,
        10,
    )
    return {name: metric.compute(context) for name, metric in METRIC_REGISTRY.items()}


def test_the_registry_holds_the_eleven_plan_axes():
    assert tuple(METRIC_REGISTRY) == METRIC_NAMES
    assert len(METRIC_REGISTRY) == 11


# Hand-computed from the reference run: RED dealt 111 damage against 97 BLUE hp,
# lost 40 of its own 97 hp (red_002 10, red_003 all 30), lost red_003 at tick 6
# and was never refused an action. 4 of 6 entities were destroyed.
RED_EXPECTED = {
    "mission_success": (3, 1.0),
    "tactical_value": (111, 1.0),
    "strategic_value": (2, 2 / 3),
    "resource_cost": (40, 1 - 40 / 97),
    "time_cost": (10, 0.0),
    "risk_growth": (1, 2 / 3),
    "failure_resistance": (6, 0.6),
    "recovery_ability": (0, 0.0),
    "system_robustness": (0, 1.0),
    "stability_impact": (4, 1 / 3),
}


@pytest.mark.parametrize("name", sorted(RED_EXPECTED))
def test_each_axis_matches_the_hand_computed_red_value(package, name):
    value = scores(package, "RED")[name]
    raw, score = RED_EXPECTED[name]

    assert value.applicable
    assert value.raw == raw
    assert value.score == pytest.approx(score)


def test_an_axis_without_data_is_not_applicable(package):
    value = scores(package, "RED")["logistics_burden"]

    assert not value.applicable
    assert value.score == 0.0
    assert "no resources" in value.explanation


def test_the_losing_side_scores_zero_mission_success(package):
    blue = scores(package, "BLUE")

    assert blue["mission_success"].score == 0.0
    assert blue["tactical_value"].raw == 53
    assert blue["resource_cost"].score == 0.0
    assert blue["risk_growth"].score == 0.0


def test_negative_hp_never_counts_as_more_than_everything():
    context = EvaluationContext.build(
        {
            "tick": 0,
            "entities": {
                "a": {"faction": "A", "state": {"hp": 10, "status": "active"}}
            },
        },
        [],
        {
            "tick": 1,
            "entities": {
                "a": {"faction": "A", "state": {"hp": -50, "status": "destroyed"}}
            },
        },
        "A",
        5,
    )

    assert context.hp_lost("a") == 10


def test_no_loss_means_full_failure_resistance_and_untested_recovery():
    state = {
        "tick": 0,
        "entities": {"a": {"faction": "A", "state": {"hp": 5, "status": "active"}}},
    }
    context = EvaluationContext.build(state, [], {**state, "tick": 3}, "A", 5)

    assert METRIC_REGISTRY["failure_resistance"].compute(context).score == 1.0
    assert not METRIC_REGISTRY["recovery_ability"].compute(context).applicable
    assert not METRIC_REGISTRY["mission_success"].compute(context).applicable


def test_repairs_and_spending_are_measured_on_a_logistics_run():
    with (FIXTURES / "scenario_logistics.json").open(encoding="utf-8") as file:
        world = create_world(validate_scenario(json.load(file)))
    initial = world.snapshot()
    resolver = ActionResolver(CORE_HANDLERS, ActionContext(random.Random(0)))
    world.get_entity("squad_1").state["hp"] = 8
    for action in (
        Action("a1", "truck_1", "repair", ActionTarget(entity_id="squad_1")),
        Action(
            "a2",
            "truck_1",
            "supply",
            ActionTarget(entity_id="squad_1"),
            required_resources={"fuel": 10},
        ),
    ):
        assert resolver.execute(world, action).accepted
    events = [event.to_dict() for event in world.event_memory]

    context = EvaluationContext.build(initial, events, world.snapshot(), "BLUE", 10)

    recovery = METRIC_REGISTRY["recovery_ability"].compute(context)
    logistics = METRIC_REGISTRY["logistics_burden"].compute(context)
    assert recovery.raw == 5
    assert recovery.score == 1.0  # squad_1 ends above where it started
    assert logistics.raw == 11  # 1 spare part for the repair, 10 fuel delivered
    assert logistics.score == pytest.approx(1 - 11 / 54)


# ── the evaluation profile contract ──────────────────────────────────────────


def profile_fixture() -> dict:
    with (FIXTURES / "evaluation_profile_valid.json").open(encoding="utf-8") as file:
        return json.load(file)


def test_the_profile_fixture_validates_unchanged():
    profile = profile_fixture()

    assert validate_evaluation_profile(profile) == profile
    assert "pass" in validate_evaluation_profile(profile)["thresholds"]


@pytest.mark.parametrize("name", ["balanced", "tactical"])
def test_the_shipped_profiles_load(name):
    profile = load_evaluation_profile(PROFILES / f"{name}.json")

    assert profile["profile_id"] == name
    assert profile["perspective"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p["weights"].update({"charisma": 1}), "unknown metrics"),
        (lambda p: p.update({"primary_metric": "luck"}), "unknown metrics"),
        (lambda p: p["thresholds"].update({"fail": 0.9}), "cannot be above"),
        (lambda p: p.update({"weights": {"time_cost": 0}}), "positive weight"),
        (
            lambda p: p.update({"forbidden_optimization_behaviors": ["cheating"]}),
            "unknown optimisation",
        ),
        (
            lambda p: p["anti_gaming_metrics"][0].update({"metric": "x"}),
            "unknown anti-gaming",
        ),
        (lambda p: p["weights"].update({"time_cost": -1}), "greater than or equal"),
    ],
)
def test_a_broken_profile_is_rejected(change, message):
    profile = profile_fixture()
    change(profile)

    with pytest.raises(ContractError) as caught:
        validate_evaluation_profile(profile)

    assert message in " | ".join(caught.value.errors)


def test_a_profile_file_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError, match="Evaluation profile file not found"):
        load_evaluation_profile(tmp_path / "missing.json")


def test_a_profile_can_be_written_in_yaml(tmp_path):
    import yaml

    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(profile_fixture()), encoding="utf-8")

    assert load_evaluation_profile(path)["profile_id"] == "fixture_balanced_red"
