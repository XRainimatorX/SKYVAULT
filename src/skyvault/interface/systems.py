"""Systems = the nine outside systems, each in its own terms (Formal Spec section 9).

Important:
An adapter turns a system's submission into what SKYVAULT runs —
to_request(submission) → {system, supported, jobs, world_actions, gaps} —
and turns what ran into what section 9 says the system gets back —
to_return(results, submission), where results holds one entry per job,
in order: {job, result, scenario}. A world action has no job: its entry
is the world's result package and scenario.

What SKYVAULT cannot model is never simulated by pretending: the
submission comes back supported false (CYBERHOUND outside a city), or the
parts that do not map come back as gaps (EIDEN-01's unknown units,
AEROGRID's airspace).
Adapters only read results; none of them chooses for the system.
"""

import copy
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from ..contracts import validate_external_submission, validate_nexus_mission
from ..domains import load_domain
from ..domains.city.information import DEFAULTS as INFORMATION_DEFAULTS
from ..failure.variables import variable_for
from ..library import find
from ..observation.history import history_from_package, observations_for_run
from ..observation.profiles import load_observer_profile
from ..report import build_briefing, render_markdown
from ..scenario_loader import load_scenario, scenario_perspective
from ..training.transitions import build_transitions
from ..virtualtest.profile import GROUPS, has_equipment_parameters, load_rules
from ..virtualtest.run import virtual_test
from ..virtualtest.tactical import unit_changes
from .handoff import authority_handoff
from .missions import compile_mission

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
DEFAULT_REPEATS = 3
# Refusals that come from what a unit can do (range, reach, ammunition,
# terrain it cannot cross, resources it lacks) — as opposed to the moment
# (a cell already occupied, a target gone, an order lost)
CAPABILITY_LIMITS = (
    "Move target out of reach",
    "Target out of range",
    "Out of ammunition",
    "Move target is impassable",
    "Actor cannot",
    "Insufficient",
)
NEXUS_TASKS = ("scenario_run", "batch", "failure_exploration")

Request = dict[str, Any]
Results = list[dict[str, Any]]


def load_scenario_named(name: str, scenarios_dir: Path = SCENARIOS_DIR) -> dict:
    """The scenario a submission names ("<scenario_id>/<version>"), compiled."""
    path = find(scenarios_dir, f"{name}.json")
    if path is None or not path.is_file():
        raise ValueError(f"nothing named {name!r} in the scenarios library")
    return load_scenario(path)


def request(
    system: str,
    jobs: list[dict[str, Any]] | None = None,
    gaps: list[str] | None = None,
    world_actions: dict[str, Any] | None = None,
    supported: bool = True,
) -> Request:
    """What an adapter asks SKYVAULT to do; every job names its system."""
    return {
        "system": system,
        "supported": supported,
        "jobs": [{**job, "source_system": system} for job in (jobs or [])],
        "world_actions": world_actions,
        "gaps": list(gaps or []),
    }


def seeded_runs(
    submission: dict[str, Any],
    runtime: dict[str, Any],
    scenarios_dir: Path,
    **extra: Any,
) -> list[dict[str, Any]]:
    """repeat_count scenario runs, the scenario's own seed upwards."""
    base = load_scenario_named(submission["scenario"], scenarios_dir)
    seed = int(base["runtime"]["random_seed"])
    repeats = int(submission["content"].get("repeat_count", DEFAULT_REPEATS))
    return [
        {
            "kind": "scenario_run",
            "scenario": submission["scenario"],
            "runtime": {**copy.deepcopy(runtime), "random_seed": seed + n},
            **copy.deepcopy(extra),
        }
        for n in range(repeats)
    ]


# ── reading result packages ──────────────────────────────────────────────────


def units(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The final units of a run."""
    return dict(package["final_world_state"]["entities"])


def start_units(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The units at the start of a run."""
    return dict(package["initial_world_state"]["entities"])


def events_of(package: dict[str, Any], *kinds: str) -> list[dict[str, Any]]:
    """The run's events of these types, in order."""
    return [e for e in package["event_memory"] if e["event_type"] in kinds]


def damage(event: dict[str, Any]) -> float:
    """hp an ATTACK took from its target."""
    before = float(event["before_state"].get("state", {}).get("hp", 0))
    after = float(event["after_state"].get("state", {}).get("hp", 0))
    return max(0.0, before - after)


def rejected(
    package: dict[str, Any], actors: set[str], system: str | None = None
) -> list[dict[str, Any]]:
    """
    The rejected actions of these units (only those system decided, when
    given): tick, unit, action type, reason.
    """
    return [
        {
            "tick": e["time"],
            "actor_id": e["source"]["actor_id"],
            "action_type": e["data"].get("action_type"),
            "reason": e["data"].get("reason"),
        }
        for e in events_of(package, "ACTION_REJECTED")
        if e["source"]["actor_id"] in actors
        and system in (None, e["source"]["system_id"])
    ]


def unit_report(package: dict[str, Any], entity_id: str) -> dict[str, Any]:
    """One unit's run: status, hp lost, damage dealt and taken, kills."""
    start = start_units(package)[entity_id]
    end = units(package)[entity_id]
    attacks = events_of(package, "ATTACK")
    return {
        "entity_id": entity_id,
        "status": end["state"].get("status", "active"),
        # a destroyed unit's hp can go below zero; it cannot lose more than it had
        "hp_lost": round(
            float(start["state"].get("hp", 0))
            - max(0.0, float(end["state"].get("hp", 0))),
            4,
        ),
        "damage_dealt": round(
            sum(
                (damage(e) for e in attacks if e["source"]["actor_id"] == entity_id),
                0.0,
            ),
            4,
        ),
        "damage_taken": round(
            sum(
                (damage(e) for e in attacks if e["target_entity_id"] == entity_id), 0.0
            ),
            4,
        ),
        "attacks_received": sum(
            1
            for e in events_of(package, "ATTACK", "MISS")
            if e["target_entity_id"] == entity_id
        ),
        "kills": sum(
            1
            for e in events_of(package, "ENTITY_DESTROYED")
            if e["source"]["actor_id"] == entity_id
        ),
    }


def verdict(package: dict[str, Any]) -> dict[str, Any]:
    """The run's result in brief."""
    evaluation = package["evaluation_result"]
    return {
        "winner_or_result": evaluation["winner_or_result"],
        "overall_judgement": evaluation["overall_judgement"],
        "overall_score": evaluation["overall_score"],
        "output_hash": package["reproducibility"]["output_hash"],
    }


def missions(package: dict[str, Any], scenario: dict[str, Any]) -> dict | None:
    """Each faction's mission outcome, when the scenario's domain pack judges one."""
    if not scenario.get("domain"):
        return None
    hook = getattr(load_domain(scenario["domain"]), "mission_outcome", None)
    return None if hook is None else dict(hook(package, scenario))


def domain_outcome(package: dict[str, Any], scenario: dict[str, Any]) -> dict | None:
    """
    What the scenario's domain pack judges after the run, through its hooks:
    the military mission outcome, the city's governance stability score and
    recovery, the airspace outcome.
    None without a domain.
    """
    if not scenario.get("domain"):
        return None
    pack = load_domain(scenario["domain"])
    judged = {}
    for hook in (
        "mission_outcome",
        "governance_outcome",
        "recovery_outcome",
        "airspace_outcome",
    ):
        if hasattr(pack, hook):
            judged[hook] = getattr(pack, hook)(package, scenario)
    return judged


def in_airspace(submission: dict[str, Any], scenarios_dir: Path) -> bool:
    """Whether the submission's scenario runs in the airspace pack (Phase 15)."""
    scenario = load_scenario_named(submission["scenario"], scenarios_dir)
    return scenario.get("domain") == "airspace"


def airspace_summary(results: Results) -> dict[str, Any]:
    """
    The airspace measures over repeated runs (the pack's airspace_outcome):
    how often the assets came through, leaks, detection and response times,
    and why each leak happened.
    """
    runs = []
    for entry in results:
        judged = domain_outcome(entry["result"], entry["scenario"]) or {}
        outcome = judged["airspace_outcome"]
        runs.append(
            {
                "job_id": entry["job"]["job_id"],
                "outcome": outcome["outcome"],
                "leaks": outcome["leaks"],
                "detection_gap": {
                    k: v for k, v in outcome["detection_gap"].items() if k != "threats"
                },
                "response_time": {
                    k: v for k, v in outcome["response_time"].items() if k != "threats"
                },
                "failure_points": outcome["failure_points"],
                "false_alarms": outcome["false_alarms"],
                "fratricide": outcome["fratricide"],
            }
        )
    reasons: dict[str, int] = {}
    for run in runs:
        for point in run["failure_points"]:
            reasons[point["reason"]] = reasons.get(point["reason"], 0) + 1
    detect = [
        r["detection_gap"]["mean_ticks_to_detect"]
        for r in runs
        if r["detection_gap"]["mean_ticks_to_detect"] is not None
    ]
    respond = [
        r["response_time"]["mean"]
        for r in runs
        if r["response_time"]["mean"] is not None
    ]
    react = [
        r["response_time"]["mean_reaction"]
        for r in runs
        if r["response_time"]["mean_reaction"] is not None
    ]
    return {
        "defended_rate": rate([r["outcome"] == "defended" for r in runs]),
        "mean_leaks": average([float(r["leaks"]) for r in runs]),
        "uncovered_share": (
            runs[0]["detection_gap"]["uncovered_share"] if runs else None
        ),
        "mean_ticks_to_detect": average(detect),
        "mean_response_ticks": average(respond),
        "mean_reaction_ticks": average(react),
        "failure_reasons": dict(sorted(reasons.items())),
        "runs": runs,
    }


RISK_THRESHOLDS = (0.2, 0.4, 0.6, 0.8)


def risk_curve(scores: list[float]) -> list[dict[str, float]]:
    """
    The risk curve of a set of runs: for each score threshold, the share of
    runs that ended below it (an exceedance curve read from the bottom).
    """
    return [
        {"score_below": t, "probability": rate([x < t for x in scores])}
        for t in RISK_THRESHOLDS
    ]


def rate(flags: list[bool]) -> float:
    return round(sum(flags) / len(flags), 4) if flags else 0.0


def average(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def branch_stats(stored: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A branch_compare's statistics by branch id ("branch:" dropped)."""
    return {v["variant_id"].removeprefix("branch:"): v for v in stored["variants"]}


def delta(stats: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    """A branch against the baseline, metric by metric."""
    keys = ("win_rate", "failure_frequency", "mean_score", "mean_hp_lost")
    return {key: round(stats[key] - baseline[key], 4) for key in keys}


# ── the nine systems ─────────────────────────────────────────────────────────


class NEXUSAdapter:
    """
    NEXUS hands over a task and takes back the full result package, the
    briefing and the state of the job (section 9: NEXUS ↔ SKYVAULT).
    """

    system = "NEXUS"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        kind = content.get("task_type", "scenario_run")
        if kind == "mission":
            compiled = compile_mission(content["mission"], scenarios_dir)
            return request(self.system, compiled["jobs"], gaps=compiled["gaps"])
        if kind not in NEXUS_TASKS:
            raise ValueError(f"NEXUS task_type must be one of {NEXUS_TASKS}")
        job: dict[str, Any] = {"kind": kind}
        for field in ("batch", "profile", "runtime", "repeat_count"):
            if field in content:
                job[field] = copy.deepcopy(content[field])
        if submission.get("scenario"):
            job["scenario"] = submission["scenario"]
        return request(self.system, [job])

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        if submission["content"].get("task_type") == "mission":
            return self.mission_return(results, submission)
        (entry,) = results
        job, stored = entry["job"], entry["result"]
        report = None
        gaps = []
        single = job["request"]["kind"] == "scenario_run" and stored is not None
        if single:
            if submission["content"].get("report_format", "markdown") == "markdown":
                report = render_markdown(build_briefing({"result_package": stored}))
        elif submission["content"].get("report_format"):
            gaps.append("a briefing is written for one run's result package")
        return {
            "system": self.system,
            "supported": True,
            "result_package": stored,
            "scenario_report": report,
            "domain_outcome": (
                domain_outcome(stored, entry["scenario"]) if single else None
            ),
            "system_status": {
                "job_id": job["job_id"],
                "lifecycle_state": job["lifecycle_state"],
                "governance": job["governance"],
                "handoff": job["summary"].get("handoff"),
                "error": job["error"],
            },
            "gaps": gaps,
        }

    def mission_return(self, results: Results, submission: dict[str, Any]) -> dict:
        """
        A mission's return (Formal Spec 21 Phase I): the mission as SKYVAULT
        read it (assessment, the scenario documents it compiled), what ran,
        the report, and the authority handoff when a decision is NEXUS's /
        陛下's — always for compare_plans, which plan to take.
        """
        mission = validate_nexus_mission(submission["content"]["mission"])
        compiled = compile_mission(mission)
        objective = mission["objective"]
        status = [
            {
                "job_id": e["job"]["job_id"],
                "lifecycle_state": e["job"]["lifecycle_state"],
                "governance": e["job"]["governance"],
                "handoff": e["job"]["summary"].get("handoff"),
                "error": e["job"]["error"],
            }
            for e in results
        ]
        returned: dict[str, Any] = {
            "system": self.system,
            "supported": True,
            "mission": {
                "mission_id": mission["mission_id"],
                "order": mission["order"],
                "objective": objective,
                "assessment": compiled["assessment"],
                "scenarios": compiled["scenarios"],
            },
            "result_package": None,
            "scenario_report": None,
            "system_status": status,
            "authority_handoff": next(
                (s["handoff"] for s in status if s["handoff"]), None
            ),
            "gaps": list(compiled["gaps"]),
        }
        markdown = mission["report_format"] == "markdown"
        if not compiled["assessment"]["needs_skyvault"]:
            returned["gaps"] += [
                "result_package: no world was needed, so nothing ran",
                "scenario_report: no world was needed, so nothing ran",
            ]
            return returned
        if objective == "compare_plans":
            (entry,) = results
            stats = branch_stats(entry["result"])
            baseline = stats["none"]
            records = entry["result"].get("runs", [])
            plans = []
            for plan in mission["plans"]:
                s = stats[plan["plan_id"]]
                scores = [
                    float(r["score"])
                    for r in records
                    if r["variant_id"] == f"branch:{plan['plan_id']}"
                ]
                plans.append(
                    {
                        "plan_id": plan["plan_id"],
                        "description": plan["description"],
                        "runs": s["runs"],
                        "consequences": {
                            "outcomes": s["outcomes"],
                            "win_rate": s["win_rate"],
                            "loss_rate": s["loss_rate"],
                        },
                        "risk": {
                            "failure_frequency": s["failure_frequency"],
                            "mean_risk_events": s["mean_risk_events"],
                        },
                        "risk_curve": risk_curve(scores),
                        "score": {"mean": s["mean_score"], "stdev": s["score_stdev"]},
                        "versus_as_is": delta(s, baseline),
                    }
                )
            returned["plans"] = plans
            handoff = authority_handoff(
                ["conflicting_branches"],
                branch_comparison=entry["result"]["branch_comparison"],
                scenario_id=mission["mission_id"],
                decision="choose which plan goes ahead (the plans exclude each other)",
            )
            returned["authority_handoff"] = handoff
            returned["gaps"].append(
                "result_package: a comparison is many runs; each plan's scenario is "
                "in mission.scenarios and reruns as a test_plan"
            )
            if markdown:
                returned["scenario_report"] = plans_markdown(mission, plans, handoff)
            return returned
        entry = results[0]
        returned["result_package"] = entry["result"]
        if markdown and objective != "explore_failures":
            returned["scenario_report"] = render_markdown(
                build_briefing({"result_package": entry["result"]})
            )
        if objective == "stress_test":
            base = entry["result"]["evaluation_result"]["overall_score"]
            returned["stress_test"] = [
                {
                    "stress": e["job"]["request"]["stress"],
                    **verdict(e["result"]),
                    "score_versus_unstressed": round(
                        e["result"]["evaluation_result"]["overall_score"] - base, 4
                    ),
                }
                for e in results[1:]
            ]
        if objective == "explore_failures":
            returned["result_package"] = None
            returned["failure_map"] = entry["result"]
            returned["gaps"].append(
                "result_package: a failure exploration is many runs; its failure map "
                "is returned instead"
            )
            if markdown:
                returned["scenario_report"] = failure_markdown(mission, entry["result"])
        if returned["scenario_report"] is None:
            returned["gaps"].append("scenario_report: report_format is none")
        return returned


def plans_markdown(
    mission: dict[str, Any],
    plans: list[dict[str, Any]],
    handoff: dict[str, Any] | None,
) -> str:
    """A plan comparison as NEXUS presents it: the order, the plans, who decides."""
    lines = [f"# {mission['mission_id']}", "", f"> {mission['order']}", ""]
    lines += ["| plan | runs | win rate | failure | mean score | vs as is |"]
    lines.append("|---|---|---|---|---|---|")
    for p in plans:
        lines.append(
            f"| {p['plan_id']} | {p['runs']} | {p['consequences']['win_rate']:.2f} | "
            f"{p['risk']['failure_frequency']:.2f} | {p['score']['mean']:.3f} | "
            f"{p['versus_as_is']['mean_score']:+.3f} |"
        )
    if handoff is not None:
        lines += [
            "",
            "## Decision",
            "",
            handoff["package_to_nexus"]["required_decision"],
            "",
            f"Decided by: {', '.join(handoff['decision_authority'])}. "
            "SKYVAULT simulated and recommends; it does not decide.",
        ]
    return "\n".join(lines) + "\n"


def failure_markdown(mission: dict[str, Any], failure_map: dict[str, Any]) -> str:
    """A failure exploration in brief: what crushes the plan, and at what level."""
    lines = [f"# {mission['mission_id']}", "", f"> {mission['order']}", ""]
    crushing = failure_map["crushing_variable"] or "nothing within the levels tried"
    lines.append(f"Crushed first by: {crushing}")
    lines += ["", "| variable | breaking level |", "|---|---|"]
    for v in failure_map["variables"]:
        lines.append(f"| {v['variable']} | {v['breaking_level'] or 'holds'} |")
    return "\n".join(lines) + "\n"


class STARTXAdapter:
    """
    STARTX submits branches; each runs as its own conflict-free variant and
    comes back as consequences, risk, resource pressure and score against
    the baseline with none of them (section 9: STARTX ↔ SKYVAULT).
    """

    system = "STARTX"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        job = {
            "kind": "branch_compare",
            "scenario": submission["scenario"],
            "branches": copy.deepcopy(content["branches"]),
            "repeat_count": content.get("repeat_count", DEFAULT_REPEATS),
        }
        return request(self.system, [job])

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        (entry,) = results
        stats = branch_stats(entry["result"])
        baseline = stats["none"]
        branches = []
        records = entry["result"].get("runs", [])
        for branch in submission["content"]["branches"]:
            s = stats[branch["branch_id"]]
            scores = [
                float(r["score"])
                for r in records
                if r["variant_id"] == f"branch:{branch['branch_id']}"
            ]
            branches.append(
                {
                    "branch_id": branch["branch_id"],
                    "consequences": {
                        "outcomes": s["outcomes"],
                        "win_rate": s["win_rate"],
                        "loss_rate": s["loss_rate"],
                        "draw_rate": s["draw_rate"],
                    },
                    "risk": {
                        "failure_frequency": s["failure_frequency"],
                        "mean_risk_events": s["mean_risk_events"],
                    },
                    "risk_curve": risk_curve(scores),
                    "resource_pressure": {"mean_hp_lost": s["mean_hp_lost"]},
                    "score": {"mean": s["mean_score"], "stdev": s["score_stdev"]},
                    "versus_baseline": delta(s, baseline),
                }
            )
        return {
            "system": self.system,
            "supported": True,
            "branches": branches,
            "baseline": baseline,
            "branch_comparison": entry["result"]["branch_comparison"],
            "gaps": [],
        }


class TACAngelAdapter:
    """
    TAC ANGEL tests local actions: in a running world (world_id) they go
    through its submission window, otherwise they are one scenario run's
    scheduled orders. It gets back the state-action-outcome of its own
    orders and whether they worked (section 9: TAC ANGEL ↔ SKYVAULT).
    """

    system = "TAC_ANGEL"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        actions = [
            {**copy.deepcopy(a), "system_id": self.system} for a in content["actions"]
        ]
        if content.get("world_id"):
            return request(
                self.system,
                world_actions={"world_id": content["world_id"], "actions": actions},
            )
        job = {
            "kind": "scenario_run",
            "scenario": submission["scenario"],
            "runtime": {"scheduled_actions": actions},
        }
        level = content.get("stress_level", "severe")
        stressed = [
            {**copy.deepcopy(job), "stress": {name: level}}
            for name in self.stress_variables(submission, scenarios_dir)
        ]
        gaps = (
            []
            if stressed
            else [
                "stress_test: the scenario names no failure variables to stress "
                "the orders under"
            ]
        )
        return request(self.system, [job, *stressed], gaps=gaps)

    def stress_variables(
        self, submission: dict[str, Any], scenarios_dir: Path
    ) -> list[str]:
        """The scenario's failure variables that apply to it, in its order."""
        scenario = load_scenario_named(submission["scenario"], scenarios_dir)
        names = (scenario.get("failure_exploration") or {}).get(
            "failure_variables"
        ) or scenario["world_contract"].get("failure_variables", [])
        perspective = scenario_perspective(scenario) or ""
        return [
            name
            for name in names
            if variable_for(scenario, name).applies(scenario, perspective)[0]
        ]

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        entry, stressed = results[0], results[1:]
        package, scenario = entry["result"], entry["scenario"]
        mine = [
            t
            for t in build_transitions(package, scenario)
            if t["action"]["system_id"] == self.system
        ]
        ordered = sorted({a["actor_id"] for a in submission["content"]["actions"]})
        refused = rejected(package, set(ordered), self.system)
        return {
            "system": self.system,
            "supported": True,
            "state_action_outcome": mine,
            "tactical_outcome": {
                "orders_carried_out": len(mine) - len(refused),
                "orders_rejected": refused,
                "units": [unit_report(package, u) for u in ordered],
                "missions": missions(package, scenario),
                **verdict(package),
            },
            "stress_test": [
                {
                    "stress": e["job"]["request"]["stress"],
                    "orders_rejected": len(
                        rejected(e["result"], set(ordered), self.system)
                    ),
                    **verdict(e["result"]),
                    "score_versus_unstressed": round(
                        e["result"]["evaluation_result"]["overall_score"]
                        - package["evaluation_result"]["overall_score"],
                        4,
                    ),
                }
                for e in stressed
            ],
            "gaps": (
                []
                if stressed
                else [
                    "stress_test: the scenario names no failure variables to "
                    "stress the orders under"
                ]
            ),
        }


class EIDENAdapter:
    """
    EIDEN-01 supplies intelligence parameters. Those that name a unit and a
    capability the scenario has become variants (each alone, and all
    together) with EIDEN-01 recorded as their provenance; the rest come
    back as gaps. It gets back the gaps, the parameters ranked by how much
    they move the result, and the effect of all of them against the
    baseline (section 9: EIDEN-01 ↔ SKYVAULT).
    """

    system = "EIDEN_01"

    def mapped(
        self, submission: dict[str, Any], scenario: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """The parameters that map onto the scenario, and gaps for the rest."""
        by_id = {unit["entity_id"]: unit for unit in scenario["entities"]}
        mapped, gaps = [], []
        for parameter in submission["content"]["parameters"]:
            entity, capability = parameter.get("entity_id"), parameter.get("capability")
            if entity is None:
                name = parameter.get("world", "?")
                gaps.append(
                    f"world parameter {name}={parameter.get('value')!r}: "
                    f"{scenario['scenario_id']} has no model for it"
                )
            elif entity not in by_id:
                gaps.append(f"{entity}: no such unit in {scenario['scenario_id']}")
            elif capability not in by_id[entity].get("capabilities", {}):
                gaps.append(f"{entity}: the scenario does not model {capability}")
            else:
                mapped.append(parameter)
        return mapped, gaps

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        scenario = load_scenario_named(submission["scenario"], scenarios_dir)
        mapped, gaps = self.mapped(submission, scenario)
        if not mapped:
            return request(self.system, gaps=gaps, supported=False)

        def change(parameters: list[dict[str, Any]]) -> dict[str, Any]:
            changes: dict[str, Any] = {}
            for p in parameters:
                changes.setdefault(p["entity_id"], {"capabilities": {}})
                changes[p["entity_id"]]["capabilities"][p["capability"]] = p["value"]
            return changes

        branches = [
            {
                "branch_id": f"{p['entity_id']}.{p['capability']}",
                "entity_changes": change([p]),
            }
            for p in mapped
        ]
        if len(mapped) > 1:
            branches.append(
                {"branch_id": "all_intel", "entity_changes": change(mapped)}
            )
        job = {
            "kind": "branch_compare",
            "scenario": submission["scenario"],
            "branches": branches,
            "repeat_count": content.get("repeat_count", DEFAULT_REPEATS),
            "data_provenance": {
                "scenario_id": scenario["scenario_id"],
                "sources": [
                    {
                        "source_id": content["source_id"],
                        "source_type": "EIDEN_01",
                        "confidence": content["confidence"],
                        "modified_by": self.system,
                    }
                ],
                "reliability_notes": [
                    f"{p['entity_id']}.{p['capability']} = {p['value']}" for p in mapped
                ],
                "missing_data": gaps,
            },
        }
        return request(self.system, [job], gaps=gaps)

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        (entry,) = results
        stats = branch_stats(entry["result"])
        baseline = stats.pop("none")
        together = stats.get("all_intel") or next(iter(stats.values()))
        effects = sorted(
            (
                (-abs(delta(s, baseline)["mean_score"]), branch_id, delta(s, baseline))
                for branch_id, s in stats.items()
                if branch_id != "all_intel"
            ),
        )
        single = [
            {"parameter": branch_id, "versus_baseline": change}
            for _, branch_id, change in effects
        ]
        job = entry["job"]["request"]
        return {
            "system": self.system,
            "supported": True,
            "gaps": list(job["data_provenance"]["missing_data"]),
            "sensitive_variables": single,
            "effect_on_result": {
                "with_intel": {k: together[k] for k in delta(together, baseline)},
                "baseline": {k: baseline[k] for k in delta(together, baseline)},
                "versus_baseline": delta(together, baseline),
            },
            "provenance": job["data_provenance"],
        }


class AEROGRIDAdapter:
    """
    AEROGRID's coverage settings are judged with its coverage observation
    over a run: how much the side covers, the gaps, and the reaction window
    (ticks between the first enemy in coverage and the first hit on the
    side). In an airspace scenario its sensor configuration runs
    repeat_count times. Either way it gets back the four items of Formal
    Spec 9.2: airspace pressure, reaction window, missed-detection risk
    and system performance.
    """

    system = "AEROGRID"
    gap = "airspace configuration has a model only in airspace scenarios (Phase 15)"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        if in_airspace(submission, scenarios_dir):
            return self.airspace_request(submission, scenarios_dir)
        job = {"kind": "scenario_run", "scenario": submission["scenario"]}
        return request(self.system, [job], gaps=[self.gap])

    def airspace_request(
        self, submission: dict[str, Any], scenarios_dir: Path
    ) -> Request:
        """
        An airspace configuration: each named sensor moved (position),
        retuned (range, detection, false_alarm, low_altitude) or switched on
        or off (online) — only sensors the scenario has (a spare included).
        """
        changes: dict[str, Any] = {}
        tunable = ("range", "detection", "false_alarm", "low_altitude")
        for sensor_id, config in submission["content"].get("sensors", {}).items():
            change: dict[str, Any] = {}
            if "position" in config:
                change["position"] = list(config["position"])
            capabilities = {k: config[k] for k in tunable if k in config}
            if capabilities:
                change["capabilities"] = capabilities
            if "online" in config:
                change["state"] = {"online": bool(config["online"])}
            changes[sensor_id] = change
        extra = {"entity_changes": changes} if changes else {}
        return request(self.system, seeded_runs(submission, {}, scenarios_dir, **extra))

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        if results and results[0]["scenario"].get("domain") == "airspace":
            air = airspace_summary(results)
            runs = air["runs"]
            return {
                "system": self.system,
                "supported": True,
                "airspace_pressure": {
                    "mean_leaks": air["mean_leaks"],
                    "failure_reasons": air["failure_reasons"],
                },
                "reaction_window": {
                    "mean_ticks_to_detect": air["mean_ticks_to_detect"],
                    "mean_reaction_ticks": air["mean_reaction_ticks"],
                    "mean_response_ticks": air["mean_response_ticks"],
                },
                "missed_detection_risk": {
                    "uncovered_share": air["uncovered_share"],
                    "undetected_leaks": air["failure_reasons"].get("undetected", 0),
                    "misidentified": air["failure_reasons"].get("misidentified", 0),
                },
                "system_performance": {
                    "defended_rate": air["defended_rate"],
                    "mean_false_alarms": average(
                        [float(r["false_alarms"]) for r in runs]
                    ),
                    "fratricide": sum(int(r["fratricide"]) for r in runs),
                },
                "airspace": air,
                "gaps": [],
            }
        (entry,) = results
        package, scenario = entry["result"], entry["scenario"]
        content = submission["content"]
        faction = content["faction"]
        threshold = float(content.get("coverage_threshold", 0.8))
        profile = load_observer_profile("aerogrid")
        summaries = [
            o["visible_world_state"]["summary"]
            for o in observations_for_run(
                package, scenario, profile, {"faction": faction}
            )
        ]
        ratios = [s["coverage_ratio"] for s in summaries]
        first_contact = next(
            (tick for tick, s in enumerate(summaries) if s["contacts"]), None
        )
        side = {u for u, e in start_units(package).items() if e["faction"] == faction}
        first_hit = next(
            (
                e["time"]
                for e in events_of(package, "ATTACK")
                if e["target_entity_id"] in side
            ),
            None,
        )
        window = (
            first_hit - first_contact
            if first_hit is not None and first_contact is not None
            else None
        )
        return {
            "system": self.system,
            "supported": True,
            "coverage": {
                "mean_ratio": average(ratios),
                "min_ratio": min(ratios),
                "final_ratio": ratios[-1],
                "ticks_below_threshold": sum(1 for r in ratios if r < threshold),
                "threshold": threshold,
            },
            "coverage_gaps": {
                "max": max(s["gaps"] for s in summaries),
                "final": summaries[-1]["gaps"],
            },
            "reaction_window": {
                "first_contact_tick": first_contact,
                "first_hit_tick": first_hit,
                "ticks": window,
            },
            # Formal Spec 9.2 in grid terms: pressure is how far coverage fell
            # short, a missed detection a tick below the coverage threshold
            "airspace_pressure": {
                "ticks_below_threshold": sum(1 for r in ratios if r < threshold),
                "max_coverage_gaps": max(s["gaps"] for s in summaries),
            },
            "missed_detection_risk": {
                "share_of_ticks_below_threshold": rate([r < threshold for r in ratios]),
                "min_coverage_ratio": min(ratios),
            },
            "system_performance": {"mean_coverage_ratio": average(ratios)},
            "gaps": [self.gap],
        }


class SKYFOXAdapter:
    """
    A SKYFOX drone flies its route under the SKYFOX adapter in repeat_count
    runs. It gets back the mission success rate (every waypoint reached and
    the drone still flying), the route's risk and the moves SKYVAULT
    refused (section 9: SKYFOX ↔ SKYVAULT).
    """

    system = "SKYFOX"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        params: dict[str, Any] = {"route": content["route"]}
        if "energy_floor" in content:
            params["energy_floor"] = content["energy_floor"]
        participant = {
            "participant_id": "skyfox",
            "policy": {"name": "skyfox_adapter", "params": params},
            "controls": {"entity_ids": [content["drone"]]},
        }
        runs = seeded_runs(submission, {"participants": [participant]}, scenarios_dir)
        return request(self.system, runs)

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        content = submission["content"]
        drone = content["drone"]
        route = [list(cell) for cell in content["route"]]
        runs = []
        for entry in results:
            package = entry["result"]
            path = [
                list(units_at[drone]["position"] or [])
                for units_at in history_from_package(package).values()
            ]
            reached = [cell in path for cell in route]
            report = unit_report(package, drone)
            energy = [
                float(units_at[drone]["state"]["energy"])
                for units_at in history_from_package(package).values()
                if (units_at[drone].get("state") or {}).get("energy") is not None
            ]
            lost_links = [
                r
                for r in rejected(package, {drone})
                if str(r["reason"]).startswith("Communication failure")
            ]
            collided = any(
                "collision" in e["tags"] and drone in affected_ids(e)
                for e in package["event_memory"]
            )
            runs.append(
                {
                    "job_id": entry["job"]["job_id"],
                    "waypoints_reached": reached,
                    "mission_success": all(reached) and report["status"] == "active",
                    "path_risk": {
                        "hp_lost": report["hp_lost"],
                        "attacks_received": report["attacks_received"],
                        "destroyed": report["status"] != "active",
                    },
                    "rejected_moves": rejected(package, {drone}),
                    "energy": (
                        {"start": energy[0], "lowest": min(energy), "end": energy[-1]}
                        if energy
                        else None
                    ),
                    "collided": collided,
                    "link_losses": len(lost_links),
                }
            )
        return {
            "system": self.system,
            "supported": True,
            "mission_success_rate": rate([r["mission_success"] for r in runs]),
            "path_risk": {
                "mean_hp_lost": average([r["path_risk"]["hp_lost"] for r in runs]),
                "loss_rate": rate([r["path_risk"]["destroyed"] for r in runs]),
            },
            "rejected_moves": sum(len(r["rejected_moves"]) for r in runs),
            "energy_pressure": energy_pressure(runs),
            "collision_or_link_loss_risk": {
                "collision_rate": rate([r["collided"] for r in runs]),
                "link_loss_rate": rate([r["link_losses"] > 0 for r in runs]),
                "mean_link_losses": average([float(r["link_losses"]) for r in runs]),
            },
            "runs": runs,
            "gaps": (
                []
                if any(r["energy"] for r in runs)
                else ["energy_pressure: the drone carries no energy state"]
            ),
        }


def affected_ids(event: dict[str, Any]) -> set[str]:
    """Every unit an event names: its target and the entities it affected."""
    return {str(event.get("target_entity_id"))} | set(
        event.get("affected", {}).get("entities", [])
    )


def energy_pressure(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """How hard a route drew on the drone's energy over runs, or None without it."""
    known = [r["energy"] for r in runs if r["energy"]]
    if not known:
        return None
    return {
        "mean_lowest_share": average(
            [e["lowest"] / e["start"] if e["start"] else 0.0 for e in known]
        ),
        "mean_used": average([e["start"] - e["end"] for e in known]),
    }


class HADESAdapter:
    """
    HADES defends with the named units under the HADES adapter in
    repeat_count runs. It gets back how effective the defence was, its
    reaction time (first threat HADES sees → first intercept) and the
    coverage gaps: enemies that hit the side without ever being engaged by
    a HADES unit (section 9: HADES ↔ SKYVAULT).
    """

    system = "HADES"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        if in_airspace(submission, scenarios_dir):
            # the defence behaviour HADES submits: its rules of engagement
            policy = {
                "name": "hades_rules",
                "params": dict(submission["content"].get("behavior", {})),
            }
            runs = seeded_runs(submission, {"policy": policy}, scenarios_dir)
            return request(self.system, runs)
        participant = {
            "participant_id": "hades",
            "policy": {"name": "hades_adapter"},
            "controls": {"entity_ids": list(submission["content"]["units"])},
        }
        runs = seeded_runs(submission, {"participants": [participant]}, scenarios_dir)
        return request(self.system, runs)

    def run_report(
        self, package: dict[str, Any], scenario: dict[str, Any], defenders: list[str]
    ) -> dict[str, Any]:
        start = start_units(package)
        faction = start[defenders[0]]["faction"]
        side = {u for u, e in start.items() if e["faction"] == faction}
        profile = load_observer_profile("hades")
        threat_ticks = [
            o["time"]
            for o in observations_for_run(
                package,
                scenario,
                profile,
                {"faction": faction, "actor_id": defenders[0]},
            )
            if o["visible_world_state"]["known_risks"]
        ]
        intercepts = [
            e
            for e in events_of(package, "ACTION_SELECTED")
            if e["source"]["actor_id"] in defenders
            and e["data"].get("intent") == "hades_intercept"
        ]
        first_threat = threat_ticks[0] if threat_ticks else None
        first_intercept = intercepts[0]["time"] if intercepts else None
        engaged = {
            e["target_entity_id"]
            for e in events_of(package, "ATTACK", "MISS")
            if e["source"]["actor_id"] in defenders
        }
        hitters = sorted(
            {
                e["source"]["actor_id"]
                for e in events_of(package, "ATTACK")
                if e["target_entity_id"] in side
            }
        )
        reports = [unit_report(package, u) for u in defenders]
        return {
            "defence_effectiveness": {
                "damage_dealt": round(sum(r["damage_dealt"] for r in reports), 4),
                "kills": sum(r["kills"] for r in reports),
                "side_losses": sum(
                    1
                    for u in side
                    if units(package)[u]["state"].get("status") == "destroyed"
                ),
                "intercepts": len(intercepts),
            },
            "reaction_time": {
                "first_threat_tick": first_threat,
                "first_intercept_tick": first_intercept,
                "ticks": (
                    first_intercept - first_threat
                    if first_threat is not None and first_intercept is not None
                    else None
                ),
            },
            "coverage_gaps": [h for h in hitters if h not in engaged],
        }

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        if results and results[0]["scenario"].get("domain") == "airspace":
            air = airspace_summary(results)
            runs = air["runs"]
            wrong = [
                {
                    "false_alarms": r["false_alarms"],
                    "fratricide": int(r["fratricide"]),
                    "misidentified": sum(
                        1 for f in r["failure_points"] if f["reason"] == "misidentified"
                    ),
                }
                for r in runs
            ]
            return {
                "system": self.system,
                "supported": True,
                "behavior": dict(submission["content"].get("behavior", {})),
                "defence_effectiveness": {
                    "defended_rate": air["defended_rate"],
                    "mean_leaks": air["mean_leaks"],
                },
                "misjudgement_rate": {
                    "runs_with_misjudgement": rate([any(w.values()) for w in wrong]),
                    **{
                        f"mean_{key}": average([float(w[key]) for w in wrong])
                        for key in ("false_alarms", "fratricide", "misidentified")
                    },
                },
                "reaction_time": {
                    "mean_reaction_ticks": air["mean_reaction_ticks"],
                    "mean_response_ticks": air["mean_response_ticks"],
                },
                "coverage_gaps": {
                    "uncovered_share": air["uncovered_share"],
                    "failure_reasons": air["failure_reasons"],
                },
                "airspace": air,
                "gaps": [],
            }
        defenders = list(submission["content"]["units"])
        runs = [
            {
                "job_id": entry["job"]["job_id"],
                **self.run_report(entry["result"], entry["scenario"], defenders),
            }
            for entry in results
        ]
        reactions = [
            r["reaction_time"]["ticks"]
            for r in runs
            if r["reaction_time"]["ticks"] is not None
        ]
        return {
            "system": self.system,
            "supported": True,
            "defence_effectiveness": {
                "mean_damage_dealt": average(
                    [r["defence_effectiveness"]["damage_dealt"] for r in runs]
                ),
                "mean_side_losses": average(
                    [r["defence_effectiveness"]["side_losses"] for r in runs]
                ),
            },
            "misjudgement_rate": None,
            "reaction_time": {
                "mean_reaction_ticks": average([float(t) for t in reactions])
            },
            "coverage_gaps": sorted({g for r in runs for g in r["coverage_gaps"]}),
            "runs": runs,
            "gaps": [
                "misjudgement_rate: a grid scenario has no identification; "
                "misjudgement is modelled in airspace scenarios"
            ],
        }


class CYBERHOUNDAdapter:
    """
    CYBERHOUND describes the information environment: the city's
    information model's parameters (domains/city/information.py) and rumor
    sources. Three variants run repeat_count times each: the city without
    the information environment, with it, and with it but no
    counter-messaging. CYBERHOUND gets back how opinion moved, the pressure
    it put on public order and the risk of backlash (Formal Spec 9.2:
    輿情變化、秩序壓力、反噬風險). A world that is not a city, or a parameter
    the model does not have, comes back as a gap — never a pretend
    simulation.
    """

    system = "CYBERHOUND"
    VARIANTS = ("without_information", "information", "no_counter_messaging")

    def environment(
        self, submission: dict[str, Any], scenarios_dir: Path
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """The information rules CYBERHOUND sets, and gaps for the rest."""
        name = submission.get("scenario")
        if not name:
            return None, ["environment: name a city scenario to run it in"]
        scenario = load_scenario_named(name, scenarios_dir)
        if "city" not in scenario["world_contract"]["rule_set"]:
            return None, [
                f"environment: {scenario['scenario_id']} is not a city; SKYVAULT's "
                "information environment model runs on a city's districts"
            ]
        content = submission["content"]
        parameters = dict(content.get("parameters", {}))
        known = set(INFORMATION_DEFAULTS) - {"sources", "initial"}
        gaps = [
            f"{key}: the information model has no such parameter"
            for key in sorted(set(parameters) - known)
        ]
        rules = {k: v for k, v in parameters.items() if k in known}
        districts = {
            e["entity_id"]
            for e in scenario["entities"]
            if e["entity_type"] == "district"
        }
        sources = []
        for source in content.get("sources", []):
            if source.get("district") in districts:
                sources.append(copy.deepcopy(source))
            else:
                gaps.append(
                    f"source in {source.get('district')!r}: no such district in "
                    f"{scenario['scenario_id']}"
                )
        rules["sources"] = sources
        initial = content.get("initial_pressure", {})
        rules["initial"] = {k: v for k, v in initial.items() if k in districts}
        gaps += [
            f"initial pressure in {k!r}: no such district"
            for k in sorted(set(initial) - districts)
        ]
        return rules, gaps

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        rules, gaps = self.environment(submission, scenarios_dir)
        if rules is None:
            return request(self.system, gaps=gaps, supported=False)
        silent = {**rules, "inform_at": 1000.0}
        runs = (
            seeded_runs(submission, {}, scenarios_dir)
            + seeded_runs(
                submission,
                {},
                scenarios_dir,
                rule_changes={"city": {"information": rules}},
            )
            + seeded_runs(
                submission,
                {},
                scenarios_dir,
                rule_changes={"city": {"information": silent}},
            )
        )
        return request(self.system, runs, gaps=gaps)

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        if not results:
            return {
                "system": self.system,
                "supported": False,
                "gaps": self.environment(submission, SCENARIOS_DIR)[1],
            }
        repeats = len(results) // len(self.VARIANTS)
        groups = {
            name: [
                entry["result"] for entry in results[n * repeats : (n + 1) * repeats]
            ]
            for n, name in enumerate(self.VARIANTS)
        }
        found = {name: information_outcome(runs) for name, runs in groups.items()}
        base, info, silent = (found[name] for name in self.VARIANTS)
        job = results[repeats]["job"]["request"]
        return {
            "system": self.system,
            "supported": True,
            "opinion_change": {
                "mean_pressure_series": info["pressure_series"],
                "final_pressure": info["final_pressure"],
                "inflamed_districts": info["inflamed"],
                "spread_paths": info["spread_paths"],
            },
            "order_pressure": {
                "mean_order_with_information": info["mean_order"],
                "mean_order_without": base["mean_order"],
                "versus_without": round(info["mean_order"] - base["mean_order"], 4),
                "order_lost_to_pressure": info["order_lost_to_pressure"],
                "outcomes": info["outcomes"],
                "outcomes_without": base["outcomes"],
            },
            "backlash_risk": {
                "backlash_per_run": info["backlash_per_run"],
                "patrols_backfired": info["patrols_backfired"],
                "counter_messages_per_run": info["counter_messages_per_run"],
                "counter_messaging_effect": {
                    "mean_order": round(info["mean_order"] - silent["mean_order"], 4),
                    "final_mean_pressure": round(
                        info["final_mean_pressure"] - silent["final_mean_pressure"], 4
                    ),
                },
            },
            "environment": job["rule_changes"]["city"]["information"],
            "repeat_count": repeats,
            "gaps": self.environment(submission, SCENARIOS_DIR)[1],
        }


def information_outcome(packages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    What the information environment did across runs: the city's mean
    pressure tick by tick, each district's final pressure, the spread paths
    (pressure carried from one district to another, summed), public order
    at the end, order lost to pressure (the emotional part of every
    district update), backlash and counter-messaging per run.
    """
    series: dict[int, list[float]] = {}
    finals: dict[str, list[float]] = {}
    paths: dict[tuple[str, str], float] = {}
    orders, lost, backlash, patrols, informs, outcomes = [], [], [], [], [], []
    for package in packages:
        final = package["final_world_state"]["entities"]
        districts = {k: v for k, v in final.items() if v["entity_type"] == "district"}
        orders.append(
            mean(float(d["state"]["public_order"]) for d in districts.values())
        )
        for eid, d in districts.items():
            finals.setdefault(eid, []).append(
                float(d["state"].get("emotional_pressure", 0.0))
            )
        outcomes.append(package["evaluation_result"]["winner_or_result"])
        by_tick: dict[int, dict[str, float]] = {}
        run_lost = run_backlash = run_patrols = run_informs = 0.0
        for event in package["event_memory"]:
            tags, data = event["tags"], event.get("data", {})
            if "information" in tags and "pressure_parts" in data:
                after = event["after_state"]["state"]["emotional_pressure"]
                by_tick.setdefault(event["time"], {})[event["target_entity_id"]] = after
                for row in data["spread_from"]:
                    key = (row["from"], event["target_entity_id"])
                    paths[key] = paths.get(key, 0.0) + row["amount"]
            if "district_update" in tags:
                run_lost += data.get("order_parts", {}).get("emotional", 0.0)
            if "patrol" in tags:
                run_patrols += 1
                run_backlash += "backlash" in tags
            if "inform" in tags:
                run_informs += 1
        current = {eid: 0.0 for eid in districts}
        for tick in sorted(by_tick):
            current.update(by_tick[tick])
            series.setdefault(tick, []).append(mean(current.values()))
        lost.append(run_lost)
        backlash.append(run_backlash)
        patrols.append(run_patrols)
        informs.append(run_informs)
    final_pressure = {eid: round(mean(v), 4) for eid, v in sorted(finals.items())}
    return {
        "pressure_series": [
            {"tick": tick, "mean_pressure": round(mean(values), 4)}
            for tick, values in sorted(series.items())
        ],
        "final_pressure": final_pressure,
        "final_mean_pressure": (
            round(mean(final_pressure.values()), 4) if final_pressure else 0.0
        ),
        "inflamed": sorted(e for e, v in final_pressure.items() if v >= 75),
        "spread_paths": [
            {"from": a, "to": b, "carried": round(v / len(packages), 4)}
            for (a, b), v in sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ],
        "mean_order": round(mean(orders), 4),
        "order_lost_to_pressure": round(-mean(lost), 4),
        "outcomes": dict(sorted(Counter(outcomes).items(), key=lambda kv: str(kv[0]))),
        "backlash_per_run": round(mean(backlash), 4),
        "patrols_backfired": rate_of(sum(backlash), sum(patrols)),
        "counter_messages_per_run": round(mean(informs), 4),
    }


def rate_of(part: float, whole: float) -> float:
    return round(part / whole, 4) if whole else 0.0


class STARGUARDAdapter:
    """
    STAR GUARD's equipment profile replaces one unit of a scenario, run
    repeat_count times next to the scenario as it is. It gets back physical
    feasibility (the actions SKYVAULT refused the unit because of what it
    can do — range, reach, ammunition, terrain, resources — apart from
    refusals of the moment such as an occupied cell) and tactical
    usefulness (the unit and its side, against the baseline)
    (section 9: STAR GUARD ↔ SKYVAULT). drills are orders for the unit at
    given ticks — the maneuvers to check — run in both sets of runs; without
    them only the actions the domain's policy chooses are checked.

    A profile in the Formal Spec section 18 shape (Phase 16: physical,
    engineering and operational parameters) is mapped onto the unit the way
    the virtual test maps it, and the return carries the virtual test's
    equipment_test_result for the submitted scenario and seeds.
    """

    system = "STAR_GUARD"
    known = ("name", "capabilities", "state", "entity_type")
    equipment = (*GROUPS, "equipment_id", "category", "description", "test_targets")

    def gaps(self, profile: dict[str, Any]) -> list[str]:
        modelled = set(self.known) | (
            set(self.equipment) if has_equipment_parameters(profile) else set()
        )
        return [
            f"equipment field {k!r} has no model (give section 18 groups: "
            f"{', '.join(GROUPS)})"
            for k in sorted(set(profile) - modelled)
        ]

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        profile = content["profile"]
        change = {k: copy.deepcopy(profile[k]) for k in self.known if k in profile}
        if has_equipment_parameters(profile):
            scenario = load_scenario_named(submission["scenario"], scenarios_dir)
            unit = next(
                e for e in scenario["entities"] if e["entity_id"] == content["replace"]
            )
            change = unit_changes(
                profile, load_rules(), unit, int(scenario["runtime"]["max_ticks"])
            )
        gaps = self.gaps(profile)
        drills = [
            {
                **copy.deepcopy(d),
                "actor_id": content["replace"],
                "system_id": self.system,
            }
            for d in content.get("drills", [])
        ]
        runtime = {"scheduled_actions": drills} if drills else {}
        equipped = seeded_runs(
            submission,
            runtime,
            scenarios_dir,
            entity_changes={content["replace"]: change},
        )
        baseline = seeded_runs(submission, runtime, scenarios_dir)
        return request(self.system, equipped + baseline, gaps=gaps)

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        content = submission["content"]
        unit = content["replace"]
        half = len(results) // 2
        faction = start_units(results[0]["result"])[unit]["faction"]

        def achieved(entry: dict[str, Any]) -> bool:
            outcome = missions(entry["result"], entry["scenario"]) or {}
            return bool(outcome.get(faction, {}).get("achieved"))

        def side(entries: Results) -> dict[str, Any]:
            reports = [unit_report(e["result"], unit) for e in entries]
            return {
                "unit_survival_rate": rate([r["status"] == "active" for r in reports]),
                "mean_damage_dealt": average([r["damage_dealt"] for r in reports]),
                "mean_hp_lost": average([r["hp_lost"] for r in reports]),
                "mean_score": average(
                    [e["result"]["evaluation_result"]["overall_score"] for e in entries]
                ),
                "mission_achieved_rate": rate([achieved(e) for e in entries]),
            }

        equipped, baseline = results[:half], results[half:]
        refused = [r for e in equipped for r in rejected(e["result"], {unit})]
        limits = [r for r in refused if str(r["reason"]).startswith(CAPABILITY_LIMITS)]
        with_it, without = side(equipped), side(baseline)
        returned: dict[str, Any] = {
            "system": self.system,
            "supported": True,
            # feasible: the equipment never hit a limit of what it can do;
            # refusals of the moment are listed, but do not count against it
            "physical_possibility": {
                "feasible": not limits,
                "capability_limits": limits,
                "situational_rejections": [r for r in refused if r not in limits],
            },
            "tactical_usefulness": {
                "equipped": with_it,
                "baseline": without,
                "versus_baseline": {
                    k: round(with_it[k] - without[k], 4) for k in with_it
                },
            },
            **self.virtual_test(results, submission),
        }
        tested = returned.get("virtual_test")
        returned["engineering_feasibility"] = (
            tested["engineering_feasibility"] if tested else None
        )
        returned["gaps"] = self.gaps(content["profile"]) + (
            []
            if tested
            else [
                "engineering_feasibility: give the profile its section 18 groups "
                f"({', '.join(GROUPS)}) to have it judged"
            ]
        )
        return returned

    def virtual_test(self, results: Results, submission: dict[str, Any]) -> dict:
        """{virtual_test: equipment_test_result} for a section 18 profile, else {}."""
        content = submission["content"]
        profile = content["profile"]
        if not has_equipment_parameters(profile):
            return {}
        half = len(results) // 2
        seeds = [int(e["job"]["request"]["runtime"]["random_seed"]) for e in results]
        result = virtual_test(
            {k: v for k, v in profile.items() if k != "name"},
            scenarios=[submission["scenario"]],
            seeds=seeds[:half],
            replace=content["replace"],
        )
        return {"virtual_test": result}


# Formal Spec 9.2: what each system gets back, item by item, and the key of
# the return that carries it. Every return carries every key (null where a
# world does not model an item, with the reason in gaps).
RETURNS: dict[str, dict[str, str]] = {
    "NEXUS": {
        "result_package": "result package",
        "scenario_report": "scenario report",
        "system_status": "system status",
    },
    "STARTX": {"branches": "分支後果、風險曲線、資源壓力、方案評分"},
    "TAC_ANGEL": {
        "state_action_outcome": "state-action-outcome",
        "tactical_outcome": "戰術成敗",
        "stress_test": "壓測結果",
    },
    "EIDEN_01": {
        "gaps": "情報轉 scenario 的缺口",
        "sensitive_variables": "敏感變量",
        "effect_on_result": "結果影響",
    },
    "AEROGRID": {
        "airspace_pressure": "空域壓力",
        "reaction_window": "反應窗口",
        "missed_detection_risk": "漏檢風險",
        "system_performance": "系統表現",
    },
    "SKYFOX": {
        "mission_success_rate": "任務成功率",
        "path_risk": "路徑風險",
        "energy_pressure": "能源壓力",
        "collision_or_link_loss_risk": "碰撞 / 失聯風險",
    },
    "HADES": {
        "defence_effectiveness": "防禦有效性",
        "misjudgement_rate": "誤判率",
        "reaction_time": "反應時間",
        "coverage_gaps": "覆蓋缺口",
    },
    "CYBERHOUND": {
        "opinion_change": "輿情變化",
        "order_pressure": "秩序壓力",
        "backlash_risk": "反噬風險",
    },
    "STAR_GUARD": {
        "physical_possibility": "physical possibility",
        "engineering_feasibility": "engineering feasibility",
        "tactical_usefulness": "tactical usefulness",
    },
}
# STARTX: each branch carries these
STARTX_BRANCH = ("consequences", "risk_curve", "resource_pressure", "score")

ADAPTERS: dict[str, Any] = {
    adapter.system: adapter
    for adapter in (
        NEXUSAdapter(),
        STARTXAdapter(),
        TACAngelAdapter(),
        EIDENAdapter(),
        AEROGRIDAdapter(),
        SKYFOXAdapter(),
        HADESAdapter(),
        CYBERHOUNDAdapter(),
        STARGUARDAdapter(),
    )
}

KINDS = {
    "NEXUS": "task",
    "STARTX": "branches",
    "TAC_ANGEL": "actions",
    "EIDEN_01": "intel",
    "AEROGRID": "airspace",
    "SKYFOX": "mission",
    "HADES": "defence",
    "CYBERHOUND": "environment",
    "STAR_GUARD": "equipment",
}


def to_request(
    submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
) -> Request:
    """
    A checked submission's request, from its system's adapter.

    Important:
    A system submits its own kind only (TAC ANGEL actions, STARTX branches…);
    anything else is refused with ValueError.
    """
    submission = validate_external_submission(submission)
    submission.setdefault("content", {})
    if KINDS[submission["system"]] != submission["kind"]:
        raise ValueError(
            f"{submission['system']} submits {KINDS[submission['system']]}, "
            f"not {submission['kind']}"
        )
    mission = submission["content"].get("task_type") == "mission"
    if mission:
        named = submission["content"].get("mission", {}).get("scenario")
        if submission.get("scenario") not in (None, named):
            raise ValueError(
                f"the submission names {submission['scenario']} but its mission "
                f"runs in {named}"
            )
    elif submission["system"] != "CYBERHOUND" and not submission.get("scenario"):
        raise ValueError(f"a {submission['system']} submission names a scenario")
    planned: Request = ADAPTERS[submission["system"]].to_request(
        submission, scenarios_dir
    )
    return planned


def to_return(results: Results, submission: dict[str, Any]) -> dict[str, Any]:
    """What the submission's system gets back from these results."""
    submission = validate_external_submission(submission)
    submission.setdefault("content", {})
    returned: dict[str, Any] = ADAPTERS[submission["system"]].to_return(
        results, submission
    )
    return returned
