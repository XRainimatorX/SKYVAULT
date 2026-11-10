"""Acceptance: one core, many scenarios; a replaceable policy; the dataset."""

import ast
import copy
import json
import os
import subprocess
import sys
from collections import Counter

import pytest
from conftest import REPO_ROOT

from skyvault.batch.run import run_batch
from skyvault.domains.military import mission_outcome
from skyvault.domains.military.dataset import build_dataset, validate_record
from skyvault.domains.military.reference import reference_scenarios, scenario_path
from skyvault.engine import SkyVaultEngine
from skyvault.policies import build_policy, import_policy_module
from skyvault.scenario_loader import load_scenario

SCENARIOS = REPO_ROOT / "data" / "scenarios"
NAMES = ("squad", "urban", "mountain", "junction")


def scenario(name, version="v0.1"):
    return load_scenario(SCENARIOS / f"military_{name}_001" / f"{version}.json")


@pytest.fixture(scope="module")
def runs():
    return {name: SkyVaultEngine(scenario(name)).run() for name in NAMES}


# ── the reference scenarios ──────────────────────────────────────────────────


def test_committed_scenarios_are_exactly_what_the_specs_build():
    built = reference_scenarios()

    for name, expected in built.items():
        with scenario_path(name).open(encoding="utf-8") as file:
            assert json.load(file) == expected, f"{name} is stale: rebuild it"
    committed = {
        f"{path.parent.name}/{path.name}"
        for path in SCENARIOS.glob("military_*/*.json")
    }
    assert committed == set(built)


def test_a_revision_is_a_child_version_with_its_own_doctrine_variants():
    revised = scenario("urban", "v0.2")
    overwatch = scenario("urban", "v0.2+overwatch")

    assert revised["version_control"]["parent_version"] == "v0.1"
    changed = revised["version_control"]["changed_from_previous"]
    assert changed["failure_variables_changed"] and not changed["rules_changed"]
    assert revised["world_contract"]["failure_variables"] == (
        revised["failure_exploration"]["failure_variables"]
    )
    assert revised["failure_exploration"]["alternatives"] == [
        "v0.2+overwatch",
        "v0.2+defensive",
    ]
    assert overwatch["version_control"]["parent_version"] == "v0.2"
    assert overwatch["world_contract"]["failure_variables"] == (
        revised["world_contract"]["failure_variables"]
    )
    assert "failure_exploration" not in overwatch
    assert revised["entities"] == scenario("urban", "v0.1")["entities"]


def test_doctrine_variants_are_child_versions_of_the_urban_plan():
    defensive = scenario("urban", "v0.1+defensive")

    assert defensive["version_control"]["parent_version"] == "v0.1"
    assert defensive["version_control"]["changed_from_previous"]["rules_changed"] == [
        "world_contract.rule_set.military.factions.RED.doctrine: "
        "'aggressive' -> 'defensive'"
    ]


# ── acceptance 1: one core, many tactical scenarios ──────────────────────────


def test_the_same_engine_runs_every_tactical_scenario(runs):
    reference = SkyVaultEngine(
        load_scenario(
            REPO_ROOT
            / "tests"
            / "fixtures"
            / "reference"
            / "scenarios"
            / "tactical_reference_001"
            / "v0.1.json"
        )
    ).run()

    summaries = {
        name: (len(p["event_memory"]), p["reproducibility"]["output_hash"])
        for name, p in {**runs, "reference": reference}.items()
    }
    assert len({count for count, _ in summaries.values()}) == 5
    assert len({digest for _, digest in summaries.values()}) == 5
    assert summaries["reference"][0] == 97
    for package in runs.values():
        assert {"MOVE", "ATTACK", "MISS", "ENTITY_STATE_CHANGED"} <= {
            e["event_type"] for e in package["event_memory"]
        }


def test_military_runs_are_reproducible(runs):
    again = SkyVaultEngine(scenario("urban")).run()

    assert (
        again["reproducibility"]["output_hash"]
        == runs["urban"]["reproducibility"]["output_hash"]
    )


def test_every_reference_scenario_reports_a_mission_outcome(runs):
    outcomes = {name: mission_outcome(runs[name], scenario(name)) for name in NAMES}

    assert {name: sorted(o) for name, o in outcomes.items()} == {
        name: ["BLUE", "RED"] for name in NAMES
    }
    assert outcomes["junction"]["BLUE"]["type"] == "delay"
    assert outcomes["urban"]["RED"]["type"] == "seize"


# ── acceptance 2: TAC ANGEL replaces the baseline ────────────────────────────


def test_an_outside_policy_drives_a_military_scenario():
    import_policy_module(str(REPO_ROOT / "examples" / "tac_angel_policy.py"))
    squad = scenario("squad")
    squad["runtime"]["policy"] = {"name": "tac_angel_example"}

    package = SkyVaultEngine(squad).run()

    deciders = Counter(
        e["source"]["system_id"]
        for e in package["event_memory"]
        if e["event_type"] in ("ACTION_SELECTED", "NO_ACTION")
    )
    assert set(deciders) == {"TAC_ANGEL"}
    upkeep = {
        e["source"]["system_id"]
        for e in package["event_memory"]
        if e["event_type"] == "ENTITY_STATE_CHANGED" and "recovery" in e["tags"]
    }
    assert upkeep <= {"military_upkeep"}


def test_a_policy_module_can_be_named_by_module_path():
    import_policy_module("skyvault.actors.basic")

    assert build_policy("rule_based", __import__("random").Random(1))
    with pytest.raises(FileNotFoundError):
        import_policy_module(str(REPO_ROOT / "examples" / "missing_policy.py"))


# ── doctrine comparison ──────────────────────────────────────────────────────


def test_doctrines_are_compared_with_the_batch_runner():
    with (REPO_ROOT / "data" / "batches" / "military_doctrine.json").open() as file:
        request = json.load(file)

    result = run_batch(request, repeats=2, workers=1)

    assert result["branch_comparison"]["variants"] == [
        "aggressive",
        "overwatch",
        "defensive",
    ]
    assert result["batch_result"]["total_runs"] == 6
    assert {r["scenario_version"] for r in result["batch_result"]["runs"]} == {
        "v0.1",
        "v0.1+overwatch",
        "v0.1+defensive",
    }


# ── acceptance 3: the state-action-outcome dataset ───────────────────────────


@pytest.fixture(scope="module")
def dataset(runs):
    return build_dataset(runs["squad"], scenario("squad"))


def test_there_is_one_record_per_decision(runs, dataset):
    selected = [
        e for e in runs["squad"]["event_memory"] if e["event_type"] == "ACTION_SELECTED"
    ]

    assert len(dataset) == len(selected)
    assert [r["action"]["action_id"] for r in dataset] == [
        e["source"]["action_id"] for e in selected
    ]
    for record in dataset:
        assert validate_record(record) == record


def test_the_state_is_the_unit_as_it_was_when_it_decided(runs, dataset):
    first = next(r for r in dataset if r["actor"]["entity_id"] == "red_01")
    start = runs["squad"]["initial_world_state"]["entities"]["red_01"]

    assert first["state"]["position"] == start["position"]
    assert first["state"]["hp"] == start["state"]["hp"]
    assert first["state"]["terrain"] == "open"
    assert {a["entity_id"] for a in first["state"]["allies"]} == {
        "red_02",
        "red_03",
        "red_04",
    }


def test_seen_enemies_follow_the_sensor_rule(dataset):
    squad = scenario("squad")
    concealment = {
        name: t["concealment"]
        for name, t in squad["world_contract"]["rule_set"]["military"][
            "terrain"
        ].items()
    }
    sensor = {
        e["entity_id"]: e["capabilities"]["sensor_range"] for e in squad["entities"]
    }

    checked = 0
    for record in dataset:
        for contact in record["state"]["seen_enemies"]:
            reach = sensor[record["actor"]["entity_id"]] * (
                1 - concealment[contact["terrain"]]
            )
            assert contact["distance"] <= reach
            checked += 1
    assert checked > 0


def test_outcomes_say_what_came_of_each_decision(dataset):
    hits = [r for r in dataset if r["outcome"]["hit"] is True]
    misses = [r for r in dataset if r["outcome"]["hit"] is False]
    refused = [r for r in dataset if not r["outcome"]["accepted"]]

    assert hits and all(r["outcome"]["damage_dealt"] > 0 for r in hits)
    assert misses and all(r["outcome"]["damage_dealt"] == 0 for r in misses)
    assert refused and all(r["outcome"]["reason"] for r in refused)
    assert any(r["outcome"]["target_destroyed"] for r in hits)


def test_each_record_carries_its_episode_and_mission(runs, dataset):
    outcome = mission_outcome(runs["squad"], scenario("squad"))
    blue = next(r for r in dataset if r["actor"]["faction"] == "BLUE")

    assert blue["episode"]["mission_achieved"] is outcome["BLUE"]["achieved"]
    assert (
        blue["episode"]["output_hash"]
        == runs["squad"]["reproducibility"]["output_hash"]
    )


def test_a_malformed_record_is_refused(dataset):
    broken = copy.deepcopy(dataset[0])
    broken["state"]["mood"] = "fine"

    with pytest.raises(ValueError, match="mood"):
        validate_record(broken)


def test_the_export_is_identical_across_hash_seeds(tmp_path):
    outputs = []
    for seed in ("1", "2"):
        target = tmp_path / f"{seed}.jsonl"
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "dev" / "export_dataset.py"),
                "--runs",
                "2",
                "--scenario",
                str(SCENARIOS / "military_squad_001" / "v0.1.json"),
                "--output",
                str(target),
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(target.read_bytes())

    assert outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) > 100


def test_mission_and_dataset_never_run_a_simulation():
    pack = REPO_ROOT / "src" / "skyvault" / "domains" / "military"
    for module in ("mission.py", "dataset.py"):
        for node in ast.walk(ast.parse((pack / module).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module in ("typing", "pydantic", "mission", None) or (
                    node.level == 0 and not node.module.startswith("skyvault")
                ), (module, node.module)


def test_every_state_matches_the_engines_own_snapshot_of_the_decider(runs, dataset):
    # ACTION_SELECTED.before_state is the engine's copy of the actor at that moment
    selected = [
        e for e in runs["squad"]["event_memory"] if e["event_type"] == "ACTION_SELECTED"
    ]

    for record, event in zip(dataset, selected, strict=True):
        actor = event["before_state"]
        assert record["state"]["position"] == actor["position"]
        assert record["state"]["hp"] == actor["state"]["hp"]
        assert record["state"]["ammo"] == actor["state"]["ammo"]
        assert record["state"]["suppression"] == actor["state"]["suppression"]
    assert len({r["state"]["hp"] for r in dataset}) > 3  # states really change


def test_the_briefing_tells_a_military_run_in_plain_words(runs):
    from skyvault.report import build_briefing

    briefing = build_briefing({"result_package": runs["mountain"]})
    happened = next(p for p in briefing["sections"] if p["title"] == "What happened")
    text = "\n".join(happened["bullets"])

    assert "_" not in text  # no raw event type names
    assert "entity state" not in text  # ammunition and rally bookkeeping is not counted
    assert "refused order" in text and "idle unit" in text
    assert "Red 2nd squad Marksman destroyed by Blue Ridge Marksman" in text
