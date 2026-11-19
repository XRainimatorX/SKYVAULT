"""Batches: many runs per variant, aggregated, compared; parallel = sequential."""

import ast
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

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.batch.aggregate import aggregate, compare_branches, wilson_interval
from skyvault.batch.run import run_batch
from skyvault.batch.runner import run_jobs
from skyvault.batch.variants import Variant
from skyvault.contracts import ContractError, validate_batch_spec
from skyvault.scenario_loader import default_evaluation_profile, load_scenario


def request(**changes) -> dict:
    with BATCH.open(encoding="utf-8") as file:
        data = json.load(file)
    data.pop("conflicts")
    data.update(changes)
    return data


def record(
    variant="a", outcome="RED_survived", status="risky", score=0.5, seed=1, **extra
):
    return {
        "variant_id": variant,
        "kind": "version",
        "scenario_version": "v1",
        "seed": seed,
        "outcome": outcome,
        "status": status,
        "score": score,
        "hp_lost": extra.get("hp_lost", 10.0),
        "risk_events": extra.get("risk_events", 1.0),
        "event_count": extra.get("event_count", 90),
        "output_hash": extra.get("output_hash", f"h{seed}"),
    }


# ── aggregation ──────────────────────────────────────────────────────────────


def test_wins_losses_and_draws_are_seen_from_the_perspective():
    records = [
        record(outcome="RED_survived", seed=1),
        record(outcome="BLUE_survived", status="fail", seed=2),
        record(outcome="no_winner_duration_limit", seed=3),
        record(outcome="draw_all_destroyed", status="fail", seed=4),
    ]

    [stats] = aggregate(records, "RED")

    assert (stats["win_rate"], stats["loss_rate"], stats["draw_rate"]) == (
        0.25,
        0.25,
        0.5,
    )
    assert stats["failure_frequency"] == 0.5
    assert stats["outcomes"] == {
        "BLUE_survived": 1,
        "RED_survived": 1,
        "draw_all_destroyed": 1,
        "no_winner_duration_limit": 1,
    }
    assert aggregate(records, "BLUE")[0]["win_rate"] == 0.25


def test_cost_risk_and_score_are_averaged_per_variant_in_first_seen_order():
    records = [
        record("b", score=0.2, hp_lost=30, risk_events=3, seed=1),
        record("a", score=0.6, hp_lost=10, risk_events=1, seed=1),
        record("b", score=0.4, hp_lost=10, risk_events=1, seed=2, output_hash="h1"),
    ]

    b, a = aggregate(records, "RED")

    assert [b["variant_id"], a["variant_id"]] == ["b", "a"]
    assert (b["mean_score"], b["mean_hp_lost"], b["mean_risk_events"]) == (
        0.3,
        20.0,
        2.0,
    )
    assert b["score_stdev"] == pytest.approx(0.1414, abs=1e-4)
    assert b["distinct_outputs"] == 1
    assert a["score_stdev"] == 0.0  # a single run has no spread


def test_the_wilson_interval():
    assert wilson_interval(6, 100) == [0.0278, 0.1248]
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0
    assert wilson_interval(0, 0) == [0.0, 1.0]


def test_branches_are_compared_metric_by_metric():
    stats = aggregate(
        [
            record("plan", score=0.4, hp_lost=60, status="fail", seed=1),
            record("alt", score=0.6, hp_lost=40, seed=1),
            record("tie", score=0.6, hp_lost=40, outcome="BLUE_survived", seed=1),
        ],
        "RED",
    )

    comparison = compare_branches(stats)

    assert comparison["best"]["mean_score"] == "alt"  # tie goes to the first listed
    assert comparison["best"]["mean_hp_lost"] == "alt"
    assert comparison["best"]["failure_frequency"] == "alt"
    assert comparison["deltas_vs_first"]["alt"]["mean_hp_lost"] == -20.0
    assert comparison["ranking"] == ["alt", "tie", "plan"]
    assert comparison["comparison"]["alt"] == {
        "better_than": ["plan"],
        "worse_than": [],
    }
    assert comparison["comparison"]["plan"] == {
        "better_than": [],
        "worse_than": ["alt", "tie"],
    }


# ── running ──────────────────────────────────────────────────────────────────


def plan():
    return load_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "reference"
        / "scenarios"
        / "tactical_reference_001"
        / "v0.1.json"
    )


def test_records_come_back_variant_by_variant_and_seed_by_seed():
    base = plan()
    variants = [Variant("one", "version", base), Variant("two", "version", base)]

    records = run_jobs(variants, default_evaluation_profile(base), [42, 43], workers=1)

    assert [(r["variant_id"], r["seed"]) for r in records] == [
        ("one", 42),
        ("one", 43),
        ("two", 42),
        ("two", 43),
    ]
    assert records[0]["outcome"] == "RED_survived"
    assert records[0]["output_hash"] == records[2]["output_hash"]


def test_a_parallel_batch_is_identical_to_a_sequential_one():
    sequential = run_batch(request(), repeats=3, workers=1)
    parallel = run_batch(request(), repeats=3, workers=3)

    for key, value in sequential["batch_result"].items():
        if key != "workers":
            assert parallel["batch_result"][key] == value, key
    assert parallel["branch_comparison"] == sequential["branch_comparison"]


# ── acceptance 1–3 ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def hundred():
    only_plan = request(variants=[{"variant_id": "plan", "scenario_version": "v0.1"}])
    del only_plan["sweeps"]
    return run_batch(only_plan, repeats=100, workers=2)


def test_the_same_scenario_runs_100_times(hundred):
    result = hundred["batch_result"]

    assert result["total_runs"] == 100
    assert result["seeds"] == list(range(42, 142))
    [plan_stats] = result["variants"]
    assert plan_stats["runs"] == 100
    assert plan_stats["distinct_outputs"] == 100


def test_each_variant_reports_win_rate_cost_risk_and_failure_frequency(hundred):
    [stats] = hundred["batch_result"]["variants"]

    assert stats["win_rate"] == 0.06
    assert stats["win_rate_ci"] == [0.0278, 0.1248]
    assert stats["failure_frequency"] == 0.27
    assert stats["mean_hp_lost"] == 69.05
    assert stats["mean_risk_events"] == 1.92


def test_versions_and_sweep_points_sit_side_by_side():
    result = run_batch(request(), repeats=4)
    table = result["branch_comparison"]["table"]

    assert list(table) == [
        "plan",
        "support-rear",
        "spread",
        "sweep:entities[blue_002].capabilities.accuracy=0.55",
        "sweep:entities[blue_002].capabilities.accuracy=0.65",
        "sweep:entities[blue_002].capabilities.accuracy=0.75",
    ]
    # Sweeping to the base value is the base plan again
    assert table["sweep:entities[blue_002].capabilities.accuracy=0.55"] == table["plan"]


# ── the request ──────────────────────────────────────────────────────────────


def test_optional_request_fields_may_be_left_out():
    minimal = {
        "batch_id": "minimal",
        "scenario_id": "tactical_reference_001",
        "base_version": "v0.1",
        "profile": "balanced",
        "run_policy": {"repeat_count": 1, "random_seed_policy": "fixed"},
        "sweeps": [{"parameter": "runtime.max_ticks", "values": [5]}],
    }

    result = run_batch(minimal)

    assert result["batch_result"]["workers"] == 1
    assert result["batch_result"]["perspective"] == "RED"
    assert result["conflict_package"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"variants": [], "sweeps": []}, "needs variants, sweeps or conflicts"),
        (
            {"variants": [{"variant_id": "x", "scenario_version": "v0.1"}] * 2},
            "variant_id must be unique",
        ),
        ({"workers": 0}, "greater than or equal to 1"),
    ],
)
def test_a_broken_request_is_rejected(change, message):
    with pytest.raises(ContractError) as caught:
        validate_batch_spec(request(**change))

    assert message in " | ".join(caught.value.errors)


def test_the_reference_request_is_valid():
    with BATCH.open(encoding="utf-8") as file:
        data = json.load(file)

    assert validate_batch_spec(data) == data


def test_aggregation_imports_nothing_from_the_project():
    path = SRC_PATH / "skyvault" / "batch" / "aggregate.py"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert not (node.module or "").startswith("skyvault")
