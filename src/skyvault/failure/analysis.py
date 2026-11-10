"""Failure analysis = turn an exploration's runs into answers.

Important:
Every function here is pure: plain data in, plain data out, nothing from the
rest of the project imported. The same exploration always gives the same
failure map.

A run survives unless its verdict is fail. A level breaks the plan when fewer
than survival_threshold of its runs survive. A variable's sensitivity is how
far survival falls from the unstressed baseline at its worst level; it can be
negative when a stress happens to help the plan.
"""

import re
from collections import Counter
from typing import Any

Runs = list[dict[str, Any]]

# What to change before acting, per variable that breaks the plan
RECOMMENDATIONS = {
    "supply_delay": "Pre-position supplies or plan for operating on reduced stock.",
    "sensor_failure": "Add redundant sensing, or plan engagements that do not rely on "
    "long-range accuracy.",
    "communication_failure": "Give units standing orders that still work when orders "
    "do not get through.",
    "weather_degradation": "Plan for degraded accuracy: close the distance or wait for "
    "a weather window.",
    "enemy_reaction_speed": "Do not assume a slow enemy: plan for an opponent that "
    "hits harder and sooner.",
    "equipment_overheat": "Budget for lower sustained damage, or rotate weapons to "
    "avoid overheating.",
    "civilian_pressure": "Hold forces in reserve for civilian demands, or plan with "
    "fewer effective units.",
    "resource_shortage": "Secure resource reserves before committing to the plan.",
}

AXIS_LINE = re.compile(r"^(\w+) \d+\.\d\d: ")


def survival_rate(runs: Runs) -> float:
    return round(sum(run["survived"] for run in runs) / len(runs), 4) if runs else 0.0


def mean_score(runs: Runs) -> float:
    return round(sum(run["score"] for run in runs) / len(runs), 4) if runs else 0.0


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def sensitivity(baseline: Runs, levels: dict[str, Runs]) -> float:
    """Baseline survival minus survival at the worst level; 0 with no levels."""
    if not levels:
        return 0.0
    worst = min(survival_rate(runs) for runs in levels.values())
    return round(survival_rate(baseline) - worst, 4)


def breaking_level(
    levels: dict[str, Runs], order: list[str], threshold: float
) -> str | None:
    """The first level, in order, where survival drops below the threshold."""
    for level in order:
        if level in levels and survival_rate(levels[level]) < threshold:
            return level
    return None


def _first_loss(run: dict[str, Any]) -> str | None:
    if not run["losses"]:
        return None
    loss = run["losses"][0]
    return f"{loss['entity']} lost at tick {loss['tick']} to {loss['by']}"


def _most_common_failure(runs: Runs) -> str | None:
    failures = Counter(_first_loss(run) for run in runs if not run["survived"])
    failures.pop(None, None)
    return failures.most_common(1)[0][0] if failures else None


def _all_runs(exploration: dict[str, Any]) -> Runs:
    runs = list(exploration["baseline"])
    for entry in exploration["variables"].values():
        for level_runs in entry["levels"].values():
            runs.extend(level_runs)
    for branch in exploration["branches"]:
        runs.extend(branch["runs"])
    return runs


def _variable_results(
    exploration: dict[str, Any], variables: dict[str, Any], baseline: Runs
) -> list[dict[str, Any]]:
    order = exploration["stress_levels"]
    threshold = exploration["survival_threshold"]
    results = []
    for name, entry in variables.items():
        levels = entry["levels"]
        results.append(
            {
                "variable": name,
                "applicable": entry["applicable"],
                "reason": entry["reason"],
                "assumption": entry["assumption"],
                "levels": [
                    {
                        "level": level,
                        "survival_rate": survival_rate(levels[level]),
                        "mean_score": mean_score(levels[level]),
                        "mean_first_loss_tick": _mean(
                            [
                                r["first_loss_tick"]
                                for r in levels[level]
                                if r["first_loss_tick"]
                            ]
                        ),
                        "most_common_failure": _most_common_failure(levels[level]),
                    }
                    for level in order
                    if level in levels
                ],
                "breaking_level": breaking_level(levels, order, threshold),
                "sensitivity": sensitivity(baseline, levels),
            }
        )
    return results


def _crushing(results: list[dict[str, Any]], order: list[str]) -> dict[str, Any] | None:
    """Largest positive sensitivity; ties go to the variable that breaks sooner."""
    candidates = [r for r in results if r["applicable"] and r["sensitivity"] > 0]
    if not candidates:
        return None

    def soonest(result: dict[str, Any]) -> int:
        level = result["breaking_level"]
        return order.index(level) if level else len(order)

    return min(candidates, key=lambda r: (-r["sensitivity"], soonest(r), r["variable"]))


def _alternative(
    alternative: dict[str, Any],
    plan_results: list[dict[str, Any]],
    plan_baseline: float,
    exploration: dict[str, Any],
) -> dict[str, Any]:
    order = exploration["stress_levels"]
    results = _variable_results(
        exploration, alternative["variables"], alternative["baseline"]
    )
    plan_breaks = {
        r["variable"]: r["breaking_level"] for r in plan_results if r["applicable"]
    }
    alt_breaks = {
        r["variable"]: r["breaking_level"] for r in results if r["applicable"]
    }

    def index(level: str | None) -> int:
        return order.index(level) if level else len(order)

    longer = [
        v
        for v in alt_breaks
        if v in plan_breaks and index(alt_breaks[v]) > index(plan_breaks[v])
    ]
    sooner = [
        v
        for v in alt_breaks
        if v in plan_breaks and index(alt_breaks[v]) < index(plan_breaks[v])
    ]
    alt_baseline = survival_rate(alternative["baseline"])
    if alt_baseline > plan_baseline:
        longer.insert(0, "baseline")
    elif alt_baseline < plan_baseline:
        sooner.insert(0, "baseline")

    verdict = (
        "mixed"
        if longer and sooner
        else "holds_longer" if longer else "breaks_sooner" if sooner else "same"
    )
    return {
        "scenario_version": alternative["scenario_version"],
        "baseline_survival_rate": alt_baseline,
        "breaking_levels": alt_breaks,
        "holds_longer_on": longer,
        "breaks_sooner_on": sooner,
        "verdict": verdict,
        "_mean_survival": mean_survival(alternative),
    }


def mean_survival(sweep: dict[str, Any]) -> float:
    """Survival over the baseline and every stressed run of a plan."""
    runs = list(sweep["baseline"])
    for entry in sweep["variables"].values():
        for level_runs in entry["levels"].values():
            runs.extend(level_runs)
    return survival_rate(runs)


def _causes(failed: Runs) -> list[str]:
    """
    Each cause with the number of failed runs it appeared in, most first.

    Important:
    Ties are ordered by name. Counting from a set made the order of tied
    causes follow string hashing, which changes between processes, so the
    same exploration could write a different failure map (ADR 010).
    """
    counts: Counter[str] = Counter()
    for run in failed:
        seen: dict[str, None] = {}
        for cause in run["failure_causes"]:
            match = AXIS_LINE.match(cause)
            if match:
                seen[f"{match.group(1)} too low"] = None
            elif cause.startswith(("Failure threshold reached", "Anti-gaming")):
                seen[cause] = None
        counts.update(seen.keys())
    total = len(failed)
    return [
        f"{cause} in {count} of {total} failed runs"
        for cause, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_failure_map(exploration: dict[str, Any]) -> dict[str, Any]:
    """The failure map: where, why, how fast, what crushes it, what lasts longer."""
    order = exploration["stress_levels"]
    threshold = exploration["survival_threshold"]
    baseline = exploration["baseline"]
    baseline_rate = survival_rate(baseline)
    results = _variable_results(exploration, exploration["variables"], baseline)
    crushing = _crushing(results, order)

    every_run = _all_runs(exploration)
    failed = [run for run in every_run if not run["survived"]]
    points = Counter(_first_loss(run) for run in failed)
    points.pop(None, None)

    alternatives = [
        _alternative(alt, results, baseline_rate, exploration)
        for alt in exploration["alternatives"]
    ]
    holding = [a for a in alternatives if a["verdict"] == "holds_longer"]
    best = (
        max(holding, key=lambda a: a["_mean_survival"])["scenario_version"]
        if holding
        else None
    )
    for alternative in alternatives:
        del alternative["_mean_survival"]

    return {
        "scenario_id": exploration["scenario_id"],
        "scenario_version": exploration["scenario_version"],
        "perspective": exploration["perspective"],
        "profile_id": exploration["profile_id"],
        "objective": exploration["objective"],
        "repeat_count": exploration["repeat_count"],
        "seeds": list(exploration["seeds"]),
        "survival_threshold": threshold,
        "baseline": {
            "survival_rate": baseline_rate,
            "mean_score": mean_score(baseline),
            "outcomes": dict(
                sorted(Counter(run["outcome"] for run in baseline).items())
            ),
            "fails_without_stress": baseline_rate < threshold,
        },
        "variables": results,
        "crushing_variable": crushing["variable"] if crushing else None,
        "crushing_assumption": crushing["assumption"] if crushing else None,
        "failure_points": [
            f"{point} ({count} of {len(failed)} failed runs)"
            for point, count in points.most_common(5)
        ],
        "failure_causes": _causes(failed),
        "how_fast": {
            "mean_first_loss_tick": _mean(
                [run["first_loss_tick"] for run in failed if run["first_loss_tick"]]
            ),
            "mean_elimination_tick": _mean(
                [run["elimination_tick"] for run in failed if run["elimination_tick"]]
            ),
        },
        "branches": [
            {
                "variables": branch["variables"],
                "level": branch["level"],
                "survival_rate": survival_rate(branch["runs"]),
                "mean_score": mean_score(branch["runs"]),
            }
            for branch in exploration["branches"]
        ],
        "alternatives": alternatives,
        "best_alternative": best,
    }


def build_collapse_sequence(exploration: dict[str, Any]) -> dict[str, Any]:
    """
    How the plan dies: the losses, in order, of one failed run.

    The run is the first failed repeat of the crushing variable at its
    breaking level (its worst level when it never breaks); without a crushing
    variable, the first failed baseline run.
    """
    failure_map = build_failure_map(exploration)
    name = failure_map["crushing_variable"]
    source: Runs = exploration["baseline"]
    label = "baseline"
    if name:
        result = next(r for r in failure_map["variables"] if r["variable"] == name)
        level = (
            result["breaking_level"]
            or min(result["levels"], key=lambda entry: entry["survival_rate"])["level"]
        )
        source = exploration["variables"][name]["levels"][level]
        label = f"{name}:{level}"

    run = next((r for r in source if not r["survived"]), None)
    if run is None:
        return {
            "scenario_id": exploration["scenario_id"],
            "stress": label,
            "collapse": None,
            "reason": "no run failed under this stress",
        }
    return {
        "scenario_id": exploration["scenario_id"],
        "stress": label,
        "scenario_version": run["scenario_version"],
        "seed": run["seed"],
        "outcome": run["outcome"],
        "status": run["status"],
        "score": run["score"],
        "sequence": list(run["losses"]),
        "output_hash": run["output_hash"],
    }


def build_survival_conditions(failure_map: dict[str, Any]) -> dict[str, Any]:
    """Under which stress the plan still holds, variable by variable."""
    per_variable = {}
    conditions = []
    untested = []
    for result in failure_map["variables"]:
        if not result["applicable"]:
            untested.append(f"{result['variable']}: {result['reason']}")
            continue
        order = [entry["level"] for entry in result["levels"]]
        breaks = result["breaking_level"]
        held = order[: order.index(breaks)] if breaks else order
        per_variable[result["variable"]] = {
            "holds_up_to": held[-1] if held else None,
            "breaks_at": breaks,
        }
        if breaks is None:
            conditions.append(f"{result['variable']}: holds at every tested level")
        elif held:
            conditions.append(
                f"{result['variable']}: holds up to {held[-1]}, breaks at {breaks}"
            )
        else:
            conditions.append(f"{result['variable']}: breaks already at {breaks}")
    return {
        "scenario_id": failure_map["scenario_id"],
        "scenario_version": failure_map["scenario_version"],
        "holds_without_stress": not failure_map["baseline"]["fails_without_stress"],
        "conditions": conditions,
        "per_variable": per_variable,
        "untested": untested,
    }


def render_recommended_modifications(
    failure_map: dict[str, Any], survival_conditions: dict[str, Any]
) -> str:
    """What must change before acting on the plan, as Markdown."""
    baseline = failure_map["baseline"]
    crushing = failure_map["crushing_variable"]
    lines = [
        f"# Recommended modifications — {failure_map['scenario_id']} "
        f"{failure_map['scenario_version']}",
        "",
        f"- Perspective: {failure_map['perspective']}, "
        f"profile `{failure_map['profile_id']}`",
        f"- Runs per stressed plan: {failure_map['repeat_count']}",
        f"- Survives without stress: {baseline['survival_rate']:.0%} of runs",
        f"- Crushed by: {crushing or 'no variable'}"
        + (
            f" (attacks the assumption `{failure_map['crushing_assumption']}`)"
            if crushing
            else ""
        ),
        "",
        "## Must change before acting",
        "",
    ]

    must = []
    if baseline["fails_without_stress"]:
        must.append(
            "The plan already fails in most runs without any stress: rework it before "
            "stressing it further."
        )
    breaking = sorted(
        (r for r in failure_map["variables"] if r["breaking_level"]),
        key=lambda r: (r["variable"] != crushing, -r["sensitivity"]),
    )
    for result in breaking:
        must.append(
            f"**{result['variable']}** breaks the plan at {result['breaking_level']}: "
            f"{RECOMMENDATIONS[result['variable']]}"
        )
    if failure_map["best_alternative"]:
        best = next(
            a
            for a in failure_map["alternatives"]
            if a["scenario_version"] == failure_map["best_alternative"]
        )
        must.append(
            f"Consider the alternative **{best['scenario_version']}**: "
            f"it holds longer on {', '.join(best['holds_longer_on'])}."
        )
    if not must:
        must.append("Nothing tested breaks the plan at the levels explored.")
    lines += [f"{number}. {item}" for number, item in enumerate(must, start=1)]

    lines += ["", "## Where and why it fails", ""]
    lines += [f"- {point}" for point in failure_map["failure_points"]] or [
        "- No run failed."
    ]
    lines += [f"- {cause}" for cause in failure_map["failure_causes"]]

    lines += ["", "## Survival conditions", ""]
    lines += [f"- {condition}" for condition in survival_conditions["conditions"]]
    if survival_conditions["untested"]:
        lines += ["", "## Not tested", ""]
        lines += [f"- {item}" for item in survival_conditions["untested"]]
    return "\n".join(lines) + "\n"
