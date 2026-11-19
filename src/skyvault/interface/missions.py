"""Missions = what NEXUS is told, compiled into what SKYVAULT runs (Spec 21 Phase I).

Important:
陛下 gives an order to NEXUS, NEXUS decides whether a world is needed and,
when it is, hands SKYVAULT a mission: the order word for word, an
objective, the world to run it in and the plans to try. SKYVAULT assesses
the mission (does answering it need a simulated world?), compiles it into
section 3.3 scenario documents — one per plan, so every plan is a scenario
anyone can reread and rerun — and into the jobs the world service runs.

The objectives:
    compare_plans      two or more plans side by side against the world as
                       it is (one branch_compare); which plan to take is a
                       decision for NEXUS / 陛下, so it always hands off
    test_plan          one plan, one run
    stress_test        one plan (or the world as it is) under every failure
                       variable of the scenario, one at a time
    explore_failures   a failure exploration of the scenario
    report_status      no world is needed: NEXUS answers from system status

SKYVAULT never picks a plan here; it compiles, runs and reports.
"""

import copy
from pathlib import Path
from typing import Any

from ..compiler import author_scenario
from ..contracts import validate_nexus_mission, validate_scenario
from ..failure.variables import variable_for
from ..reproducibility.versioning import child_version
from ..scenario_loader import scenario_perspective

SIMULATED = ("compare_plans", "test_plan", "stress_test", "explore_failures")


def assess_mission(mission: dict[str, Any]) -> dict[str, Any]:
    """
    Does the mission need a simulated world? {needs_skyvault, reason}.

    Important:
    A question about consequences — comparing, testing, stressing plans,
    exploring failure — needs a world; a status report does not, and SKYVAULT
    says so rather than run something for show.
    """
    mission = validate_nexus_mission(mission)
    objective = mission["objective"]
    if objective in SIMULATED:
        return {
            "needs_skyvault": True,
            "reason": f"{objective}: the answer is a consequence only a run world "
            f"shows ({mission['scenario']})",
        }
    return {
        "needs_skyvault": False,
        "reason": "report_status: answered from system status; no world is run",
    }


def _orders(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The plan's orders, each carrying the system that wrote it."""
    system = plan.get("system_id") or "NEXUS"
    return [
        {**copy.deepcopy(a), "system_id": a.get("system_id", system)}
        for a in plan["actions"]
    ]


def _job_for(mission: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
    """One scenario_run of the mission's world, with plan applied (None: as it is)."""
    runtime: dict[str, Any] = {}
    if mission.get("max_ticks"):
        runtime["max_ticks"] = mission["max_ticks"]
    job: dict[str, Any] = {"kind": "scenario_run", "scenario": mission["scenario"]}
    if plan is not None:
        if plan["actions"]:
            runtime["scheduled_actions"] = _orders(plan)
        for field in ("entity_changes", "rule_changes"):
            if plan.get(field):
                job[field] = copy.deepcopy(plan[field])
    if runtime:
        job["runtime"] = runtime
    return job


def compile_mission(
    mission: dict[str, Any], scenarios_dir: Path | None = None
) -> dict[str, Any]:
    """
    {assessment, jobs, scenarios, gaps}: the mission as jobs and as one
    section 3.3 document per plan.

    Important:
    Each document is the mission's world with the plan applied — its
    orders, unit and rule changes — as a version of the world's scenario
    ("<version>+<mission_id>.<plan_id>", its version record pointing back
    and listing what the plan changed), with the order as its purpose. It
    is checked against the scenario grammar, so a plan that does not make
    a valid scenario is refused here, before anything runs.
    """
    from ..worldservice.jobs import SCENARIOS_DIR, scenario_for

    folder = scenarios_dir or SCENARIOS_DIR
    mission = validate_nexus_mission(mission)
    assessment = assess_mission(mission)
    if not assessment["needs_skyvault"]:
        return {"assessment": assessment, "jobs": [], "scenarios": {}, "gaps": []}

    objective = mission["objective"]
    plans = mission["plans"]
    gaps: list[str] = []
    scenarios: dict[str, dict[str, Any]] = {}
    base = scenario_for(_job_for(mission, None), folder)
    for plan in plans or [None]:
        label = plan["plan_id"] if plan else "as_is"
        compiled = scenario_for(_job_for(mission, plan), folder)
        compiled["purpose"] = mission["order"]
        compiled = child_version(
            base,
            compiled,
            f"{mission['mission_id']}.{label}",
            f"NEXUS mission {mission['mission_id']}: {mission['order']}",
        )
        scenarios[label] = validate_scenario(author_scenario(compiled))

    repeats = mission.get("repeat_count")
    jobs: list[dict[str, Any]]
    if objective == "compare_plans":
        job: dict[str, Any] = {
            "kind": "branch_compare",
            "scenario": mission["scenario"],
            "branches": [
                {
                    "branch_id": p["plan_id"],
                    "actions": _orders(p),
                    **{
                        k: copy.deepcopy(p[k])
                        for k in ("entity_changes", "rule_changes")
                        if p.get(k)
                    },
                }
                for p in plans
            ],
            "repeat_count": repeats or 3,
        }
        if mission.get("max_ticks"):
            job["runtime"] = {"max_ticks": mission["max_ticks"]}
        jobs = [job]
    elif objective == "test_plan":
        jobs = [_job_for(mission, plans[0] if plans else None)]
    elif objective == "stress_test":
        base = _job_for(mission, plans[0] if plans else None)
        compiled = scenario_for(base, folder)
        names = (compiled.get("failure_exploration") or {}).get(
            "failure_variables"
        ) or compiled["world_contract"].get("failure_variables", [])
        perspective = scenario_perspective(compiled) or ""
        usable = [
            n
            for n in names
            if variable_for(compiled, n).applies(compiled, perspective)[0]
        ]
        if not usable:
            gaps.append(
                "stress_test: the scenario names no failure variables that apply to it"
            )
        jobs = [base] + [
            {**copy.deepcopy(base), "stress": {n: mission["stress_level"]}}
            for n in usable
        ]
    else:  # explore_failures
        compiled = scenario_for(_job_for(mission, None), folder)
        if not compiled.get("failure_exploration"):
            gaps.append(
                "explore_failures: the scenario has no failure_exploration section"
            )
            jobs = []
        else:
            jobs = [{"kind": "failure_exploration", "scenario": mission["scenario"]}]
            if repeats:
                jobs[0]["repeat_count"] = repeats
    if mission.get("priority"):
        for job in jobs:
            job["priority"] = mission["priority"]
    return {
        "assessment": assessment,
        "jobs": jobs,
        "scenarios": scenarios,
        "gaps": gaps,
    }
