"""The airspace reference scenarios, built from the specs in data/domains/airspace/."""

import json
from pathlib import Path
from typing import Any

from .scenario import build_airspace_scenario

DATA = Path(__file__).resolve().parents[4] / "data"
SPECS = DATA / "domains" / "airspace" / "scenarios"
RULES = DATA / "domains" / "airspace" / "rules.json"


def load_rules() -> dict[str, Any]:
    rules: dict[str, Any] = json.loads(RULES.read_text(encoding="utf-8"))
    return rules


def load_spec(name: str) -> dict[str, Any]:
    spec: dict[str, Any] = json.loads((SPECS / f"{name}.json").read_text("utf-8"))
    return spec


def reference_scenarios() -> dict[str, dict[str, Any]]:
    """Every airspace spec, built: {scenario_id: scenario}."""
    rules = load_rules()
    built = {}
    for path in sorted(SPECS.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        built[spec["scenario_id"]] = build_airspace_scenario(spec, rules)
    return built


def scenario_path(name: str, version: str = "v0.1") -> Path:
    return DATA / "scenarios" / name / f"{version}.json"
