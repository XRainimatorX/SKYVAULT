"""Scenario loader = reads scenarios and evaluation profiles against their contracts."""

import json
from pathlib import Path
from typing import Any

import yaml

from .contracts import validate_evaluation_profile, validate_scenario

JSON_SUFFIXES = {".json"}
YAML_SUFFIXES = {".yaml", ".yml"}

PROFILE_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation_profiles"
DEFAULT_PROFILE = PROFILE_DIR / "balanced.json"


def load_scenario(path: str | Path) -> dict[str, Any]:
    """
    Load a scenario file and validate it.

    Important:
    The file may be JSON or YAML; the suffix decides which. Either way the
    result must satisfy the scenario contract, so a scenario missing
    scenario_id, carrying an unknown key or written for another schema_version
    raises ContractError here, before any world is built from it.

    This module only reads and validates. It does not build a WorldState —
    that is engine.build_world().
    """
    return validate_scenario(_read(path, "Scenario"))


def load_evaluation_profile(path: str | Path) -> dict[str, Any]:
    """
    Load an evaluation profile file (JSON or YAML) and validate it.

    Important:
    A profile is judged separately from any scenario: the same run can be
    evaluated under several profiles without running it again.
    """
    return validate_evaluation_profile(_read(path, "Evaluation profile"))


def default_evaluation_profile(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    The profile a run is judged by when none is given: balanced.json, seen
    from the scenario's perspective.

    Important:
    The perspective is scenario.evaluation.perspective when declared,
    otherwise the faction of the scenario's first entity that has one.
    """
    profile = load_evaluation_profile(DEFAULT_PROFILE)
    if profile["perspective"] is None:
        profile["perspective"] = scenario_perspective(scenario)
    return profile


def scenario_perspective(scenario: dict[str, Any]) -> str | None:
    """Whose plan the scenario is judged as, when a profile does not say."""
    declared = scenario.get("evaluation", {}).get("perspective")
    if declared:
        return str(declared)
    for entity in scenario["entities"]:
        if entity.get("faction"):
            return str(entity["faction"])
    return None


def _read(path: str | Path, kind: str) -> Any:
    """The parsed content of a JSON or YAML file; the suffix decides which."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"{kind} file not found: {path}")

    suffix = path.suffix.lower()

    with path.open("r", encoding="utf-8") as file:
        if suffix in JSON_SUFFIXES:
            return json.load(file)
        if suffix in YAML_SUFFIXES:
            return yaml.safe_load(file)

    raise ValueError(
        f"Unsupported {kind.lower()} format {suffix!r}: use .json, .yaml or .yml"
    )
