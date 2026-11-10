"""Phase 8 acceptance 1: the same input gives the same result, bit for bit."""

import ast
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.reproducibility import (
    canonical_json,
    content_hash,
    input_hash,
    output_hash,
)
from skyvault.runtime.ids import IdSequence, RunIds
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_evaluation_profile, load_scenario

SCENARIOS = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001"
PROFILES = REPO_ROOT / "data" / "evaluation_profiles"


def run(version: str = "v0.1", seed: int | None = None) -> dict:
    scenario = load_scenario(SCENARIOS / f"{version}.json")
    if seed is not None:
        scenario["runtime"]["random_seed"] = seed
    return SkyVaultEngine(scenario).run()


def without_reproducibility(package: dict) -> dict:
    return {key: value for key, value in package.items() if key != "reproducibility"}


# ── deterministic ids ────────────────────────────────────────────────────────


def test_two_runs_of_the_same_input_are_identical():
    first, second = run(), run()

    assert without_reproducibility(first) == without_reproducibility(second)
    assert first["event_memory"][0]["event_id"] == "event_0000000001"
    assert first["event_memory"][-1]["event_id"] == "event_0000000097"


def test_ids_count_per_run_not_per_process():
    with (FIXTURES / "scenario_graph.json").open(encoding="utf-8") as file:
        scenario = validate_scenario(json.load(file))
    a, b = create_world(scenario), create_world(scenario)

    a.update_entity_state("convoy_1", {"status": "x"})
    a.update_entity_state("convoy_1", {"status": "y"})
    event = b.update_entity_state("convoy_1", {"status": "z"})

    assert event.event_id == "event_0000000001"
    assert a.event_memory[-1].event_id == "event_0000000002"


def test_an_id_sequence_keeps_the_phase_1_id_shape():
    sequence = IdSequence("event")
    ids = RunIds()

    assert [sequence.next(), sequence.next()] == [
        "event_0000000001",
        "event_0000000002",
    ]
    assert (ids.action(), ids.event(), ids.action()) == (
        "action_0000000001",
        "event_0000000001",
        "action_0000000002",
    )


def test_nothing_in_the_engine_draws_ids_from_uuid():
    for path in (SRC_PATH / "skyvault").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(alias.name != "uuid" for alias in node.names), path
            if isinstance(node, ast.ImportFrom):
                assert node.module != "uuid", path


# ── hashing ──────────────────────────────────────────────────────────────────


def test_canonical_json_ignores_key_order_and_keeps_characters():
    assert canonical_json({"b": 1, "a": [1, {"d": 2, "c": "é"}]}) == (
        '{"a":[1,{"c":"é","d":2}],"b":1}'
    )
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_changing_any_value_changes_the_hash():
    assert content_hash({"a": 1}) != content_hash({"a": 2})
    assert len(content_hash({})) == 64


def test_the_output_hash_ignores_only_the_reproducibility_block():
    package = {"event_memory": [1, 2], "reproducibility": {"run_id": "x"}}
    changed = {"event_memory": [1, 2], "reproducibility": {"run_id": "y"}}

    assert output_hash(package) == output_hash(changed)
    assert output_hash(package) != output_hash({"event_memory": [1, 3]})


def test_two_runs_have_the_same_output_hash_and_another_seed_does_not():
    assert output_hash(run()) == output_hash(run())
    assert output_hash(run()) != output_hash(run(seed=7))


@pytest.mark.parametrize("profile", ["balanced", "tactical"])
def test_the_profile_is_part_of_the_input(profile):
    scenario = load_scenario(SCENARIOS / "v0.1.json")
    chosen = load_evaluation_profile(PROFILES / f"{profile}.json")
    other = load_evaluation_profile(PROFILES / "balanced.json")
    other["profile_id"] = "renamed"

    assert input_hash(scenario, chosen) != input_hash(scenario, other)
    assert input_hash(scenario, chosen) == input_hash(scenario, dict(chosen))
