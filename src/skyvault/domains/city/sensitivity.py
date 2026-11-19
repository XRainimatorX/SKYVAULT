"""Which city coefficients change a conclusion = one-at-a-time sensitivity.

Important:
Phase 23. Each coefficient in calibration.json is moved to each end of its
range, one at a time, and the reference cities are run again on the same
seeds. Two kinds of conclusion are compared with the calibrated run:

    verdict   each scenario's majority result over the seeds
              (order_restored / order_not_restored)
    best plan the takeover plan with the highest mean governance score
              (强攻 / 封鎖 / 談判 / 先恢復供應, data/missions)

A coefficient that flips a conclusion at either end is high criticality;
one that moves a scenario's mean governance score by at least SHIFT is
medium; the rest are low. Low-confidence, high-criticality coefficients
are where measured data is needed first.
"""

import copy
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...engine import SkyVaultEngine
from .calibration import with_value
from .score import governance_stability

REPORT = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "domains"
    / "city"
    / "sensitivity.json"
)
MISSION = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "missions"
    / "city_takeover_branches_001.json"
)
SCENARIOS = (
    "city_blackout_001",
    "city_reconstruction_001",
    "city_takeover_001",
    "urban_crisis_test_001",
)
SEEDS = (1, 2, 3)
SHIFT = 0.05


def _merge(into: dict[str, Any], change: dict[str, Any]) -> None:
    for key, value in change.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = copy.deepcopy(value)


def with_rules(scenario: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    """A copy of scenario whose city rules have change merged in."""
    changed = copy.deepcopy(scenario)
    _merge(changed["world_contract"]["rule_set"]["city"], change)
    return changed


def with_plan(scenario: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """A copy of scenario with a takeover plan's rule and unit changes."""
    changed = with_rules(scenario, plan.get("rule_changes", {}).get("city", {}))
    units = {unit["entity_id"]: unit for unit in changed["entities"]}
    for entity_id, change in plan.get("entity_changes", {}).items():
        for field in ("capabilities", "state"):
            units[entity_id][field] = {
                **units[entity_id].get(field, {}),
                **change.get(field, {}),
            }
    return changed


def outcome(scenario: dict[str, Any], seeds: tuple[int, ...]) -> dict[str, Any]:
    """{verdict, governance}: majority result and mean governance score over seeds."""
    results, scores = [], []
    for seed in seeds:
        run = copy.deepcopy(scenario)
        run["runtime"]["random_seed"] = seed
        package = SkyVaultEngine(run).run()
        results.append(package["evaluation_result"]["winner_or_result"])
        scores.append(governance_stability(package, scenario)["score"])
    verdict = sorted(Counter(results).items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return {"verdict": verdict, "governance": round(sum(scores) / len(scores), 4)}


def conclusions(
    scenarios: dict[str, dict[str, Any]],
    plans: list[dict[str, Any]],
    change: dict[str, Any],
    seeds: tuple[int, ...] = SEEDS,
) -> dict[str, Any]:
    """Every scenario's outcome and the takeover plans' ranking under change."""
    found = {
        name: outcome(with_rules(scenario, change), seeds)
        for name, scenario in scenarios.items()
    }
    takeover = with_rules(scenarios["city_takeover_001"], change)
    ranking = {
        plan["plan_id"]: outcome(with_plan(takeover, plan), seeds)["governance"]
        for plan in plans
    }
    best = max(sorted(ranking), key=lambda plan_id: ranking[plan_id])
    return {"scenarios": found, "plans": ranking, "best_plan": best}


def flips(base: dict[str, Any], moved: dict[str, Any]) -> list[str]:
    """The conclusions moved differs from base on."""
    found = [
        f"{name}: {base['scenarios'][name]['verdict']} → {got['verdict']}"
        for name, got in moved["scenarios"].items()
        if got["verdict"] != base["scenarios"][name]["verdict"]
    ]
    if moved["best_plan"] != base["best_plan"]:
        found.append(f"best plan: {base['best_plan']} → {moved['best_plan']}")
    return found


def criticality(flipped: list[str], shift: float) -> str:
    return "high" if flipped else "medium" if shift >= SHIFT else "low"


def sweep(
    scenarios: dict[str, dict[str, Any]],
    calibration: dict[str, Any],
    seeds: tuple[int, ...] = SEEDS,
    only: list[str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    The sensitivity report: the calibrated conclusions (baseline) and, for
    each coefficient (or only those named), each end of its range — what
    flipped, the largest shift in mean governance score, and criticality.
    """
    plans = json.loads(MISSION.read_text(encoding="utf-8"))["plans"]
    base = conclusions(scenarios, plans, {}, seeds)
    rows = []
    for entry in calibration["coefficients"]:
        name = entry["coefficient"]
        if only is not None and name not in only:
            continue
        if progress is not None:
            progress(name)
        ends = {}
        for label, value in zip(("low", "high"), entry["range"], strict=True):
            moved = conclusions(scenarios, plans, with_value(name, value), seeds)
            shift = max(
                abs(
                    moved["scenarios"][s]["governance"]
                    - base["scenarios"][s]["governance"]
                )
                for s in moved["scenarios"]
            )
            ends[label] = {
                "value": value,
                "flips": flips(base, moved),
                "max_governance_shift": round(shift, 4),
                "best_plan": moved["best_plan"],
            }
        flipped = ends["low"]["flips"] + ends["high"]["flips"]
        shift = max(
            ends["low"]["max_governance_shift"], ends["high"]["max_governance_shift"]
        )
        rows.append(
            {
                "coefficient": name,
                "confidence": entry["confidence"],
                "ends": ends,
                "criticality": criticality(flipped, shift),
            }
        )
    return {
        "calibration_version": calibration["version"],
        "seeds": list(seeds),
        "shift_threshold": SHIFT,
        "baseline": base,
        "coefficients": rows,
        "data_first": [
            r["coefficient"]
            for r in rows
            if r["criticality"] == "high" and r["confidence"] == "assumed"
        ],
    }


def load_sensitivity() -> dict[str, Any]:
    """The committed sensitivity report (data/domains/city/sensitivity.json)."""
    found: dict[str, Any] = json.loads(REPORT.read_text(encoding="utf-8"))
    return found
