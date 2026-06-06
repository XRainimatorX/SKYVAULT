import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = {
    "scenario_id",
    "scenario_version",
    "world_contract",
    "entities",
    "runtime",
    "evaluation",
}


def load_scenario(path: str | Path) -> dict[str, Any]:
    """
    Load a scenario JSON file.

    This is intentionally simple.
    Full schema validation comes later.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        scenario = json.load(file)

    missing = REQUIRED_KEYS - set(scenario.keys())

    if missing:
        raise ValueError(f"Scenario missing required keys: {sorted(missing)}")

    return scenario