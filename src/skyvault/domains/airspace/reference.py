"""The airspace reference scenarios, built from the specs in data/domains/airspace/."""

import json
from pathlib import Path
from typing import Any

from ...compiler import publish
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


def reference_files() -> dict[str, Any]:
    """
    {"worlds/<id>.json" | "scenarios/<id>/<version>.json": document}, as the
    reference scenarios are kept in data/.
    """
    return publish(
        {
            f"{s['scenario_id']}/{s['scenario_version']}.json": s
            for s in reference_scenarios().values()
        }
    )
