"""Where the city's coefficients come from = data/domains/city/calibration.json.

Important:
Phase 23. Every coefficient of the city's information, disaster and
recovery models (and order.dark) has one entry: its value, unit,
confidence (anchored / derived / assumed), the finding and sources behind
it, how the value was converted, and the range the sensitivity analysis
sweeps. The rules (rules.json) hold the values the engine runs on; this
registry has to agree with them (registry_problems), and every built city
scenario carries it as assumptions and provenance sources.
"""

import json
from pathlib import Path
from typing import Any

CALIBRATION = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "domains"
    / "city"
    / "calibration.json"
)
CONFIDENCE = {"anchored": 0.7, "derived": 0.5, "assumed": 0.3}
COVERED_GROUPS = (
    "information_defaults",
    "disaster_effects",
    "recovery",
    "repair",
)


def load_calibration() -> dict[str, Any]:
    """The coefficient registry."""
    found: dict[str, Any] = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return found


def value_at(rules: dict[str, Any], dotted: str) -> Any:
    """The value at a dotted path in the rules (KeyError when there is none)."""
    here: Any = rules
    for key in dotted.split("."):
        here = here[key]
    return here


def with_value(dotted: str, value: Any) -> dict[str, Any]:
    """{group: {...: value}}: a rule change that sets one dotted path."""
    keys = dotted.split(".")
    change: Any = value
    for key in reversed(keys[1:]):
        change = {key: change}
    return {keys[0]: change}


def _leaves(tree: dict[str, Any], prefix: str) -> list[str]:
    found = []
    for key, value in tree.items():
        path = f"{prefix}.{key}"
        found += _leaves(value, path) if isinstance(value, dict) else [path]
    return found


def registry_problems(rules: dict[str, Any], calibration: dict[str, Any]) -> list[str]:
    """
    Where the registry and the rules disagree: a coefficient the rules do
    not have or hold at another value, a value outside its range, a source
    the registry does not list, an unknown confidence, or a coefficient of
    the covered groups (and order.dark) with no entry. Empty when they agree.
    """
    problems = []
    entries = {c["coefficient"]: c for c in calibration["coefficients"]}
    for name, entry in entries.items():
        try:
            held = value_at(rules, name)
        except (KeyError, TypeError):
            problems.append(f"{name}: not in the rules")
            continue
        if held != entry["value"]:
            problems.append(f"{name}: rules hold {held}, registry {entry['value']}")
        low, high = entry["range"]
        if not low <= entry["value"] <= high:
            problems.append(f"{name}: {entry['value']} outside {entry['range']}")
        if entry["confidence"] not in CONFIDENCE:
            problems.append(f"{name}: unknown confidence {entry['confidence']!r}")
        for source in entry["sources"]:
            if source not in calibration["sources"]:
                problems.append(f"{name}: unknown source {source!r}")
    wanted = {"order.dark"}
    for group in COVERED_GROUPS:
        wanted |= set(_leaves(rules.get(group, {}), group))
    problems += [f"{name}: no registry entry" for name in sorted(wanted - set(entries))]
    return problems


def coefficient_assumptions(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    """Each coefficient as a Formal Spec 11.2 assumption."""
    return [
        {
            "assumption_id": f"coefficient.{c['coefficient']}",
            "description": f"{c['unit']} ({c['confidence']}). {c['method']}",
            "category": "coefficient",
            "value": c["value"],
            "confidence": CONFIDENCE[c["confidence"]],
            "criticality": c.get("criticality", "medium"),
        }
        for c in calibration["coefficients"]
    ]


def coefficient_provenance(calibration: dict[str, Any]) -> dict[str, Any]:
    """The registry's sources and what it leaves unknown, as 11.3 provenance."""
    used = sorted({s for c in calibration["coefficients"] for s in c["sources"]})
    counts = {
        level: sum(1 for c in calibration["coefficients"] if c["confidence"] == level)
        for level in CONFIDENCE
    }
    assumed = [
        c["coefficient"]
        for c in calibration["coefficients"]
        if c["confidence"] == "assumed"
    ]
    return {
        "sources": [
            {
                "source_id": f"calibration.{source}",
                "source_type": "external_data",
                "confidence": 0.5,
                "version": calibration["version"],
                "modified_by": "SKYVAULT Phase 23",
            }
            for source in used
        ],
        "reliability_notes": [
            f"city coefficients (calibration.json v{calibration['version']}): "
            + ", ".join(f"{n} {level}" for level, n in counts.items())
            + "; sources read from search abstracts, full texts not read"
        ],
        "missing_data": [f"a measured value for {name}" for name in assumed],
    }


def summary(calibration: dict[str, Any]) -> str:
    """One line: the registry version and how many coefficients at each confidence."""
    counts = {
        level: sum(1 for c in calibration["coefficients"] if c["confidence"] == level)
        for level in CONFIDENCE
    }
    return f"city calibration v{calibration['version']}: " + ", ".join(
        f"{n} {level}" for level, n in counts.items()
    )
