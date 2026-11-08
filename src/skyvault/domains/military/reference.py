"""The pack's reference scenarios: four specs and the doctrine variants of one.

Important:
data/scenarios/military_*/ is generated from data/domains/military/ by
scripts/build_military_scenarios.py; a test rebuilds them and compares, so
the committed scenarios can never drift from their specs.
"""

import json
from pathlib import Path
from typing import Any

from .profiles import REPO_ROOT, load_profiles
from .scenario import build_scenario, doctrine_variant

SPEC_DIR = REPO_ROOT / "data" / "domains" / "military" / "scenarios"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

# scenario_id -> (faction, doctrine) variants written next to its v0.1
DOCTRINE_VARIANTS = {
    "military_urban_001": [("RED", "overwatch"), ("RED", "defensive")],
}


def reference_scenarios(profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"<scenario_id>/<version>.json": scenario} for every reference scenario."""
    profiles = profiles or load_profiles()
    scenarios: dict[str, Any] = {}
    for path in sorted(SPEC_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as file:
            base = build_scenario(json.load(file), profiles)
        scenarios[_name(base)] = base
        for faction, doctrine in DOCTRINE_VARIANTS.get(base["scenario_id"], []):
            variant = doctrine_variant(base, faction, doctrine)
            scenarios[_name(variant)] = variant
    return scenarios


def _name(scenario: dict[str, Any]) -> str:
    return f"{scenario['scenario_id']}/{scenario['scenario_version']}.json"


def scenario_path(name: str) -> Path:
    return SCENARIO_DIR / name
