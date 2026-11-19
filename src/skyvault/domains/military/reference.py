"""The pack's reference scenarios: four specs, their revisions, and doctrine variants.

Important:
data/scenarios/military_*/ is generated from data/domains/military/ by
scripts/dev/build_military_scenarios.py; a test rebuilds them and compares, so
the committed scenarios can never drift from their specs.

A spec's "revisions" are later versions of the same plan, each a child of
the one before (v0.1 -> v0.2): every field a revision names replaces the
plan's, and version_control records what changed. Doctrine variants are
written next to the base version and next to every revision.
"""

import copy
import json
from pathlib import Path
from typing import Any

from ...compiler import publish
from ...reproducibility.versioning import compare_scenarios
from .profiles import REPO_ROOT, load_profiles
from .scenario import build_scenario, doctrine_variant

SPEC_DIR = REPO_ROOT / "data" / "domains" / "military" / "scenarios"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

# scenario_id -> (faction, doctrine) variants written next to each version
DOCTRINE_VARIANTS = {
    "military_urban_001": [("RED", "overwatch"), ("RED", "defensive")],
}


def reference_scenarios(profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"<scenario_id>/<version>.json": scenario} for every reference scenario."""
    profiles = profiles or load_profiles()
    scenarios: dict[str, Any] = {}
    for path in sorted(SPEC_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as file:
            spec = json.load(file)
        # the world can suffer every failure any version of the plan explores
        spec["failure_variables"] = sorted(
            {
                v
                for r in spec.get("revisions", [])
                for v in r.get("failure_variables", [])
            }
        )
        base = build_scenario(spec, profiles)
        versions = [base]
        for revision in spec.get("revisions", []):
            versions.append(revised(versions[-1], revision))
        for version in versions:
            scenarios[_name(version)] = version
            for faction, doctrine in DOCTRINE_VARIANTS.get(base["scenario_id"], []):
                variant = doctrine_variant(version, faction, doctrine)
                variant.pop("failure_exploration", None)
                scenarios[_name(variant)] = variant
    return scenarios


def revised(parent: dict[str, Any], revision: dict[str, Any]) -> dict[str, Any]:
    """
    The next version of parent: its failure exploration replaced by the
    revision's, recorded as a child of parent. (The world already declares
    every failure variable a revision explores.)
    """
    child = copy.deepcopy(parent)
    child["scenario_version"] = revision["scenario_version"]
    if "failure_exploration" in revision:
        child["failure_exploration"] = copy.deepcopy(revision["failure_exploration"])
    child["version_control"] = {
        "version": revision["scenario_version"],
        "parent_version": parent["scenario_version"],
        "changed_from_previous": compare_scenarios(parent, child),
        "change_reason": revision["change_reason"],
    }
    return child


def _name(scenario: dict[str, Any]) -> str:
    return f"{scenario['scenario_id']}/{scenario['scenario_version']}.json"


def scenario_path(name: str) -> Path:
    return SCENARIO_DIR / name


def reference_files(profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    {"worlds/<id>.json" | "scenarios/<id>/<version>.json": document}, as the
    reference scenarios are kept in data/.
    """
    return publish(reference_scenarios(profiles))
