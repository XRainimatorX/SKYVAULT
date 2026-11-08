"""Systems = the nine outside systems, each in its own terms (Formal Spec section 9).

Important:
An adapter turns a system's submission into what SKYVAULT runs —
to_request(submission) → {system, supported, jobs, world_actions, gaps} —
and turns what ran into what section 9 says the system gets back —
to_return(results, submission), where results holds one entry per job,
in order: {job, result, scenario}. A world action has no job: its entry
is the world's result package and scenario.

What SKYVAULT cannot model is never simulated by pretending: the
submission comes back supported false (CYBERHOUND), or the parts that do
not map come back as gaps (EIDEN-01's unknown units, AEROGRID's airspace).
Adapters only read results; none of them chooses for the system.
"""

import copy
import json
from pathlib import Path
from statistics import mean
from typing import Any

from ..contracts import validate_external_submission
from ..domains import load_domain
from ..observation.history import history_from_package, observations_for_run
from ..observation.profiles import load_observer_profile
from ..report import build_briefing, render_markdown
from ..training.transitions import build_transitions

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
DEFAULT_REPEATS = 3
NEXUS_TASKS = ("scenario_run", "batch", "failure_exploration")

Request = dict[str, Any]
Results = list[dict[str, Any]]


def load_scenario_named(name: str, scenarios_dir: Path = SCENARIOS_DIR) -> dict:
    """The scenario a submission names ("<scenario_id>/<version>"), as stored."""
    path = (scenarios_dir / f"{name}.json").resolve()
    if not path.is_relative_to(scenarios_dir.resolve()) or not path.is_file():
        raise ValueError(f"nothing named {name!r} in data/scenarios")
    scenario: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return scenario


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
        (entry,) = results
        job, stored = entry["job"], entry["result"]
        briefing = None
        gaps = []
        if job["request"]["kind"] == "scenario_run" and stored is not None:
            if submission["content"].get("report_format", "markdown") == "markdown":
                briefing = render_markdown(build_briefing({"result_package": stored}))
        elif submission["content"].get("report_format"):
            gaps.append("a briefing is written for one run's result package")
        return {
            "system": self.system,
            "supported": True,
            "result_package": stored,
            "briefing": briefing,
            "system_status": {
                "job_id": job["job_id"],
                "lifecycle_state": job["lifecycle_state"],
                "governance": job["governance"],
                "handoff": job["summary"].get("handoff"),
                "error": job["error"],
            },
            "gaps": gaps,
        }


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
        for branch in submission["content"]["branches"]:
            s = stats[branch["branch_id"]]
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
        return request(self.system, [job])

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        (entry,) = results
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
            "gaps": [],
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
    side). Airspace configuration has no model yet and comes back as a gap
    (section 9: AEROGRID ↔ SKYVAULT).
    """

    system = "AEROGRID"
    gap = "airspace configuration (altitude, corridors) has no model before Phase 15"

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        job = {"kind": "scenario_run", "scenario": submission["scenario"]}
        return request(self.system, [job], gaps=[self.gap])

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
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
            "runs": runs,
            "gaps": [],
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
            "mean_reaction_ticks": average([float(t) for t in reactions]),
            "coverage_gaps": sorted({g for r in runs for g in r["coverage_gaps"]}),
            "runs": runs,
            "gaps": [],
        }


class CYBERHOUNDAdapter:
    """
    CYBERHOUND describes the information environment. SKYVAULT has no model
    of it before Phases 14–16, so nothing runs: every parameter comes back
    as a gap and supported is false — never a pretend simulation.
    """

    system = "CYBERHOUND"

    def gaps(self, submission: dict[str, Any]) -> list[str]:
        names = sorted(submission["content"].get("parameters", {})) or ["environment"]
        return [
            f"{name}: SKYVAULT has no information environment model (Phases 14-16)"
            for name in names
        ]

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        return request(self.system, gaps=self.gaps(submission), supported=False)

    def to_return(self, results: Results, submission: dict[str, Any]) -> dict:
        return {
            "system": self.system,
            "supported": False,
            "gaps": self.gaps(submission),
        }


class STARGUARDAdapter:
    """
    STAR GUARD's equipment profile replaces one unit of a scenario, run
    repeat_count times next to the scenario as it is. It gets back physical
    feasibility (the moves and actions SKYVAULT refused the unit) and
    tactical usefulness (the unit and its side, against the baseline)
    (section 9: STAR GUARD ↔ SKYVAULT).
    """

    system = "STAR_GUARD"
    known = ("name", "capabilities", "state", "entity_type")

    def to_request(
        self, submission: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
    ) -> Request:
        content = submission["content"]
        profile = content["profile"]
        change = {k: copy.deepcopy(profile[k]) for k in self.known if k in profile}
        gaps = [
            f"equipment field {k!r} has no model before Phases 14-16"
            for k in sorted(set(profile) - set(self.known))
        ]
        equipped = seeded_runs(
            submission, {}, scenarios_dir, entity_changes={content["replace"]: change}
        )
        baseline = seeded_runs(submission, {}, scenarios_dir)
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
        with_it, without = side(equipped), side(baseline)
        return {
            "system": self.system,
            "supported": True,
            "physical_feasibility": {
                "feasible": not refused,
                "rejected_actions": refused,
            },
            "tactical_usefulness": {
                "equipped": with_it,
                "baseline": without,
                "versus_baseline": {
                    k: round(with_it[k] - without[k], 4) for k in with_it
                },
            },
            "gaps": [
                f"equipment field {k!r} has no model before Phases 14-16"
                for k in sorted(set(content["profile"]) - set(self.known))
            ],
        }


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
    if submission["system"] != "CYBERHOUND" and not submission.get("scenario"):
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
