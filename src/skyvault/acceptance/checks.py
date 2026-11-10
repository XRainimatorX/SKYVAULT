"""The fifteen final acceptance criteria and the fourteen must-haves, as checks.

Important:
Each check returns {passed, evidence}: evidence is what a reader can look
up (job ids, output hashes, event counts, handoff ids, required decisions).
A check that raises fails with the error as its evidence; nothing is
skipped. The checks run in order on one Service and share what they made
(the shared dict), so the fifteen criteria are one continuous session.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..boundary import ROLE
from ..contracts import validate_result_package, validate_world_contract
from ..engine import SkyVaultEngine
from ..observation.history import observations_for_run
from ..observation.profiles import load_observer_profile
from ..report import build_briefing, render_markdown
from ..runtime.sourcing import rebuild_world
from ..scenario_loader import load_scenario
from ..verification import verify_reproducibility
from ..views.screens import overview_view
from ..virtualtest.profile import load_profile
from .service import BASELINE, Service

ROOT = Path(__file__).resolve().parents[3]
SCENARIOS = ROOT / "data" / "scenarios"
BASELINE_HASH = "78aa3fe5bbdf"
CONFLICTING = [
    {
        "system": "TAC_ANGEL",
        "tick": 1,
        "actor_id": "red_08",
        "action_type": "move",
        "target": {"location": [9, 1]},
        "intent": "advance",
    },
    {
        "system": "STARTX",
        "tick": 1,
        "actor_id": "red_08",
        "action_type": "move",
        "target": {"location": [10, 0]},
        "intent": "hold_line",
        "priority": "high",
    },
    {
        "system": "HADES",
        "tick": 1,
        "actor_id": "red_07",
        "action_type": "move",
        "target": {"location": [9, 1]},
        "intent": "cover",
    },
]
STARTX_BRANCHES = [
    {
        "branch_id": "press",
        "actions": [
            {
                "tick": 1,
                "actor_id": "red_08",
                "action_type": "move",
                "target": {"location": [9, 1]},
                "intent": "press",
            }
        ],
    },
    {
        "branch_id": "hold",
        "actions": [
            {
                "tick": 1,
                "actor_id": "red_08",
                "action_type": "move",
                "target": {"location": [10, 0]},
                "intent": "hold",
            }
        ],
    },
]

Check = Callable[[Service, dict[str, Any]], dict[str, Any]]
# the systems the acceptance carries a submission or an action through
SYSTEMS = ("NEXUS", "STARTX", "TAC_ANGEL", "HADES", "AEROGRID", "SKYFOX", "STAR_GUARD")


def _carried(shared: dict[str, Any], system: str, ok: bool) -> None:
    if ok:
        shared.setdefault("systems", set()).add(system)


def _scenario(name: str) -> dict[str, Any]:
    """name is "<scenario_id>" (its v0.1) or "<scenario_id>/<version>"."""
    return load_scenario(SCENARIOS / f"{name if '/' in name else name + '/v0.1'}.json")


# ── the fifteen final acceptance criteria ────────────────────────────────────


def nexus_task(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    done = s.submit(
        {
            "system": "NEXUS",
            "kind": "task",
            "scenario": BASELINE,
            "content": {"task_type": "scenario_run", "report_format": "markdown"},
        }
    )
    returned = done["returned"]
    package = returned["result_package"]
    _carried(shared, "NEXUS", returned["supported"])
    shared["nexus"] = {
        "run_id": done["answer"]["submission_id"],
        "briefing": returned["briefing"],
    }
    return {
        "passed": returned["supported"] and package is not None,
        "evidence": {
            "submission_id": done["answer"]["submission_id"],
            "result": package["evaluation_result"]["winner_or_result"],
            "output_hash": package["reproducibility"]["output_hash"][:12],
        },
    }


def create_world(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    world_id = s.world()
    state = s.get(f"/run/{world_id}").json()["world"]
    shared["world"] = world_id
    return {
        "passed": state["tick"] == 0,
        "evidence": {"world_id": world_id, "lifecycle": state["lifecycle_state"]},
    }


def startx_branch(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    done = s.submit(
        {
            "system": "STARTX",
            "kind": "branches",
            "scenario": BASELINE,
            "content": {"branches": STARTX_BRANCHES, "repeat_count": 2},
        }
    )
    returned = done["returned"]
    branches = sorted(b["branch_id"] for b in returned["branches"])
    _carried(shared, "STARTX", returned["supported"])
    return {
        "passed": returned["supported"] and {"press", "hold"} <= set(branches),
        "evidence": {"branches": branches, "runs": len(done["answer"]["run_ids"])},
    }


def tac_angel_action(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    world_id = shared["world"]
    action = {
        "tick": 1,
        "actor_id": "red_01",
        "action_type": "move",
        "target": {"location": [0, 1]},
        "intent": "tac_angel_probe",
    }
    accepted = s.act(world_id, "TAC_ANGEL", action)
    s.post(f"/api/worlds/{world_id}/advance", {"ticks": 1})
    events = s.get(f"/run/{world_id}/events").json()["event_memory"]
    mine = [e for e in events if e["source"]["system_id"] == "TAC_ANGEL"]
    _carried(shared, "TAC_ANGEL", bool(mine))
    return {
        "passed": accepted.status_code == 202 and bool(mine),
        "evidence": {
            "world_id": world_id,
            "event_id": mine[0]["event_id"] if mine else None,
            "event_type": mine[0]["event_type"] if mine else None,
        },
    }


def airspace_systems(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    scenario = "airspace_defence_001/v0.1"
    returned = {
        "HADES": s.submit(
            {
                "system": "HADES",
                "kind": "defence",
                "scenario": scenario,
                "content": {"behavior": {"salvo": 2}, "repeat_count": 1},
            }
        )["returned"],
        "AEROGRID": s.submit(
            {
                "system": "AEROGRID",
                "kind": "airspace",
                "scenario": scenario,
                "content": {
                    "sensors": {"radar_spare": {"online": True}},
                    "repeat_count": 1,
                },
            }
        )["returned"],
        "SKYFOX": s.submit(
            {
                "system": "SKYFOX",
                "kind": "mission",
                "scenario": scenario,
                "content": {
                    "drone": "skyfox_1",
                    "route": [[7, 6], [8, 6]],
                    "repeat_count": 1,
                },
            }
        )["returned"],
    }
    for system, answer in returned.items():
        _carried(shared, system, answer["supported"])
    return {
        "passed": all(r["supported"] for r in returned.values()),
        "evidence": {
            "HADES_defended_rate": returned["HADES"]["airspace"]["defended_rate"],
            "AEROGRID_uncovered": returned["AEROGRID"]["airspace"]["uncovered_share"],
            "SKYFOX_mission_success": returned["SKYFOX"]["mission_success_rate"],
        },
    }


def star_guard_profile(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    profile = load_profile("pax_test_001")
    returned = s.submit(
        {
            "system": "STAR_GUARD",
            "kind": "equipment",
            "scenario": "military_squad_001/v0.1",
            "content": {"replace": "red_02", "repeat_count": 1, "profile": profile},
        }
    )["returned"]
    judgement = returned["virtual_test"]["final_judgement"]
    _carried(shared, "STAR_GUARD", returned["supported"])
    return {
        "passed": returned["gaps"] == [] and bool(judgement["status"]),
        "evidence": {
            "equipment": profile["equipment_id"],
            "judgement": judgement["status"],
        },
    }


def normal_simulation(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    job = s.job({"kind": "scenario_run", "scenario": BASELINE})
    shared["run"] = job["job_id"]
    summary = job["summary"]
    return {
        "passed": job["lifecycle_state"] == "completed"
        and summary["output_hash"].startswith(BASELINE_HASH),
        "evidence": {
            "job_id": job["job_id"],
            "result": summary["result"],
            "events": summary["events"],
            "output_hash": summary["output_hash"][:12],
        },
    }


def failure_exploration_run(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    answer = s.post(
        "/failure_exploration/run",
        {
            "scenario": "airspace_defence_001/v0.1",
            "repeat_count": 2,
            "source_system": "NEXUS",
        },
    )
    s.wait()
    run = s.get(f"/run/{answer.json()['job_id']}").json()
    # an exploration's result is its failure map
    failure_map = s.get(f"/api/jobs/{run['job_id']}/result").json()
    shared["exploration"] = run
    return {
        "passed": run["lifecycle_state"] == "completed" and bool(failure_map),
        "evidence": {
            "job_id": run["job_id"],
            "crushing_variable": failure_map["crushing_variable"],
            "baseline_survival": failure_map["baseline"]["survival_rate"],
        },
    }


def result_package(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = s.get(f"/run/{shared['run']}/result").json()
    validate_result_package(package)
    shared["package"] = package
    return {
        "passed": "evaluation_result" in package,
        "evidence": {
            "job_id": shared["run"],
            "sections": sorted(package),
            "events": len(package["event_memory"]),
        },
    }


def replay(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    answer = s.post(f"/api/jobs/{shared['run']}/replay")
    s.wait()
    job = s.get(f"/api/jobs/{answer.json()['job_id']}").json()
    return {
        "passed": job["lifecycle_state"] == "completed"
        and job["summary"]["reproduced"] is True
        and job["summary"]["replay_of"] == shared["run"],
        "evidence": {
            "replay_job": job["job_id"],
            "of": job["summary"]["replay_of"],
            "reproduced": job["summary"]["reproduced"],
        },
    }


def human_report(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    briefing = shared["nexus"]["briefing"]
    headings = [line[3:] for line in briefing.splitlines() if line.startswith("## ")]
    return {
        "passed": "Summary" in headings and "What happened" in headings,
        "evidence": {"headings": headings, "lines": len(briefing.splitlines())},
    }


def high_risk_handoff(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    # military squad, seed 45: Phase 7 flags extreme_high_risk_optimization
    job = s.job(
        {
            "kind": "scenario_run",
            "scenario": "military_squad_001/v0.1",
            "runtime": {"random_seed": 45},
        }
    )
    handoff = job["summary"]["handoff"] or {}
    # a run that waits on an authority's decision: the may-not checks try it
    shared["handoff_run"] = job["job_id"]
    return {
        "passed": "high_risk_outcome" in handoff.get("triggers", []),
        "evidence": {
            "job_id": job["job_id"],
            "handoff_id": handoff.get("handoff_id", "")[:12],
            "triggers": handoff.get("triggers"),
            "required_decision": handoff.get("required_decision"),
        },
    }


def conflict_required_decision(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    world_id = s.world()
    for action in CONFLICTING:
        s.act(world_id, str(action["system"]), action)
    held = s.post(f"/api/worlds/{world_id}/advance", {"ticks": 1}).json()
    conflict_id = held["awaiting_decision"]
    package = s.get(f"/conflict/{conflict_id}/package").json()
    record = s.get(f"/conflict/{conflict_id}").json()
    shared["conflict"] = {"id": conflict_id, "package": package, "record": record}
    return {
        "passed": package["recommendation_to_nexus"]["required_decision"] is True
        and bool(record["handoff"]["required_decision"]),
        "evidence": {
            "conflict_id": conflict_id,
            "required_decision": record["handoff"]["required_decision"],
            "branches": sorted(
                s.get(f"/conflict/{conflict_id}/branches").json()["branches"]
            ),
        },
    }


def failure_to_authority(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    handoff = shared["exploration"]["handoff"] or {}
    authorities = handoff.get("decision_authority", [])
    return {
        "passed": "failure_threshold_crossed" in handoff.get("triggers", [])
        and {"NEXUS", "SOVEREIGN"} <= set(authorities),
        "evidence": {
            "job_id": shared["exploration"]["job_id"],
            "decision_authority": authorities,
            "triggers": handoff.get("triggers"),
        },
    }


def role_boundary(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    declared = s.get("/api/boundary").json()
    attempt = s.post(
        f"/run/{shared['handoff_run']}/decision",
        {"decided_by": "SKYVAULT", "decision": "accept"},
    )
    return {
        "passed": declared["role"] == ROLE and attempt.status_code == 403,
        "evidence": {
            "role": declared["role"],
            "skyvault_deciding": attempt.status_code,
            "may_not": len(declared["may_not"]),
        },
    }


ACCEPTANCE: dict[str, Check] = {
    "nexus_task": nexus_task,
    "create_world": create_world,
    "startx_branch": startx_branch,
    "tac_angel_action": tac_angel_action,
    "airspace_systems": airspace_systems,
    "star_guard_profile": star_guard_profile,
    "normal_simulation": normal_simulation,
    "failure_exploration_run": failure_exploration_run,
    "result_package": result_package,
    "replay": replay,
    "human_report": human_report,
    "high_risk_handoff": high_risk_handoff,
    "conflict_required_decision": conflict_required_decision,
    "failure_to_authority": failure_to_authority,
    "role_boundary": role_boundary,
}


# ── the fourteen must-haves ──────────────────────────────────────────────────


def world_contract(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    names = sorted(p.name for p in SCENARIOS.iterdir() if p.is_dir())
    domains = set()
    for name in names:
        scenario = _scenario(name)
        validate_world_contract(scenario["world_contract"])
        domains.add(scenario.get("domain"))
    # every scenario SKYVAULT ships passes the contract, in all three domains
    return {
        "passed": {"military", "city", "airspace"} <= domains,
        "evidence": {"scenarios": names, "domains": sorted(d or "" for d in domains)},
    }


def scenario_grammar(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    versions = sorted(
        str(p.relative_to(SCENARIOS)) for p in SCENARIOS.glob("*/v*.json")
    )
    for path in versions:
        load_scenario(SCENARIOS / path)
    refused = s.post("/api/jobs", {"kind": "scenario_run", "scenario": "no_such/v0.1"})
    return {
        "passed": refused.status_code in (404, 422),
        "evidence": {"versions": len(versions), "unknown_refused": refused.status_code},
    }


def execution_protocol(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    hashes = {
        SkyVaultEngine(_scenario(BASELINE)).run()["reproducibility"]["output_hash"][:12]
        for _ in range(2)
    }
    return {
        "passed": hashes == {BASELINE_HASH},
        "evidence": {"output_hashes": sorted(hashes)},
    }


def observation_contract(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    scenario = _scenario(BASELINE)
    observations = observations_for_run(
        shared["package"], scenario, load_observer_profile("hades"), {"faction": "RED"}
    )
    return {
        "passed": len(observations)
        == shared["package"]["final_world_state"]["tick"] + 1,
        "evidence": {"observer": "hades", "observations": len(observations)},
    }


def action_consequence(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    events = shared["package"]["event_memory"]
    chosen = sum(1 for e in events if e["event_type"] == "ACTION_SELECTED")
    caused = sum(1 for e in events if e["causal_links"])
    return {
        "passed": chosen > 0 and caused > 0,
        "evidence": {"actions": chosen, "linked_events": caused},
    }


def event_memory_replay(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["package"]
    rebuilt = rebuild_world(package["initial_world_state"], package["event_memory"])
    same = rebuilt["entities"] == package["final_world_state"]["entities"]
    return {
        "passed": same,
        "evidence": {"rebuilt_tick": rebuilt["tick"], "matches_final_state": same},
    }


def evaluation_engine(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    verdict = shared["package"]["evaluation_result"]
    return {
        "passed": len(verdict["scores"]) >= 7
        and bool(verdict["overall_judgement"]["status"]),
        "evidence": {
            "axes": len(verdict["scores"]),
            "verdict": verdict["overall_judgement"]["status"],
            "anti_gaming": sorted(verdict["anti_gaming"]["flagged_behaviors"]),
        },
    }


def failure_exploration(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": shared["exploration"]["lifecycle_state"] == "completed",
        "evidence": {"job_id": shared["exploration"]["job_id"]},
    }


def reproducibility(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    verdict = verify_reproducibility(shared["package"], _scenario(BASELINE))
    return {
        "passed": bool(verdict["reproduced"]),
        "evidence": {k: verdict[k] for k in ("reproduced", "input_hash_matches")},
    }


def background_service(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    status = s.get("/api/status").json()
    record = shared["package"]["reproducibility"]["run_metadata"][
        "resource_compute_governance"
    ]
    return {
        "passed": status["jobs"].get("completed", 0) >= 5
        and record["policy_id"] != "ungoverned",
        "evidence": {"jobs": status["jobs"], "policy": record["policy_id"]},
    }


def external_adapter(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    carried = sorted(shared.get("systems", set()))
    return {
        "passed": set(SYSTEMS) <= set(carried),
        "evidence": {"systems_carried_out": carried},
    }


def multi_domain(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    runs = {}
    for name in ("military_squad_001", "city_blackout_001", "airspace_defence_001"):
        job = s.job({"kind": "scenario_run", "scenario": f"{name}/v0.1"})
        runs[name] = (
            job["summary"]["result"]
            if job["lifecycle_state"] == "completed"
            else "failed"
        )
    return {"passed": "failed" not in runs.values(), "evidence": runs}


def ui_report(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    overview = overview_view(shared["package"])
    briefing = render_markdown(build_briefing({"result_package": shared["package"]}))
    return {
        "passed": bool(overview["scenario_id"])
        and briefing.startswith("# SKYVAULT briefing"),
        "evidence": {
            "overview": overview["scenario_id"],
            "briefing_lines": len(briefing.splitlines()),
        },
    }


def authority_handoff(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    record = shared["conflict"]["record"]
    return {
        "passed": record["handoff"]["may_execute_final_decision"] is False,
        "evidence": {
            "conflict_handoff": record["handoff"]["handoff_id"][:12],
            "triggers": record["handoff"]["triggers"],
        },
    }


MUST_HAVE: dict[str, Check] = {
    "world_contract": world_contract,
    "scenario_grammar": scenario_grammar,
    "execution_protocol": execution_protocol,
    "observation_contract": observation_contract,
    "action_consequence": action_consequence,
    "event_memory_replay": event_memory_replay,
    "evaluation_engine": evaluation_engine,
    "failure_exploration": failure_exploration,
    "reproducibility": reproducibility,
    "background_service": background_service,
    "external_adapter": external_adapter,
    "multi_domain": multi_domain,
    "ui_report": ui_report,
    "authority_handoff": authority_handoff,
}


def copy_of(data: Any) -> Any:
    """A deep copy that is plain JSON (what a report may keep)."""
    return json.loads(json.dumps(copy.deepcopy(data), default=str))
