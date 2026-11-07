"""Scenario loader = reads a scenario file and checks it against its contract."""

import json
from pathlib import Path
from typing import Any

import yaml

from .contracts import validate_scenario

JSON_SUFFIXES = {".json"}
YAML_SUFFIXES = {".yaml", ".yml"}


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
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    suffix = path.suffix.lower()

    with path.open("r", encoding="utf-8") as file:
        if suffix in JSON_SUFFIXES:
            raw = json.load(file)
        elif suffix in YAML_SUFFIXES:
            raw = yaml.safe_load(file)
        else:
            raise ValueError(
                f"Unsupported scenario format {suffix!r}: use .json, .yaml or .yml"
            )

    return validate_scenario(raw)
