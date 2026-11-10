"""The training pipeline: transitions, labels, the anti-gaming filter, exports."""

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
SCENARIOS = REPO_ROOT / "data" / "scenarios"
BATCHES = REPO_ROOT / "data" / "batches"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.batch.run import run_batch
from skyvault.engine import SkyVaultEngine
from skyvault.failure import apply_stress
from skyvault.scenario_loader import load_scenario
from skyvault.training.branches import branch_evaluation
from skyvault.training.export import (
    read_jsonl,
    read_parquet,
    write_jsonl,
    write_parquet,
)
from skyvault.training.filter import anti_gaming_report, bucket_of, split_runs
from skyvault.training.labels import BEHAVIOR_LABELS, LABELS, run_labels
from skyvault.training.pipeline import build_training_data
from skyvault.training.rag import build_rag_index, query, tokens
from skyvault.training.records import validate_transition
from skyvault.training.registry import TrainingRegistry, dataset_id
from skyvault.training.transitions import build_transitions


def run(path, seed=None, stress=None):
    scenario = load_scenario(SCENARIOS / path)
    if stress:
        scenario = apply_stress(scenario, stress, "RED")
    if seed is not None:
        scenario["runtime"]["random_seed"] = seed
    return SkyVaultEngine(scenario).run(), scenario


@pytest.fixture(scope="module")
def reference():
    return run(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "reference"
        / "scenarios"
        / "tactical_reference_001/v0.1.json"
    )


@pytest.fixture(scope="module")
def urban():
    return run("military_urban_001/v0.1.json")


@pytest.fixture(scope="module")
def stressed():
    return run(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "reference"
        / "scenarios"
        / "tactical_reference_001/v0.1.json",
        stress={"communication_failure": "severe"},
    )


def decisions(package):
    return [e for e in package["event_memory"] if e["event_type"] == "ACTION_SELECTED"]


# ── acceptance 1: a transition per decision, on every kind of run ────────────


@pytest.mark.parametrize("kind", ["reference", "urban", "stressed"])
def test_every_decision_becomes_a_transition(kind, request):
    package, scenario = request.getfixturevalue(kind)

    transitions = build_transitions(package, scenario)

    assert [t["action"]["action_id"] for t in transitions] == [
        e["source"]["action_id"] for e in decisions(package)
    ]
    for record in transitions:
        assert validate_transition(record) == record
        assert {
            "state",
            "observation",
            "action",
            "consequence",
            "reward",
            "next_state",
            "event_sequence",
            "failure_labels",
            "scenario",
        } <= set(record)


def test_state_and_next_state_are_the_engines_snapshots(reference):
    package, scenario = reference
    transitions = build_transitions(package, scenario)
    events = decisions(package)

    for i, (record, event) in enumerate(zip(transitions, events, strict=True)):
        assert record["state"] == event["before_state"]
        actor = event["source"]["actor_id"]
        later = [e for e in events[i + 1 :] if e["source"]["actor_id"] == actor]
        expected = (
            later[0]["before_state"]
            if later
            else package["final_world_state"]["entities"][actor]
        )
        assert record["next_state"] == expected
        assert record["done"] == (
            not later or expected["state"]["status"] == "destroyed"
        )


def test_rewards_count_damage_given_taken_and_losses(reference):
    package, scenario = reference
    transitions = build_transitions(package, scenario)

    for record in transitions:
        dealt = sum(
            e["data"].get("damage", 0)
            for e in record["consequence"]["events"]
            if e["event_type"] == "ATTACK"
        )
        assert record["reward"]["damage_dealt"] == dealt
        before = record["state"]["state"]["hp"]
        after = max(0, record["next_state"]["state"]["hp"])
        assert record["reward"]["damage_taken"] == before - after
        assert record["reward"]["episode_score"] == 0.5045
    killers = [t for t in transitions if t["reward"]["target_destroyed"]]
    lost = [t for t in transitions if t["reward"]["own_destroyed"]]
    assert len(killers) == 4
    assert {t["action"]["actor_id"] for t in lost} == {
        "red_003",
        "blue_001",
        "blue_002",
        "blue_003",
    }


def test_the_event_sequence_is_the_decision_and_what_it_caused(reference):
    package, scenario = reference
    record = next(
        t
        for t in build_transitions(package, scenario)
        if t["reward"]["target_destroyed"]
    )
    by_id = {e["event_id"]: e for e in package["event_memory"]}

    types = [by_id[i]["event_type"] for i in record["event_sequence"]]
    assert types == ["ACTION_SELECTED", "ATTACK", "ENTITY_DESTROYED"]


def test_a_refused_order_says_why(urban):
    package, scenario = urban
    refused = [
        t
        for t in build_transitions(package, scenario)
        if not t["consequence"]["accepted"]
    ]

    assert refused
    assert all(t["consequence"]["reason"] for t in refused)


def test_the_observation_comes_from_the_domain_or_is_labelled_full(reference, urban):
    full = build_transitions(*reference)[0]["observation"]
    sensed = build_transitions(*urban)[0]["observation"]

    assert full["observation_model"] == "full_state"
    assert len(full["units"]) == 6
    assert sensed["observation_model"] == "military_sensor"
    assert set(sensed) == {"observation_model", "seen_enemies", "allies"}


def test_the_scenario_metadata_names_the_run_by_its_hashes(reference):
    package, scenario = reference

    meta = build_transitions(package, scenario)[0]["scenario"]

    assert meta["input_hash"] == package["reproducibility"]["input_hash"]
    assert meta["output_hash"] == package["reproducibility"]["output_hash"]
    assert (meta["domain"], meta["seed"], meta["perspective"]) == (None, 42, "RED")


# ── labels, acceptance 4 and 6 ───────────────────────────────────────────────


def rigged(package, triggered=(), flagged=(), winner=None, status=None, mission=None):
    changed = copy.deepcopy(package)
    report = changed["anti_gaming_report"]
    report["triggered_behaviors"] = list(triggered)
    report["flagged_behaviors"] = list(flagged)
    report["gaming_detected"] = bool(flagged)
    evaluation = changed["evaluation_result"]
    if winner is not None:
        evaluation["winner_or_result"] = winner
    if status is not None:
        evaluation["overall_judgement"]["status"] = status
    if mission is not None:
        evaluation["scores"]["mission_success"] = mission
    return changed


@pytest.mark.parametrize(("behavior", "label"), list(BEHAVIOR_LABELS.items()))
def test_each_check_sets_its_label_and_a_flag_makes_it_a_violation(
    reference, behavior, label
):
    package, scenario = reference

    clear = run_labels(rigged(package), scenario)
    seen = run_labels(rigged(package, triggered=[behavior]), scenario)
    flagged = run_labels(rigged(package, [behavior], [behavior]), scenario)

    assert clear["labels"][label] is False
    assert seen["labels"][label] is True and label not in seen["violations"]
    assert label in flagged["violations"]


def test_a_success_without_the_mission_is_misaligned(reference):
    package, scenario = reference

    aligned = run_labels(rigged(package, winner="RED_survived", mission=0.6), scenario)
    misaligned = run_labels(
        rigged(package, winner="RED_survived", mission=0.4), scenario
    )
    not_a_success = run_labels(
        rigged(package, winner="BLUE_survived", status="fail", mission=0.0), scenario
    )

    assert aligned["labels"]["strategic_misalignment_label"] is False
    assert misaligned["labels"]["strategic_misalignment_label"] is True
    assert misaligned["violations"] == ["strategic_misalignment_label"]
    assert not_a_success["labels"]["strategic_misalignment_label"] is False


def test_a_domain_judges_the_mission_itself(urban):
    package, scenario = urban
    # A perfect mission_success axis cannot hide that RED never took the courtyard
    pretend = rigged(package, winner="RED_survived", mission=1.0)

    labels = run_labels(pretend, scenario)

    assert labels["mission_achieved"] is False
    assert labels["labels"]["strategic_misalignment_label"] is True


@pytest.mark.parametrize(
    ("changes", "success_type"),
    [
        ({"winner": "RED_survived", "mission": 1.0}, "genuine_success"),
        ({"winner": "draw", "status": "pass", "mission": 1.0}, "genuine_success"),
        (
            {
                "winner": "RED_survived",
                "mission": 1.0,
                "triggered": ["maximize_score_by_inaction"],
                "flagged": ["maximize_score_by_inaction"],
            },
            "false_success",
        ),
        ({"winner": "no_winner_duration_limit", "status": "fail"}, "failure"),
    ],
)
def test_success_false_success_and_failure_are_told_apart(
    reference, changes, success_type
):
    package, scenario = reference

    assert (
        run_labels(rigged(package, **changes), scenario)["success_type"] == success_type
    )


# ── the filter, acceptance 5 ─────────────────────────────────────────────────


def test_each_run_goes_to_one_bucket_for_a_stated_reason(reference):
    package, scenario = reference
    flagged = rigged(
        package, ["maximize_score_by_inaction"], ["maximize_score_by_inaction"]
    )
    risky = rigged(package, status="risky")
    failed = rigged(package, status="fail")

    assert bucket_of(flagged, run_labels(flagged, scenario)) == (
        "rejected",
        "violations: inaction_gaming_label",
    )
    assert bucket_of(risky, run_labels(risky, scenario))[0] == "risky"
    assert bucket_of(failed, run_labels(failed, scenario)) == (
        "clean",
        "no violation; verdict fail",
    )


@pytest.fixture(scope="module")
def mixed_runs(reference, urban, stressed):
    extra = [
        run(
            REPO_ROOT
            / "tests"
            / "fixtures"
            / "reference"
            / "scenarios"
            / "tactical_reference_001/v0.1.json",
            seed=s,
        )
        for s in (43, 44, 45, 46)
    ]
    return [reference, urban, stressed, *extra]


def test_no_transition_of_a_rejected_run_reaches_the_clean_set(mixed_runs):
    split = split_runs(mixed_runs)
    report = anti_gaming_report(mixed_runs)

    rejected = {
        e["output_hash"] for e in report["entries"] if e["bucket"] == "rejected"
    }
    assert rejected  # the guard is exercised
    assert not {t["scenario"]["output_hash"] for t in split["clean"]} & rejected
    assert all(t["violations"] for t in split["rejected"])
    assert not any(t["violations"] for t in split["clean"] + split["risky"])
    total = sum(len(decisions(p)) for p, _ in mixed_runs)
    assert sum(len(rows) for rows in split.values()) == total


def test_the_report_counts_labels_and_explains_every_run(mixed_runs):
    report = anti_gaming_report(mixed_runs)

    assert report["runs"] == 7
    assert sum(report["buckets"].values()) == 7
    assert set(report["label_counts"]) == set(LABELS)
    for entry in report["entries"]:
        assert entry["reason"]
        assert set(entry["violations"]) <= set(entry["labels"])
    assert report["entries"][0]["violations"] == ["stability_damage_label"]


# ── STARTX branch evaluation, acceptance 3 ───────────────────────────────────


def test_branches_and_variants_become_evaluation_records():
    with (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "reference"
        / "batches"
        / "tactical_reference_001.json"
    ).open() as file:
        request = json.load(file)
    result = run_batch(request, repeats=2)

    records = branch_evaluation(
        result["batch_result"], result["branch_comparison"], result["conflict_package"]
    )

    variants = [r for r in records if r["record_type"] == "variant"]
    branches = [r for r in records if r["record_type"] == "branch"]
    assert [r["variant_id"] for r in variants] == result["branch_comparison"][
        "variants"
    ]
    assert sorted(r["rank"] for r in variants) == list(range(1, 10))
    assert variants[0]["delta_vs_first"]["mean_score"] == 0.0
    assert [r["branch_id"] for r in branches] == ["P1", "P2+P3", "none"]
    assert all(r["required_decision"] for r in branches)
    best = result["branch_comparison"]["best"]["mean_score"]
    assert (
        "mean_score" in next(r for r in variants if r["variant_id"] == best)["best_at"]
    )


def test_a_batch_without_conflicts_gives_only_variant_records():
    with (BATCHES / "military_doctrine.json").open() as file:
        request = json.load(file)
    result = run_batch(request, repeats=1)

    records = branch_evaluation(result["batch_result"], result["branch_comparison"])

    assert [r["variant_id"] for r in records] == [
        "aggressive",
        "overwatch",
        "defensive",
    ]


# ── export, registry, RAG index ──────────────────────────────────────────────


def test_jsonl_and_parquet_give_back_the_same_records(tmp_path, reference):
    rows = build_transitions(*reference)[:5] + [{"only": None, "nested": {"a": [1]}}]

    write_jsonl(tmp_path / "rows.jsonl", rows)
    write_parquet(tmp_path / "rows.parquet", rows)

    assert read_jsonl(tmp_path / "rows.jsonl") == rows
    assert read_parquet(tmp_path / "rows.parquet") == rows


def test_the_registry_names_a_dataset_by_its_content(tmp_path):
    registry = TrainingRegistry(tmp_path / "registry.jsonl")
    first = dataset_id("set", {"clean": "a\n"})

    registry.record({"dataset_id": first, "records": 1})
    registry.record({"dataset_id": first, "records": 2})

    assert dataset_id("set", {"clean": "a\n"}) == first
    assert dataset_id("set", {"clean": "b\n"}) != first
    assert len(registry.all()) == 2
    assert registry.get(first)["records"] == 2
    with pytest.raises(KeyError):
        registry.get("set-0000")
    assert TrainingRegistry(tmp_path / "none.jsonl").all() == []


def test_the_rag_index_finds_runs_by_what_happened():
    documents = [
        {"doc_id": "a", "text": "urban seize failure risk_spike_label"},
        {"doc_id": "b", "text": "reference stability_damage_label false_success"},
        {"doc_id": "c", "text": "reference stability damage clean"},
    ]
    index = build_rag_index(documents)

    hits = query(index, "stability damage reference", k=2)

    assert tokens("risk_spike_label!") == ["risk", "spike", "label"]
    assert [h["doc_id"] for h in hits] == ["b", "c"]  # equal match: index order
    assert hits[0]["matched_tokens"] == 3
    assert query(index, "nothing matches", k=3) == []


# ── the pipeline, end to end ─────────────────────────────────────────────────

SMALL = {
    "dataset": "test_training",
    "profile": "balanced",
    "seeds": 2,
    "runs": [
        {"scenario": "tactical_reference_001/v0.1"},
        {
            "scenario": "tactical_reference_001/v0.1",
            "stress": {"weather_degradation": "severe"},
        },
        {"scenario": "military_squad_001/v0.1"},
    ],
    "batches": [{"batch": "military_doctrine", "repeats": 1}],
}


def test_the_pipeline_produces_every_output():
    data = build_training_data(SMALL, SCENARIOS, BATCHES)

    assert data["anti_gaming_report"]["runs"] == 6
    assert (
        sum(
            len(data[name])
            for name in (
                "clean_training_dataset",
                "risky_behavior_dataset",
                "rejected_behavior_dataset",
            )
        )
        > 100
    )
    assert len(data["branch_evaluation"]) == 3
    assert len(data["rag_index"]["documents"]) == 6
    versions = {e["scenario_version"] for e in data["anti_gaming_report"]["entries"]}
    assert "v0.1+weather_degradation:severe" in versions


def test_the_export_is_identical_across_hash_seeds(tmp_path):
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({**SMALL, "batches": []}))
    outputs = []
    for seed in ("1", "2"):
        out = tmp_path / seed
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "build_training_data.py"),
                "--sources",
                str(sources),
                "--output",
                str(out),
                "--registry",
                str(tmp_path / "registry.jsonl"),
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append({p.name: p.read_bytes() for p in sorted(out.iterdir())})

    assert outputs[0] == outputs[1]
    entries = TrainingRegistry(tmp_path / "registry.jsonl").all()
    assert entries[0]["dataset_id"] == entries[1]["dataset_id"]


def test_the_pure_steps_never_run_a_simulation():
    package = SRC_PATH / "skyvault" / "training"
    banned = ("engine", "batch", "failure", "scenario_loader")
    for name in (
        "transitions",
        "labels",
        "filter",
        "branches",
        "rag",
        "registry",
        "export",
        "records",
    ):
        tree = ast.parse((package / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert not any(b in (node.module or "") for b in banned), (
                    name,
                    node.module,
                )
