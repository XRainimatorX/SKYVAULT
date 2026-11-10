"""The training pipeline: run the sources, label, filter, export, index.

Important:
This module runs simulations (with the engine and the batch runner); every
step after the runs is one of the pure functions in this package. Runs are
done in source order and seed order, so the same sources always give the
same datasets.
"""

import copy
import json
from pathlib import Path
from typing import Any

from ..batch.run import run_batch
from ..engine import SkyVaultEngine
from ..failure import apply_stress
from ..library import scenario_folder
from ..scenario_loader import PROFILE_DIR, load_evaluation_profile, load_scenario
from .branches import branch_evaluation
from .filter import anti_gaming_report, split_runs
from .rag import build_rag_index, run_document


def run_sources(
    sources: dict[str, Any], scenarios_dir: Path, profile_dir: Path = PROFILE_DIR
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(package, scenario) for every source × seed, in that order."""
    profile = load_evaluation_profile(profile_dir / f"{sources['profile']}.json")
    runs = []
    for source in sources["runs"]:
        scenario_id, version = source["scenario"].split("/")
        base = load_scenario(
            scenario_folder(scenarios_dir, scenario_id) / f"{version}.json"
        )
        if source.get("stress"):
            perspective = (
                source.get("perspective")
                or profile.get("perspective")
                or (
                    base["evaluation"].get("perspective")
                    or base["entities"][0]["faction"]
                )
            )
            base = apply_stress(base, source["stress"], perspective)
        for offset in range(int(sources["seeds"])):
            scenario = copy.deepcopy(base)
            scenario["runtime"]["random_seed"] = base["runtime"]["random_seed"] + offset
            package = SkyVaultEngine(
                scenario, evaluation_profile=copy.deepcopy(profile)
            ).run()
            runs.append((package, scenario))
    return runs


def build_training_data(
    sources: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
    profile_dir: Path = PROFILE_DIR,
    workers: int = 1,
) -> dict[str, Any]:
    """Every output of the pipeline as plain data (nothing written here)."""
    runs = run_sources(sources, scenarios_dir, profile_dir)
    split = split_runs(runs)
    report = anti_gaming_report(runs)
    documents = [
        run_document(entry, package)
        for entry, (package, _) in zip(report["entries"], runs, strict=True)
    ]
    branches = []
    for item in sources.get("batches", []):
        with (batches_dir / f"{item['batch']}.json").open(encoding="utf-8") as file:
            request = json.load(file)
        result = run_batch(
            request,
            scenarios_dir=scenarios_dir,
            profile_dir=profile_dir,
            repeats=item.get("repeats"),
            workers=workers,
        )
        branches += branch_evaluation(
            result["batch_result"],
            result["branch_comparison"],
            result["conflict_package"],
        )
    return {
        "clean_training_dataset": split["clean"],
        "risky_behavior_dataset": split["risky"],
        "rejected_behavior_dataset": split["rejected"],
        "anti_gaming_report": report,
        "branch_evaluation": branches,
        "rag_index": build_rag_index(documents),
    }
