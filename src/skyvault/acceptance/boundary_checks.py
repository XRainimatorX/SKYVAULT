"""The Final Authority Boundary, checked: six things SKYVAULT may do, five it may not.

Important:
A "may" is shown by doing it. A "may not" is shown by trying it and being
refused — or, where there is nothing to refuse (SKYVAULT never picks a
branch), by showing the output leaves the choice to an authority. Each
check returns {passed, evidence}, like the acceptance checks.
"""

from typing import Any

from ..contracts import ContractError, validate_edition, validate_governance
from ..editions.manifest import load_edition
from ..interface.handoff import AUTHORITIES
from ..worldservice.governance import load_governance
from .checks import CONFLICTING, Check
from .service import Service

# ── may ─────────────────────────────────────────────────────────────────────


def simulate(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": bool(shared.get("run")),
        "evidence": {"job_id": shared.get("run")},
    }


def recommend(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    position = shared["conflict"]["record"]["handoff"]["skyvault_position"]
    return {
        "passed": bool(position["statement"]),
        "evidence": {
            "statement": position["statement"][:160],
            "recommended_next_tests": len(position["recommended_next_tests"]),
        },
    }


def warn(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    verdict = shared["package"]["evaluation_result"]
    flagged = verdict["anti_gaming"]["flagged_behaviors"]
    return {
        "passed": verdict["overall_judgement"]["status"] in ("risky", "fail")
        or bool(flagged),
        "evidence": {
            "verdict": verdict["overall_judgement"]["status"],
            "flagged": sorted(flagged),
        },
    }


def failure_map(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    found = s.get(f"/api/jobs/{shared['exploration']['job_id']}/result").json()
    return {
        "passed": "crushing_variable" in found and "baseline" in found,
        "evidence": {"crushing_variable": found["crushing_variable"]},
    }


def conflict_package(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["conflict"]["package"]
    return {
        "passed": bool(package["branch_runs"]),
        "evidence": {
            "conflict_id": package["conflict_id"],
            "branches": len(package["branch_runs"]),
        },
    }


def reject_invalid(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    unknown = s.post("/api/jobs", {"kind": "scenario_run", "scenario": "no_such/v0.1"})
    path = s.post("/api/jobs", {"kind": "scenario_run", "scenario": "../secrets"})
    nameless = s.post("/api/jobs", {"kind": "scenario_run"})
    codes = [unknown.status_code, path.status_code, nameless.status_code]
    return {
        "passed": all(400 <= c < 500 for c in codes),
        "evidence": {"unknown": codes[0], "path": codes[1], "no_scenario": codes[2]},
    }


# ── may not ─────────────────────────────────────────────────────────────────


def sovereign_decision(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    run_id = shared["handoff_run"]
    codes = {
        name: s.post(
            f"/run/{run_id}/decision", {"decided_by": name, "decision": "accept"}
        ).status_code
        for name in ("SKYVAULT", "Sky Vault", "sky_vault")
    }
    return {"passed": set(codes.values()) == {403}, "evidence": codes}


def override_nexus(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    conflict_id = shared["conflict"]["id"]
    branch = next(iter(s.get(f"/conflict/{conflict_id}/branches").json()["branches"]))
    nexus = s.post(
        "/branch_conflict/resolve",
        {"conflict_id": conflict_id, "branch_id": branch, "decided_by": "NEXUS"},
    )
    skyvault = s.post(
        "/branch_conflict/resolve",
        {"conflict_id": conflict_id, "branch_id": "none", "decided_by": "SKYVAULT"},
    )
    record = s.get(f"/conflict/{conflict_id}").json()
    return {
        "passed": nexus.status_code == 200
        and skyvault.status_code == 403
        and record["decided_by"] == "NEXUS",
        "evidence": {
            "nexus_decided": branch,
            "skyvault_overriding": skyvault.status_code,
            "decided_by": record["decided_by"],
        },
    }


def override_startx(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["conflict"]["package"]
    submitted = next(a for a in CONFLICTING if a["system"] == "STARTX")
    carried = [a for a in package["conflicting_actions"] if a["system_id"] == "STARTX"]
    intent = [a["intent"] for a in carried]
    return {
        "passed": bool(carried) and intent == [submitted["intent"]],
        "evidence": {"startx_proposals": len(carried), "intent_as_submitted": intent},
    }


def replace_human(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    refused = []
    for name, check in (
        ("governance", lambda: validate_governance(
            {**load_governance(), "decision_authorities": ["SKYVAULT"]}
        )),
        ("edition", lambda: validate_edition(
            {**load_edition("internal"), "decision_authorities": ["SkyVault"]}
        )),
    ):  # fmt: skip
        try:
            check()
        except ContractError:
            refused.append(name)
    return {
        "passed": refused == ["governance", "edition"] and "SOVEREIGN" in AUTHORITIES,
        "evidence": {"refused": refused, "default_authorities": list(AUTHORITIES)},
    }


def final_strategy(s: Service, shared: dict[str, Any]) -> dict[str, Any]:
    package = shared["conflict"]["package"]
    recommendation = package["recommendation_to_nexus"]
    handoff = shared["conflict"]["record"]["handoff"]
    picks = {"chosen", "selected", "decision", "chosen_branch"} & set(recommendation)
    return {
        "passed": not picks
        and handoff["may_execute_final_decision"] is False
        and "does not choose" in recommendation["decision_reason"],
        "evidence": {
            "may_execute_final_decision": handoff["may_execute_final_decision"],
            "picks_a_branch": sorted(picks),
        },
    }


MAY: dict[str, Check] = {
    "simulate": simulate,
    "recommend": recommend,
    "warn": warn,
    "failure_map": failure_map,
    "conflict_package": conflict_package,
    "reject_invalid": reject_invalid,
}

MAY_NOT: dict[str, Check] = {
    "sovereign_decision": sovereign_decision,
    "override_nexus": override_nexus,
    "override_startx": override_startx,
    "replace_human": replace_human,
    "final_strategy": final_strategy,
}
