"""Spec checks = SKYVAULT 2.0 accepted against the Formal Spec and the Definition.

Important:
Phase 22: the two founding documents decide whether SKYVAULT 2.0 is
accepted, not the development plan written after them. Each check here
answers one criterion of data/v2/spec_acceptance.json — the Formal Spec's
nine hard requirements (§0), its contracts field by field (§2 – §18),
the pass criteria of its maturity phases (§21 A – J) and the Definition
section by section — and returns what it found as evidence. The Phase 20
checks run first, as regression; their results and the runs they made
are in shared.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..compiler import compile_scenario
from ..contracts import validate_scenario
from ..contracts.json_schema import build_json_schemas
from ..domains import load_domain
from ..domains.city.pack import ACTORS as CITY_ACTORS
from ..domains.city.reference import reference_scenarios
from ..domains.city.score import recovery_outcome
from ..editions.manifest import allows, load_edition
from ..engine import SkyVaultEngine
from ..failure import FAILURE_TAXONOMY
from ..interface.api import run_submission
from ..interface.handoff import authority_handoff, decide
from ..interface.missions import assess_mission
from ..interface.systems import ADAPTERS, RETURNS
from ..interface.triangle import run_triangle
from ..observation.profiles import OBSERVERS
from ..reproducibility.versioning import compare_runs
from ..scenario_loader import load_scenario
from ..virtualtest.conditions import TEST_CONDITIONS
from ..virtualtest.external import external_simulation
from ..virtualtest.profile import load_profile, load_rules
from ..virtualtest.run import virtual_test
from ..worldservice.governance import load_governance
from .service import Service
from .spec_fields import SPEC_FIELDS
from .standins import StandInSTARTX, StandInTACAngel

DATA = Path(__file__).resolve().parents[3] / "data"
SYSTEMS = (
    "NEXUS",
    "STARTX",
    "TAC_ANGEL",
    "EIDEN_01",
    "AEROGRID",
    "SKYFOX",
    "HADES",
    "CYBERHOUND",
    "STAR_GUARD",
)
Check = Callable[[Service, dict[str, Any]], dict[str, Any]]


# ── helpers ──────────────────────────────────────────────────────────────────


def _regression(shared: dict[str, Any], *ids: str) -> dict[str, bool]:
    """Whether these Phase 20 checks passed (they ran first, in shared)."""
    rows = shared["regression"]
    return {i: bool(rows.get(i, {}).get("passed")) for i in ids}


def _schema_fields(name: str) -> set[str]:
    """Every property name in a contract's JSON Schema, at any depth."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            found.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(build_json_schemas()[name])
    return found


def _keys(node: Any) -> set[str]:
    """Every key of a document, at any depth."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= _keys(value)
    elif isinstance(node, list):
        for value in node:
            found |= _keys(value)
    return found


def _document(name: str) -> dict[str, Any]:
    """A scenario document from data/scenarios ("<id>/<version>")."""
    loaded: dict[str, Any] = json.loads(
        (DATA / "scenarios" / f"{name}.json").read_text(encoding="utf-8")
    )
    return loaded


def _run(s: Service, scenario: str, **runtime: Any) -> dict[str, Any]:
    """A scenario run through the service: the job and its result package."""
    request: dict[str, Any] = {"kind": "scenario_run", "scenario": scenario}
    if runtime:
        request["runtime"] = runtime
    job = s.job(request)
    if job["lifecycle_state"] != "completed":
        raise RuntimeError(f"{scenario} failed: {job['error']}")
    package: dict[str, Any] = s.get(f"/api/jobs/{job['job_id']}/result").json()
    return {"job": job, "package": package}


def _submit(s: Service) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Carry a submission through the acceptance's own store, synchronously."""
    policy = load_governance()
    return lambda submission: run_submission(submission, s.store, policy)


def _mission(objective: str, **extra: Any) -> dict[str, Any]:
    move = {"action_type": "move", "intent": "advance", "tick": 1}
    plans = [
        {
            "plan_id": "left",
            "actions": [{**move, "actor_id": "red_01", "target": {"location": [1, 1]}}],
        },
        {
            "plan_id": "right",
            "actions": [{**move, "actor_id": "red_05", "target": {"location": [6, 1]}}],
        },
    ]
    return {
        "mission_id": f"acceptance_{objective}",
        "order": "比較兩種城鎮推進方案",
        "objective": objective,
        "scenario": "military_urban_001/v0.2",
        "plans": plans,
        "repeat_count": 1,
        **extra,
    }


def _nexus(mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": "NEXUS",
        "kind": "task",
        "content": {"task_type": "mission", "mission": mission},
    }


def _failure_map(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = s.get(
        f"/api/jobs/{shared['exploration']['job_id']}/result"
    ).json()
    return found


# ── Formal Spec §0: the nine hard requirements ───────────────────────────────


def world_engine(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    worlds = {}
    for name in (
        "military_urban_001/v0.2",
        "city_blackout_001/v0.1",
        "airspace_defence_001/v0.1",
    ):
        package = _run(s, name)["package"]
        protocol = package["execution_protocol"]
        worlds[name] = {
            "steps": len(protocol),
            "space": package["final_world_state"]["space"]["type"],
            "result": package["evaluation_result"]["winner_or_result"],
        }
    return {
        "passed": all(w["steps"] == 14 for w in worlds.values())
        and len({w["space"] for w in worlds.values()}) >= 2,
        "evidence": worlds,
    }


def common_environment(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": set(ADAPTERS) == set(SYSTEMS)
        and set(OBSERVERS) == set(SYSTEMS)
        and set(RETURNS) == set(SYSTEMS),
        "evidence": {
            "adapters": sorted(ADAPTERS),
            "observers": sorted(OBSERVERS),
            "returns": {k: sorted(v) for k, v in RETURNS.items()},
        },
    }


def world_only(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    handoff = authority_handoff(
        ["conflicting_branches"], scenario_id="acceptance", decision="choose"
    )
    if handoff is None:  # pragma: no cover - a trigger always hands off
        raise RuntimeError("a conflicting_branches trigger handed nothing off")
    try:
        decide(handoff, "SKYVAULT", "go")
        refused = False
    except PermissionError:
        refused = True
    may_not = shared["regression_groups"]["may_not"]
    return {
        "passed": refused
        and handoff["skyvault_position"]["may_execute_final_decision"] is False
        and all(row["passed"] for row in may_not),
        "evidence": {
            "skyvault_deciding": "refused" if refused else "accepted",
            "decision_authority": handoff["decision_authority"],
            "may_not_refused": [r["id"] for r in may_not if r["passed"]],
        },
    }


USES = {
    "戰術": "scenarios/military_urban_001",
    "戰略": "missions/city_takeover_branches_001.json",
    "治理": "scenarios/city_takeover_001",
    "城市": "scenarios/city_blackout_001",
    "危機": "scenarios/urban_crisis_test_001",
    "裝備": "virtualtest/profiles",
    "AI": "observers/tac_angel.json",
    "制度": "editions/internal.json",
    "後勤": "scenarios/city_reconstruction_001",
}


def cross_domain(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    present = {use: (DATA / path).exists() for use, path in USES.items()}
    domains = {
        name: load_domain(name).name for name in ("military", "city", "airspace")
    }
    return {
        "passed": all(present.values()) and len(domains) == 3,
        "evidence": {"domains": sorted(domains), "uses": USES},
    }


def star_guard_triple(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    result = virtual_test(load_profile("exo_test_001"))
    parts = {
        k: result[k]["score"]
        for k in (
            "physical_possibility",
            "engineering_feasibility",
            "tactical_usefulness",
        )
    }
    return {
        "passed": all(v is not None for v in parts.values()),
        "evidence": {**parts, "judgement": result["final_judgement"]["status"]},
    }


def external_engineering(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found = {
        name: external_simulation(load_profile(name), load_rules())
        for name in ("msx_test_001", "exo_test_001", "pax_test_001")
    }
    required = {k: v["required"] for k, v in found.items()}
    handed = {k: v["adapter"] for k, v in found.items() if v["required"]}
    return {
        "passed": any(required.values())
        and all(a is not None and a["status"] == "not_run" for a in handed.values()),
        "evidence": {
            "require_external_simulation": required,
            "reasons": {k: v["reasons"][:2] for k, v in found.items() if v["required"]},
            "adapter": {k: a["status"] for k, a in handed.items()},
        },
    }


def background_service(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    contract = s.get("/api/service").json()
    modes = set(contract["operation_modes"])
    wanted = {"standby", "triggered_scenario", "persistent_world", "batch_simulation"}
    return {
        "passed": wanted <= modes
        and contract["service_status"]["health"] in ("normal", "degraded")
        and all(_regression(shared, "result_package", "create_world").values()),
        "evidence": {
            "operation_modes": sorted(modes),
            "health": contract["service_status"]["health"],
            **_regression(shared, "result_package", "create_world"),
        },
    }


def dual_track(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    internal, commercial = load_edition("internal"), load_edition("commercial")
    hidden = [name for name in SYSTEMS if not allows(commercial, "system", name)]
    return {
        "passed": len(hidden) == len(SYSTEMS)
        and all(allows(internal, "system", name) for name in SYSTEMS)
        and set(commercial["domains"]) == set(internal["domains"]),
        "evidence": {
            "commercial_products": commercial["products"],
            "systems_hidden_from_commercial": hidden,
            "shared_domains": commercial["domains"],
        },
    }


def judgement_output(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["package"]
    evaluation = package["evaluation_result"]
    failure_map = _failure_map(s, shared)
    consequences = sum(
        1 for e in package["event_memory"] if e["before_state"] != e["after_state"]
    )
    return {
        "passed": consequences > 0
        and bool(evaluation["scores"])
        and len(failure_map["answers"]) == 7,
        "evidence": {
            "state_changing_events": consequences,
            "verdict": evaluation["overall_judgement"]["status"],
            "failure_map_answers": sorted(failure_map["answers"]),
        },
    }


# ── Formal Spec §2 – §18: the contracts, field by field ──────────────────────


def _contract_check(section: str) -> Check:
    def check(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
        root, contract, fields = SPEC_FIELDS[section]
        if contract == "urban_crisis_test_001":
            have = _keys(
                reference_scenarios()["urban_crisis_test_001"]["world_contract"]
            )
        elif "+" in contract:
            have = set().union(*(_schema_fields(c) for c in contract.split("+")))
        else:
            have = _schema_fields(contract)
        missing = [f for f in fields if f not in have]
        return {
            "passed": not missing,
            "evidence": {
                "spec_example": root,
                "checked_against": contract,
                "fields": len(fields),
                "missing": missing,
            },
        }

    return check


# ── Formal Spec §21: the maturity phases' pass criteria ──────────────────────


def phase_a(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    doc = _document("urban_crisis_test_001/v0.1")
    world = json.loads(
        (DATA / "worlds" / "urban_crisis_test_001.json").read_text(encoding="utf-8")
    )
    parts = {
        "世界": doc["world_binding"]["world_contract_id"],
        "初始條件": sorted(doc["initial_conditions"]),
        "actor": {
            "slots": [s["slot_id"] for s in doc["participants"]["ai_agent_slots"]],
            "acting_units": sorted(
                e["entity_id"]
                for e in doc["initial_conditions"]["entities"]
                if e["entity_type"] in CITY_ACTORS
            ),
            "systems_admitted": world["actor_slots"],
        },
        "限制": doc["execution_settings"]["duration_limit"],
        "評估目標": doc["evaluation"]["primary_metrics"],
        "假設": [a["assumption_id"] for a in doc["assumption_registry"]["assumptions"]],
        "資料來源": [src["source_id"] for src in doc["data_provenance"]["sources"]],
    }
    validate_scenario(doc)
    actors = parts["actor"]
    return {
        "passed": all(bool(v) for v in parts.values())
        and bool(actors["acting_units"] or actors["slots"]),
        "evidence": parts,
    }


def phase_b(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    first = _run(s, "city_blackout_001/v0.1")["package"]
    second = _run(s, "city_blackout_001/v0.1")["package"]
    same = (
        first["reproducibility"]["output_hash"]
        == second["reproducibility"]["output_hash"]
    )
    return {
        "passed": same and bool(first["event_memory"]) and "evaluation_result" in first,
        "evidence": {
            "runs": 2,
            "events": len(first["event_memory"]),
            "same_output": same,
            "verdict": first["evaluation_result"]["overall_judgement"]["status"],
        },
    }


def phase_c(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    old = _run(s, "military_urban_001/v0.1")["package"]
    new = _run(s, "military_urban_001/v0.2")["package"]
    compared = compare_runs(old, new)
    return {
        "passed": _regression(shared, "replay")["replay"]
        and not compared["same_input"]
        and compared["scenario_version"] == {"before": "v0.1", "after": "v0.2"},
        "evidence": {
            **_regression(shared, "replay", "reproducibility"),
            "scenario_version": compared["scenario_version"],
            "outcome": compared["outcome"],
            "overall_score": compared["overall_score"],
            "same_output": compared["same_output"],
        },
    }


def phase_d(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found = _regression(
        shared, "startx_branch", "tac_angel_action", "nexus_task", "result_package"
    )
    return {"passed": all(found.values()), "evidence": found}


def phase_e(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    world = s.world()
    s.post(f"/api/worlds/{world}/advance", {"ticks": 2})
    checkpoints = s.get(f"/api/worlds/{world}/checkpoints").json()
    s.post(f"/api/worlds/{world}/finish")
    s.wait()
    package = s.get(f"/api/jobs/{world}/result").json()
    status = s.get("/api/service").json()["service_status"]
    return {
        "passed": bool(checkpoints) and "evaluation_result" in package,
        "evidence": {
            "world": world,
            "checkpoints": len(checkpoints),
            "result": package["evaluation_result"]["winner_or_result"],
            "health": status["health"],
        },
    }


def phase_f(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    answers = _failure_map(s, shared)["answers"]
    return {
        "passed": len(answers) == 7 and bool(answers["what_must_change"]),
        "evidence": {
            "where": answers["where_it_failed"][:2],
            "why": answers["why_it_failed"][:2],
            "how_fast": answers["how_fast_it_failed"],
            "variable": answers["which_variable_pushed_it_over"],
            "alternative": answers["which_alternative_survived_longer"],
            "must_change": answers["what_must_change"][:2],
        },
    }


PROFILES = {
    "city": "city_blackout_001/v0.1",
    "crisis": "urban_crisis_test_001/v0.1",
    "airspace": "airspace_defence_001/v0.1",
    "logistics": "city_reconstruction_001/v0.1",
    "military": "military_urban_001/v0.2",
}


def phase_g(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    compiled = {}
    for profile, name in PROFILES.items():
        scenario = compile_scenario(validate_scenario(_document(name)))
        compiled[profile] = scenario["world_contract"]["time_model"]["type"]
    info = reference_scenarios()["urban_crisis_test_001"]["world_contract"]
    return {
        "passed": len(compiled) == len(PROFILES)
        and "information" in info["rule_set"]["city"]
        and (DATA / "virtualtest" / "profiles").exists(),
        "evidence": {
            "one_scenario_contract": compiled,
            "information_environment": "urban_crisis_test_001: city.information",
            "equipment": "data/virtualtest/profiles",
        },
    }


def phase_h(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    result = virtual_test(
        load_profile("pax_test_001"), scenarios=["military_squad_001/v0.1"], seeds=[42]
    )
    fails = [p["condition"] for p in result["failure_exploration"]["failure_points"]]
    return {
        "passed": _regression(shared, "star_guard_profile")["star_guard_profile"]
        and bool(fails),
        "evidence": {
            "physical": result["physical_possibility"]["score"],
            "engineering": result["engineering_feasibility"]["score"],
            "tactical": result["tactical_usefulness"]["score"],
            "fails_under": fails,
            "judgement": result["final_judgement"]["status"],
        },
    }


def phase_i(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    quiet = {**_mission("report_status"), "scenario": None, "plans": []}
    asked = s.post("/nexus/mission/assess", quiet).json()["assessment"]
    returned = s.submit(_nexus(_mission("compare_plans")))["returned"]
    handoff = returned["authority_handoff"]
    return {
        "passed": asked["needs_skyvault"] is False
        and bool(returned["plans"])
        and handoff is not None
        and "SKYVAULT" not in handoff["decision_authority"],
        "evidence": {
            "status_report_needs_skyvault": asked["needs_skyvault"],
            "plans_run": [p["plan_id"] for p in returned["plans"]],
            "handed_to": handoff["decision_authority"] if handoff else None,
            "required_decision": (
                handoff["package_to_nexus"]["required_decision"] if handoff else None
            ),
        },
    }


SHELLS = {
    "crisis planning simulator": "crisis_planning",
    "training simulator": "training_aar",
    "urban resilience simulator": "urban_resilience",
    "equipment concept screening tool": "equipment_screening",
    "AI scenario testing platform": "ai_scenario_testing",
    "risk simulation studio": "risk_studio",
}


def phase_j(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    commercial = load_edition("commercial")
    shells = {k: v in commercial["products"] for k, v in SHELLS.items()}
    from ..editions.feedback import contribute, import_contribution

    scenario = load_scenario(DATA / "scenarios" / "city_blackout_001" / "v0.1.json")
    contribution = contribute(scenario, commercial, "urban_resilience")
    imported = import_contribution(contribution, commercial)
    return {
        "passed": all(shells.values()) and not commercial["systems"] and bool(imported),
        "evidence": {
            "shells": shells,
            "core_systems_in_commercial": commercial["systems"],
            "fed_back": contribution["contribution_id"],
        },
    }


# ── the Definition ───────────────────────────────────────────────────────────


def def_not(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["package"]
    deciders: dict[str, set[str]] = {}
    for event in package["event_memory"]:
        if event["event_type"] == "ACTION_SELECTED":
            unit = package["initial_world_state"]["entities"][
                event["source"]["actor_id"]
            ]
            deciders.setdefault(unit["faction"], set()).add(
                event["source"]["system_id"]
            )
    slots = load_scenario(DATA / "scenarios" / "military_urban_001" / "v0.2.json")[
        "world_contract"
    ]["actor_slots"]
    return {
        "passed": world_only(s, shared)["passed"]
        and cross_domain(s, shared)["passed"]
        and bool(slots)
        and all("skyvault" not in d for ds in deciders.values() for d in ds)
        and external_engineering(s, shared)["passed"],
        "evidence": {
            "decides": "never (handoff to NEXUS / SOVEREIGN)",
            "domains": ["military", "city", "airspace"],
            "who_decides_for_each_side": {k: sorted(v) for k, v in deciders.items()},
            "actor_slots": slots,
            "engineering_simulation": "flagged and handed to an external adapter",
        },
    }


def def_what(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["package"]
    world = package["initial_world_state"]
    events = package["event_memory"]
    parts = {
        "空間": world["space"]["type"],
        "時間": package["final_world_state"]["tick"],
        "實體": len(world["entities"]),
        "規則": bool(shared["package"]["reproducibility"]["ruleset_version"]),
        "行動": sum(e["event_type"] == "ACTION_SELECTED" for e in events),
        "事件": len(events),
        "因果": sum(bool(e["causal_links"]) for e in events),
        "狀態變化": sum(e["before_state"] != e["after_state"] for e in events),
        "記錄": "event_memory",
        "結果分析": package["evaluation_result"]["overall_judgement"]["status"],
    }
    return {"passed": all(bool(v) for v in parts.values()), "evidence": parts}


def def_position(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    kinds = {name: adapter.system for name, adapter in ADAPTERS.items()}
    return {
        "passed": set(kinds) == set(SYSTEMS)
        and _regression(shared, "external_adapter")["external_adapter"],
        "evidence": {
            "systems_with_their_own_interface": sorted(kinds),
            **_regression(shared, "external_adapter"),
        },
    }


def def_triangle(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    loop = run_triangle(
        "比較三種城鎮突入方案",
        "military_urban_001/v0.2",
        StandInSTARTX(),
        StandInTACAngel(),
        _submit(s),
        mission_id="acceptance_triangle",
        repeat_count=1,
    )
    order = [(step["step"], step["system"]) for step in loop["steps"]]
    return {
        "passed": order
        == [
            (1, "STARTX"),
            (2, "SKYVAULT"),
            (3, "TAC_ANGEL"),
            (4, "SKYVAULT"),
            (5, "STARTX"),
            (6, "TAC_ANGEL"),
            (7, "NEXUS"),
        ]
        and loop["authority_handoff"] is not None,
        "evidence": {
            "steps": [f"{n}. {who}" for n, who in order],
            "startx_prefers": loop["startx"]["preferred"],
            "tactics": {
                k: loop["tactics"][k]["orders_rejected"] for k in ("before", "after")
            },
            "decided_by": loop["authority_handoff"]["decision_authority"],
            "stand_ins": "STARTX and TAC ANGEL are acceptance stand-ins",
        },
    }


def def_nexus(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    quiet = {**_mission("report_status"), "scenario": None, "plans": []}
    asked = {
        "report_status": assess_mission(quiet)["needs_skyvault"],
        "compare_plans": assess_mission(_mission("compare_plans"))["needs_skyvault"],
    }
    return {
        "passed": asked == {"report_status": False, "compare_plans": True},
        "evidence": asked,
    }


def def_uses_a(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found = {
        "交火": [
            p.parent.name for p in (DATA / "scenarios").glob("military_*/v0.1.json")
        ],
        "TAC ANGEL 訓練場": (DATA / "observers" / "tac_angel.json").exists(),
        "doctrine 比較": (DATA / "batches" / "military_doctrine.json").exists(),
        "軍官復盤": "training_aar" in load_edition("internal")["products"],
        "裝備戰術價值": _regression(shared, "star_guard_profile")["star_guard_profile"],
    }
    return {"passed": all(bool(v) for v in found.values()), "evidence": found}


def def_uses_b(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    mission = json.loads(
        (DATA / "missions" / "city_takeover_branches_001.json").read_text("utf-8")
    )
    mission["repeat_count"] = 1
    returned = s.submit(_nexus(mission))["returned"]
    plans = {p["plan_id"]: p["risk"]["failure_frequency"] for p in returned["plans"]}
    return {
        "passed": set(plans)
        == {"assault", "blockade", "negotiate", "restore_supply_first"}
        and returned["authority_handoff"] is not None,
        "evidence": {
            "branches_failure_frequency": plans,
            "logistics": "supply_delay, resource_shortage (city failure variables)",
            "handed_to": returned["authority_handoff"]["decision_authority"],
        },
    }


def def_uses_c(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    crisis = SkyVaultEngine(
        copy.deepcopy(reference_scenarios()["urban_crisis_test_001"])
    ).run()
    rebuilt_scenario = reference_scenarios()["city_reconstruction_001"]
    rebuilt = SkyVaultEngine(copy.deepcopy(rebuilt_scenario)).run()
    tags = {t for e in crisis["event_memory"] for t in e["tags"]}
    recovery = recovery_outcome(rebuilt, rebuilt_scenario)
    found = {
        "停電": "blackout" in tags,
        "災害應變": sorted(tags & {"flood", "fire", "roads"}),
        "治安恢復": crisis["evaluation_result"]["winner_or_result"],
        "民心與秩序": sorted(tags & {"information", "inform", "backlash"}),
        "戰後重建": recovery["recovered"],
    }
    return {"passed": all(bool(v) for v in found.values()), "evidence": found}


def def_uses_d(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    systems = ("EIDEN_01", "AEROGRID", "SKYFOX", "HADES", "CYBERHOUND")
    contract = build_json_schemas()["external_submission"]
    return {
        "passed": all(name in ADAPTERS for name in systems)
        and "system" in contract["properties"],
        "evidence": {
            "adapters": list(systems),
            "unknown_new_systems": "external_submission contract + adapter registry",
        },
    }


def def_star_guard(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    items = sum(len(kind) for kind in TEST_CONDITIONS.values())
    return {
        "passed": star_guard_triple(s, shared)["passed"] and items > 0,
        "evidence": {
            "kinds": sorted(TEST_CONDITIONS),
            "conditions_mapped": items,
            "triple": "physical → engineering → tactical",
        },
    }


def def_commercial(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found = dual_track(s, shared)
    return {
        "passed": found["passed"],
        "evidence": {
            **found["evidence"],
            "core_kept": "internal edition mounts every system",
        },
    }


def def_final(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    rows = sum(len(plan["failures"]) for plan in FAILURE_TAXONOMY.values())
    answers = _failure_map(s, shared)["answers"]
    return {
        "passed": rows > 0 and bool(answers["what_must_change"]),
        "evidence": {
            "ways_plans_are_made_to_fail": rows,
            "what_must_change": answers["what_must_change"][:2],
        },
    }


SPEC_CHECKS: dict[str, Check] = {
    "world_engine": world_engine,
    "common_environment": common_environment,
    "world_only": world_only,
    "cross_domain": cross_domain,
    "star_guard_triple": star_guard_triple,
    "external_engineering": external_engineering,
    "background_service": background_service,
    "dual_track": dual_track,
    "judgement_output": judgement_output,
    **{
        f"spec_{section.replace('.', '_')}": _contract_check(section)
        for section in SPEC_FIELDS
    },
    "phase_a": phase_a,
    "phase_b": phase_b,
    "phase_c": phase_c,
    "phase_d": phase_d,
    "phase_e": phase_e,
    "phase_f": phase_f,
    "phase_g": phase_g,
    "phase_h": phase_h,
    "phase_i": phase_i,
    "phase_j": phase_j,
    "def_not": def_not,
    "def_what": def_what,
    "def_position": def_position,
    "def_triangle": def_triangle,
    "def_nexus": def_nexus,
    "def_uses_a": def_uses_a,
    "def_uses_b": def_uses_b,
    "def_uses_c": def_uses_c,
    "def_uses_d": def_uses_d,
    "def_star_guard": def_star_guard,
    "def_commercial": def_commercial,
    "def_final": def_final,
}
