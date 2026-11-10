"""Shared fixtures: the Phase 0 reference slice, and its workspace.

Important:
The reference slice (tests/fixtures/reference/: the tactical reference
policy, its scenarios and its batch) is a development fixture — SKYVAULT
itself has none of it (Phase 21). This module puts it within reach of the
tests only, the way any deployment adds its own: the policy module through
SKYVAULT_POLICY_MODULES (it registers "tactical_reference" when a run first
asks for it), the scenario and batch folders through SKYVAULT_SCENARIO_PATH
and SKYVAULT_BATCH_PATH. Scripts the tests run inherit all three.

Tests never read output/. The reference workspace is the run, its failure
exploration and the reference batch, produced here by the same library
calls into tmp_path once per session.
"""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
REFERENCE_SLICE = REPO_ROOT / "tests" / "fixtures" / "reference"
REFERENCE_SCENARIOS = REFERENCE_SLICE / "scenarios"
REFERENCE_POLICY = REFERENCE_SLICE / "policy.py"
REFERENCE = REFERENCE_SCENARIOS / "tactical_reference_001" / "v0.1.json"
BATCH = REFERENCE_SLICE / "batches" / "tactical_reference_001.json"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

os.environ["SKYVAULT_SCENARIO_PATH"] = str(REFERENCE_SCENARIOS)
os.environ["SKYVAULT_BATCH_PATH"] = str(REFERENCE_SLICE / "batches")
os.environ["SKYVAULT_POLICY_MODULES"] = str(REFERENCE_POLICY)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_run(folder: Path) -> dict:
    from skyvault.engine import SkyVaultEngine
    from skyvault.scenario_loader import load_scenario

    package = SkyVaultEngine(load_scenario(REFERENCE)).run()
    write_json(folder / "result_package.json", package)
    return package


@pytest.fixture(scope="session")
def run_only_workspace(tmp_path_factory) -> Path:
    """A workspace with only the reference run's result package."""
    folder = tmp_path_factory.mktemp("run_only")
    write_run(folder)
    return folder


@pytest.fixture(scope="session")
def reference_workspace(tmp_path_factory) -> Path:
    """The run, the default failure exploration and the 100-run batch."""
    from skyvault.batch.aggregate import render_comparative_report
    from skyvault.batch.run import run_batch
    from skyvault.failure import (
        build_collapse_sequence,
        build_failure_map,
        build_survival_conditions,
        explore_failures,
        render_recommended_modifications,
    )
    from skyvault.scenario_loader import default_evaluation_profile, load_scenario

    folder = tmp_path_factory.mktemp("reference")
    write_run(folder)

    scenario = load_scenario(REFERENCE)
    exploration = explore_failures(
        scenario,
        default_evaluation_profile(scenario),
        copy.deepcopy(scenario["failure_exploration"]),
    )
    failure_map = build_failure_map(exploration)
    conditions = build_survival_conditions(failure_map)
    write_json(folder / "failure_map.json", failure_map)
    write_json(folder / "collapse_sequence.json", build_collapse_sequence(exploration))
    write_json(folder / "survival_conditions.json", conditions)
    (folder / "recommended_modifications.md").write_text(
        render_recommended_modifications(failure_map, conditions), encoding="utf-8"
    )

    with BATCH.open(encoding="utf-8") as file:
        result = run_batch(json.load(file), workers=4)
    write_json(folder / "batch_result.json", result["batch_result"])
    write_json(folder / "branch_comparison.json", result["branch_comparison"])
    write_json(folder / "conflict_package.json", result["conflict_package"])
    (folder / "comparative_report.md").write_text(
        render_comparative_report(
            result["batch_result"],
            result["branch_comparison"],
            result["conflict_package"],
        ),
        encoding="utf-8",
    )
    return folder
