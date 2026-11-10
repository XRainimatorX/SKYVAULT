"""Verification = rerun a recorded run and check it produces the same result.

Important:
This module sits above the engine, next to the scripts: it builds an engine to
rerun a package. Nothing below it imports it.
"""

from pathlib import Path
from typing import Any

from .engine import SkyVaultEngine
from .reproducibility import input_hash, output_hash
from .scenario_loader import PROFILE_DIR, load_evaluation_profile, load_scenario

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def locate_inputs(
    package: dict[str, Any],
    scenario_dir: Path = SCENARIO_DIR,
    profile_dir: Path = PROFILE_DIR,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    The scenario and evaluation profile a result package was produced from.

    Important:
    A package names its own sources: scenario_id and scenario_version find
    data/scenarios/<scenario_id>/<scenario_version>.json, and the verdict's
    profile_id finds data/evaluation_profiles/<profile_id>.json, judged from
    the perspective the verdict records.
    """
    block = package["reproducibility"]
    scenario = load_scenario(
        scenario_dir / block["scenario_id"] / f"{block['scenario_version']}.json"
    )
    verdict = package["evaluation_result"]
    profile = load_evaluation_profile(profile_dir / f"{verdict['profile_id']}.json")
    if profile["perspective"] is None:
        profile["perspective"] = verdict["perspective"]
    return scenario, profile


def verify_reproducibility(
    package: dict[str, Any],
    scenario: dict[str, Any],
    evaluation_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Rerun the scenario and compare the new result with the recorded one.

    Returns {reproduced, replay_available, input_hash_matches,
    expected_output_hash, recorded_output_hash, actual_output_hash}.

    Important:
    expected_output_hash is recomputed from the package itself, so a package
    edited after it was written fails even if its reproducibility block was
    left alone. A run whose block says replay is not available (stochastic)
    is not rerun: reproduced is False and replay_available says why.
    """
    block = package["reproducibility"]
    recorded = block["output_hash"]
    expected = output_hash(package)

    if not block["deterministic_replay_available"]:
        return {
            "reproduced": False,
            "replay_available": False,
            "input_hash_matches": None,
            "expected_output_hash": expected,
            "recorded_output_hash": recorded,
            "actual_output_hash": None,
        }

    engine = SkyVaultEngine(scenario, evaluation_profile)
    rerun = engine.run()
    actual = rerun["reproducibility"]["output_hash"]
    same_input = (
        input_hash(engine.scenario, engine.evaluation_profile) == block["input_hash"]
    )

    return {
        "reproduced": same_input and actual == expected == recorded,
        "replay_available": True,
        "input_hash_matches": same_input,
        "expected_output_hash": expected,
        "recorded_output_hash": recorded,
        "actual_output_hash": actual,
    }
