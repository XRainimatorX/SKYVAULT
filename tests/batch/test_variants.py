"""Batch variants and outside orders scheduled into a run."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
SCENARIOS = REPO_ROOT / "data" / "scenarios"
BATCH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "reference"
    / "batches"
    / "tactical_reference_001.json"
)

for path in (SRC_PATH, REPO_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from reference_trace import trace  # noqa: E402

from skyvault.batch.variants import branch_variant, build_variants, set_parameter
from skyvault.contracts import ContractError, validate_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario


def batch() -> dict:
    with BATCH.open(encoding="utf-8") as file:
        return json.load(file)


def plan() -> dict:
    return load_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "reference"
        / "scenarios"
        / "tactical_reference_001"
        / "v0.1.json"
    )


def proposals(*ids):
    found = {p["proposal_id"]: p for p in batch()["conflicts"]["proposals"]}
    return [found[i] for i in ids]


def entity(scenario, entity_id):
    return next(e for e in scenario["entities"] if e["entity_id"] == entity_id)


# ── set_parameter ────────────────────────────────────────────────────────────


def test_a_parameter_is_set_by_the_path_compare_scenarios_prints():
    original = plan()

    changed = set_parameter(original, "entities[blue_002].capabilities.accuracy", 0.65)

    assert entity(changed, "blue_002")["capabilities"]["accuracy"] == 0.65
    assert entity(original, "blue_002")["capabilities"]["accuracy"] == 0.55
    assert (
        set_parameter(original, "runtime.max_ticks", 12)["runtime"]["max_ticks"] == 12
    )


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("entities[ghost].capabilities.accuracy", "no entity 'ghost'"),
        ("entities[blue_002].capabilities.charisma", "'charisma' not found"),
        ("entities[blue_002]", "must end at a value"),
        ("runtime.speed", "'speed' not found"),
        ("runtime.max ticks", "bad path segment"),
    ],
)
def test_a_wrong_path_raises_instead_of_adding_a_key(path, message):
    with pytest.raises(KeyError, match=message):
        set_parameter(plan(), path, 1)


# ── building variants ────────────────────────────────────────────────────────


def test_the_reference_batch_builds_three_versions_and_three_sweep_points():
    variants = build_variants(batch(), SCENARIOS)

    assert [(v.variant_id, v.kind) for v in variants] == [
        ("plan", "version"),
        ("support-rear", "version"),
        ("spread", "version"),
        ("sweep:entities[blue_002].capabilities.accuracy=0.55", "sweep"),
        ("sweep:entities[blue_002].capabilities.accuracy=0.65", "sweep"),
        ("sweep:entities[blue_002].capabilities.accuracy=0.75", "sweep"),
    ]
    for variant in variants:
        validate_scenario(variant.scenario)


def test_a_sweep_point_is_a_child_version_of_the_base():
    point = build_variants(batch(), SCENARIOS)[4].scenario

    assert point["scenario_version"] == (
        "v0.1+sweep:entities[blue_002].capabilities.accuracy=0.65"
    )
    assert point["version_control"]["parent_version"] == "v0.1"
    assert point["version_control"]["changed_from_previous"]["data_changed"] == [
        "entities[blue_002].capabilities.accuracy: 0.55 -> 0.65"
    ]


def test_a_request_without_sweeps_or_versions_builds_nothing():
    bare = {k: v for k, v in batch().items() if k not in ("variants", "sweeps")}

    assert build_variants(bare, SCENARIOS) == []


# ── branches and scheduled orders ────────────────────────────────────────────


def test_a_branch_schedules_its_orders_and_keeps_their_ids():
    variant = branch_variant(plan(), "P2+P3", proposals("P2", "P3"))

    scheduled = variant.scenario["runtime"]["scheduled_actions"]
    assert variant.variant_id == "branch:P2+P3"
    assert [s["metadata"]["proposal_id"] for s in scheduled] == ["P2", "P3"]
    assert (
        variant.scenario["version_control"]["change_reason"] == "Batch branch: P2, P3"
    )
    validate_scenario(variant.scenario)


def test_the_baseline_branch_schedules_nothing():
    variant = branch_variant(plan(), "none", [])

    assert "scheduled_actions" not in variant.scenario["runtime"]
    assert (
        variant.scenario["version_control"]["changed_from_previous"]["rules_changed"]
        == []
    )


def run(scenario):
    return SkyVaultEngine(scenario).run()


def test_a_scheduled_order_replaces_the_policy_and_carries_its_system():
    package = run(branch_variant(plan(), "P1", proposals("P1")).scenario)

    tick_one = [
        e
        for e in package["event_memory"]
        if e["time"] == 1 and e["source"]["actor_id"] == "red_002"
    ]
    selected, moved = tick_one[0], tick_one[1]
    assert selected["event_type"] == "ACTION_SELECTED"
    assert selected["source"]["system_id"] == "TAC_ANGEL"
    assert selected["data"]["intent"] == "advance the support team"
    assert moved["event_type"] == "MOVE"
    assert moved["source"]["system_id"] == "TAC_ANGEL"
    assert moved["data"] == {"from": [1, 0], "to": [1, 1]}


def test_two_orders_for_different_actors_both_run():
    package = run(branch_variant(plan(), "P2+P3", proposals("P2", "P3")).scenario)

    moves = {
        e["source"]["actor_id"]: e["data"]["to"]
        for e in package["event_memory"]
        if e["time"] == 1 and e["event_type"] == "MOVE"
    }
    assert moves["red_001"] == [1, 1]
    assert moves["red_002"] == [0, 1]


def test_without_scheduled_orders_nothing_changes():
    assert trace(run(branch_variant(plan(), "none", []).scenario)) == trace(run(plan()))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda o: o.update({"actor_id": "ghost"}), "unknown actor"),
        (lambda o: o.update({"tick": 99}), "after max_ticks"),
    ],
)
def test_a_scheduled_order_must_fit_the_run(change, message):
    scenario = branch_variant(plan(), "P1", proposals("P1")).scenario
    change(scenario["runtime"]["scheduled_actions"][0])

    with pytest.raises(ContractError, match=message):
        validate_scenario(scenario)


def test_one_actor_cannot_have_two_orders_in_one_tick():
    scenario = branch_variant(plan(), "P1+P2", proposals("P1", "P2")).scenario

    with pytest.raises(ContractError, match="two scheduled actions at tick 1"):
        validate_scenario(scenario)
