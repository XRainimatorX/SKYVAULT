"""Profiles and rules: what STAR GUARD submits and what the screening assumes."""

import copy
import json
from pathlib import Path
from typing import Any

from ..contracts import validate_equipment_profile

DATA = Path(__file__).resolve().parents[3] / "data" / "virtualtest"
PROFILES = DATA / "profiles"
RULES = DATA / "rules.json"
GROUPS = ("physical_parameters", "engineering_parameters", "operational_parameters")


def load_rules() -> dict[str, Any]:
    rules: dict[str, Any] = json.loads(RULES.read_text(encoding="utf-8"))
    return rules


def load_profile(name: str) -> dict[str, Any]:
    """A committed profile by file name (exo_test_001), validated."""
    data = json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))
    return validate_equipment_profile(data)


def reference_profiles() -> dict[str, dict[str, Any]]:
    """Every committed profile, validated: {equipment_id: profile}."""
    found = {}
    for path in sorted(PROFILES.glob("*.json")):
        profile = validate_equipment_profile(json.loads(path.read_text("utf-8")))
        found[profile["equipment_id"]] = profile
    return found


def param(profile: dict[str, Any], group: str, name: str) -> Any:
    """One parameter, or None when the profile does not give it."""
    return (profile.get(group) or {}).get(name)


def physical(profile: dict[str, Any], name: str) -> float | None:
    value = param(profile, "physical_parameters", name)
    return None if value is None else float(value)


def category_rules(profile: dict[str, Any], rules: dict[str, Any]) -> dict | None:
    """The envelope of the profile's category, or None for one the rules do not know."""
    found: dict[str, Any] | None = rules["categories"].get(profile["category"])
    return found


def with_param(
    profile: dict[str, Any], group: str, name: str, value: Any
) -> dict[str, Any]:
    """A copy of the profile with one parameter changed."""
    changed = copy.deepcopy(profile)
    changed.setdefault(group, {})[name] = value
    return changed


def has_equipment_parameters(profile: dict[str, Any]) -> bool:
    """Whether a submitted profile carries any section 18 parameter group."""
    return any(profile.get(group) for group in GROUPS)
