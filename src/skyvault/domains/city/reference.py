"""The city reference scenarios, built from the specs in data/domains/city/."""

import json
from pathlib import Path
from typing import Any

from .scenario import build_city_scenario

DATA = Path(__file__).resolve().parents[4] / "data"
SPECS = DATA / "domains" / "city" / "scenarios"
RULES = DATA / "domains" / "city" / "rules.json"


def load_rules() -> dict[str, Any]:
    rules: dict[str, Any] = json.loads(RULES.read_text(encoding="utf-8"))
    return rules


def reference_scenarios() -> dict[str, dict[str, Any]]:
    """Every city spec, built: {scenario_id: scenario}."""
    rules = load_rules()
    built = {}
    for path in sorted(SPECS.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        built[spec["scenario_id"]] = build_city_scenario(spec, rules)
    return built


def scenario_path(name: str, version: str = "v0.1") -> Path:
    return DATA / "scenarios" / name / f"{version}.json"
