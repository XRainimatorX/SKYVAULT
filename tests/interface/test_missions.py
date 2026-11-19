"""Phase 22: NEXUS missions (Formal Spec 21 Phase I) and the triangle loop."""

import copy
from functools import cache

import pytest
from fastapi.testclient import TestClient

from skyvault.acceptance.standins import StandInSTARTX, StandInTACAngel
from skyvault.compiler import compile_scenario
from skyvault.contracts import ContractError, validate_nexus_mission
from skyvault.engine import SkyVaultEngine
from skyvault.interface.api import run_submission
from skyvault.interface.missions import assess_mission, compile_mission
from skyvault.interface.triangle import run_triangle
from skyvault.worldservice.api import create_world_service
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import NotFound, execute_job
from skyvault.worldservice.queues import InProcessQueue
from skyvault.worldservice.store import SQLiteStore

WORLD = "military_urban_001/v0.2"
ORDER = "比較兩種城鎮推進方案"


def order(actor: str, cell: list[int], tick: int = 1) -> dict:
    return {
        "tick": tick,
        "actor_id": actor,
        "action_type": "move",
        "target": {"location": cell},
        "intent": "advance",
    }


def mission(objective: str = "compare_plans", **extra) -> dict:
    plans = [
        {"plan_id": "left", "actions": [order("red_01", [1, 1])]},
        {"plan_id": "right", "actions": [order("red_05", [6, 1])]},
    ]
    base = {
        "mission_id": "m1",
        "order": ORDER,
        "objective": objective,
        "scenario": WORLD,
        "plans": plans if objective == "compare_plans" else plans[:1],
        "repeat_count": 2,
    }
    return {**base, **extra}


def nexus(given: dict) -> dict:
    return {
        "system": "NEXUS",
        "kind": "task",
        "content": {"task_type": "mission", "mission": given},
    }


@cache
def carried(objective: str) -> dict:
    given = mission(objective)
    if objective == "explore_failures":
        given["plans"] = []
        given["repeat_count"] = 1
    if objective == "report_status":
        given = {k: v for k, v in given.items() if k != "scenario"}
        given["plans"] = []
    return run_submission(nexus(given), SQLiteStore(), load_governance())


# ── the mission contract ─────────────────────────────────────────────────────


def test_a_mission_fills_its_defaults():
    full = validate_nexus_mission(mission())
    assert full["stress_level"] == "severe" and full["report_format"] == "markdown"
    assert full["plans"][0]["entity_changes"] is None


@pytest.mark.parametrize(
    "change, problem",
    [
        ({"plans": []}, "at least two plans"),
        ({"scenario": None}, "names its scenario"),
        ({"objective": "test_plan"}, "one plan at most"),
        ({"order": ""}, "order"),
        ({"objective": "decide"}, "objective"),
    ],
)
def test_a_mission_that_does_not_fit_its_objective_is_refused(change, problem):
    with pytest.raises(ContractError, match=problem):
        validate_nexus_mission({**mission(), **change})


def test_plan_ids_are_unique():
    given = mission()
    given["plans"][1]["plan_id"] = "left"
    with pytest.raises(ContractError, match="unique"):
        validate_nexus_mission(given)


# ── assessment and the mission-to-scenario compiler ──────────────────────────


@pytest.mark.parametrize(
    "objective", ["compare_plans", "test_plan", "stress_test", "explore_failures"]
)
def test_a_question_about_consequences_needs_a_world(objective):
    assessed = assess_mission(mission(objective))
    assert assessed["needs_skyvault"] is True
    assert assessed["reason"].startswith(objective)


def test_a_status_report_needs_no_world():
    given = {**mission(), "objective": "report_status", "scenario": None, "plans": []}
    assert assess_mission(given)["needs_skyvault"] is False
    assert compile_mission(given) == {
        "assessment": assess_mission(given),
        "jobs": [],
        "scenarios": {},
        "gaps": [],
    }


def test_each_plan_compiles_to_a_section_3_3_scenario_version():
    compiled = compile_mission(mission())
    assert sorted(compiled["scenarios"]) == ["left", "right"]
    left = compiled["scenarios"]["left"]
    assert left["identity"]["scenario_id"] == "military_urban_001"
    assert left["identity"]["scenario_version"] == "v0.2+m1.left"
    assert left["identity"]["purpose"] == ORDER
    control = left["scenario_version_control"]
    assert control["parent_version"] == "v0.2"
    assert control["change_reason"] == f"NEXUS mission m1: {ORDER}"
    orders = [
        o
        for slot in left["participants"]["system_slots"]
        for o in slot.get("orders", [])
    ]
    assert orders == [{k: v for k, v in order("red_01", [1, 1]).items()}]


def test_a_compare_mission_is_one_branch_compare_of_its_plans():
    (job,) = compile_mission(mission())["jobs"]
    assert job["kind"] == "branch_compare" and job["repeat_count"] == 2
    assert [b["branch_id"] for b in job["branches"]] == ["left", "right"]
    assert job["branches"][0]["actions"][0]["system_id"] == "NEXUS"


def test_a_stress_mission_runs_the_plan_under_each_failure_variable():
    jobs = compile_mission(mission("stress_test", stress_level="moderate"))["jobs"]
    assert jobs[0].get("stress") is None
    assert [list(j["stress"].values()) for j in jobs[1:]] == [["moderate"]] * (
        len(jobs) - 1
    )
    assert len(jobs) > 1


def test_a_plan_that_does_not_make_a_valid_scenario_is_refused_before_running():
    given = mission("test_plan")
    given["plans"][0]["entity_changes"] = {"nobody": {"state": {"hp": 1}}}
    with pytest.raises(NotFound, match="no units"):
        compile_mission(given)


def test_priority_carries_to_every_job():
    jobs = compile_mission(mission("stress_test", priority="urgent"))["jobs"]
    assert {j["priority"] for j in jobs} == {"urgent"}


# ── through NEXUS ────────────────────────────────────────────────────────────


def test_a_compared_mission_hands_the_choice_of_plan_to_nexus():
    returned = carried("compare_plans")["returned"]
    assert [p["plan_id"] for p in returned["plans"]] == ["left", "right"]
    for plan in returned["plans"]:
        assert plan["runs"] == 2
        assert {"consequences", "risk", "risk_curve", "score", "versus_as_is"} <= set(
            plan
        )
    handoff = returned["authority_handoff"]
    assert handoff["reason"] == ["conflicting_branches"]
    assert handoff["scenario_id"] == "m1"
    assert handoff["package_to_nexus"]["required_decision"].startswith(
        "choose which plan goes ahead"
    )
    assert handoff["skyvault_position"]["may_execute_final_decision"] is False
    assert "SKYVAULT" not in handoff["decision_authority"]
    report = returned["scenario_report"]
    assert report.startswith("# m1") and f"> {ORDER}" in report
    assert "## Decision" in report and "| left | 2 |" in report
    assert returned["result_package"] is None
    assert any(g.startswith("result_package:") for g in returned["gaps"])


def test_a_tested_plan_reruns_from_its_compiled_scenario():
    done = carried("test_plan")
    returned = done["returned"]
    package = returned["result_package"]
    document = returned["mission"]["scenarios"]["left"]
    # the document carries its own version; rerun it under the job's version
    rerun_scenario = compile_scenario(copy.deepcopy(document))
    rerun_scenario["scenario_version"] = package["scenario_version"]
    rerun_scenario["version_control"] = copy.deepcopy(
        done["results"][0]["scenario"]["version_control"]
    )
    rerun_scenario["purpose"] = done["results"][0]["scenario"]["purpose"]
    rerun = SkyVaultEngine(rerun_scenario).run()
    assert (
        rerun["evaluation_result"]["winner_or_result"]
        == package["evaluation_result"]["winner_or_result"]
    )
    assert len(rerun["event_memory"]) == len(package["event_memory"])
    assert returned["scenario_report"].startswith("# SKYVAULT briefing")


def test_a_stressed_mission_reports_each_variable_against_the_plan():
    returned = carried("stress_test")["returned"]
    rows = returned["stress_test"]
    assert rows and all(len(r["stress"]) == 1 for r in rows)
    base = returned["result_package"]["evaluation_result"]["overall_score"]
    for row in rows:
        assert row["score_versus_unstressed"] == round(row["overall_score"] - base, 4)


def test_an_explored_mission_returns_its_failure_map():
    returned = carried("explore_failures")["returned"]
    crushing = returned["failure_map"]["crushing_variable"]
    assert returned["scenario_report"].startswith("# m1")
    assert (
        f"Crushed first by: {crushing or 'nothing within the levels tried'}"
        in returned["scenario_report"]
    )
    for variable in returned["failure_map"]["variables"]:
        assert f"| {variable['variable']} |" in returned["scenario_report"]


def test_a_status_mission_runs_nothing_and_says_so():
    done = carried("report_status")
    assert done["request"]["jobs"] == [] and done["results"] == []
    returned = done["returned"]
    assert returned["mission"]["assessment"]["needs_skyvault"] is False
    assert returned["result_package"] is None and returned["system_status"] == []


# ── over HTTP ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    store, policy = SQLiteStore(str(tmp_path / "m.sqlite")), load_governance()
    queue = InProcessQueue(
        lambda job_id: execute_job(job_id, store, policy),
        policy["max_parallel_runs"],
        policy["queue_policy"],
    )
    yield TestClient(create_world_service(store, queue, policy))
    queue.close()


def test_nexus_can_ask_what_a_mission_compiles_to_without_running_it(client):
    answer = client.post("/nexus/mission/assess", json=mission()).json()
    assert answer["assessment"]["needs_skyvault"] is True
    assert sorted(answer["scenarios"]) == ["left", "right"]
    assert client.get("/api/jobs").json() == []
    refused = client.post("/nexus/mission/assess", json={**mission(), "plans": []})
    assert refused.status_code == 422


def test_a_mission_that_needs_no_world_is_answered_at_once(client):
    given = {**mission(), "objective": "report_status", "scenario": None, "plans": []}
    answer = client.post("/scenario/submit", json=nexus(given)).json()
    assert answer["run_ids"] == []
    assert answer["returned"]["mission"]["assessment"]["needs_skyvault"] is False


def test_a_submission_and_its_mission_must_name_the_same_world(client):
    other = {**nexus(mission()), "scenario": "military_squad_001/v0.1"}
    assert client.post("/scenario/submit", json=other).status_code == 422


# ── the triangle (SKYVAULT Definition IV) ────────────────────────────────────


@cache
def triangle() -> dict:
    store, policy = SQLiteStore(), load_governance()
    return run_triangle(
        "比較三種城鎮突入方案",
        WORLD,
        StandInSTARTX(),
        StandInTACAngel(),
        lambda s: run_submission(s, store, policy),
    )


def test_the_triangle_runs_its_seven_steps_in_order():
    loop = triangle()
    assert [(s["step"], s["system"]) for s in loop["steps"]] == [
        (1, "STARTX"),
        (2, "SKYVAULT"),
        (3, "TAC_ANGEL"),
        (4, "SKYVAULT"),
        (5, "STARTX"),
        (6, "TAC_ANGEL"),
        (7, "NEXUS"),
    ]
    built = loop["steps"][1]
    assert built["assessment"]["needs_skyvault"] is True
    assert set(built["scenarios"]) == {"west_axis", "east_axis", "broad_front"}
    assert loop["steps"][3]["runs"] == 3 * 2


def test_startx_not_skyvault_ranks_the_branches_and_nexus_decides():
    loop = triangle()
    ranked = sorted(
        loop["comparison"],
        key=lambda p: (
            -p["score"]["mean"],
            p["risk"]["failure_frequency"],
            p["plan_id"],
        ),
    )
    assert loop["startx"]["ranking"] == [p["plan_id"] for p in ranked]
    assert loop["startx"]["preferred"] == ranked[0]["plan_id"]
    handoff = loop["authority_handoff"]
    assert handoff["decision_authority"] == ["NEXUS", "SOVEREIGN"]
    assert handoff["status"] == "awaiting_decision"


def test_tac_angel_adjusts_from_what_skyvault_refused():
    tactics = triangle()["tactics"]
    assert tactics["plan_id"] == triangle()["startx"]["preferred"]
    assert tactics["before"]["orders_rejected"] > 0
    assert tactics["after"]["orders_rejected"] < tactics["before"]["orders_rejected"]


def test_nexus_presents_one_report_of_the_whole_loop():
    report = triangle()["report"]
    assert report.startswith("# 比較三種城鎮突入方案")
    assert "Judged from RED's side." in report
    for line in ("1. STARTX", "4. SKYVAULT", "6. TAC_ANGEL", "## Decision"):
        assert line in report
