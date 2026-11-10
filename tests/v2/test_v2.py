"""Phase 20: Full SKYVAULT v2.0 — the Final Authority Boundary and the acceptance."""

import copy
import json
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skyvault.acceptance.boundary_checks import sovereign_decision
from skyvault.acceptance.report import acceptance_report
from skyvault.acceptance.run import load_list, run_acceptance
from skyvault.boundary import MAY, MAY_NOT, ROLE, declaration, is_skyvault
from skyvault.contracts import (
    ContractError,
    validate_authority_handoff,
    validate_edition,
    validate_governance,
)
from skyvault.editions.manifest import load_edition
from skyvault.editions.redact import leaks
from skyvault.editions.service import create_edition_service
from skyvault.engine import SkyVaultEngine
from skyvault.interface.conflicts import resolve as decide_conflict
from skyvault.interface.handoff import authority_handoff, decide, handoff_triggers
from skyvault.scenario_loader import load_scenario
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from layers import RANK, SRC, layer_of, modules_below  # noqa: E402

REFERENCE = (
    ROOT
    / "tests"
    / "fixtures"
    / "reference"
    / "scenarios"
    / "tactical_reference_001"
    / "v0.1.json"
)
POLICY = load_governance()


@cache
def accepted() -> dict:
    return run_acceptance()


@cache
def reference_handoff() -> dict:
    package = SkyVaultEngine(load_scenario(REFERENCE)).run()
    return authority_handoff(handoff_triggers(result=package), result=package)


# ── the boundary as declared ─────────────────────────────────────────────────


def test_the_boundary_is_the_plan_s_six_mays_and_five_may_nots():
    assert ROLE == "world_environment_engine"
    assert len(MAY) == 6 and len(MAY_NOT) == 5
    assert declaration() == {"role": ROLE, "may": list(MAY), "may_not": list(MAY_NOT)}
    listed = load_list()["boundary"]
    assert len(listed["may"]) == len(MAY) and len(listed["may_not"]) == len(MAY_NOT)


@pytest.mark.parametrize(
    "name,is_it",
    [
        ("SKYVAULT", True),
        ("SkyVault", True),
        ("Sky Vault", True),
        ("sky_vault", True),
        ("SKY-VAULT", True),
        ("sky.vault", True),
        ("NEXUS", False),
        ("SKYVAULTS", False),
        ("skyvault_team", False),
        ("", False),
    ],
)
def test_skyvault_is_recognised_however_it_is_written(name, is_it):
    assert is_skyvault(name) is is_it


# ── the three ways around it, measured at the opening, now refused ───────────


@pytest.mark.parametrize("name", ["SKYVAULT", "Sky Vault", "sky_vault"])
def test_a_governance_policy_cannot_make_skyvault_an_authority(name):
    with pytest.raises(ContractError, match="never the one who decides"):
        validate_governance({**POLICY, "decision_authorities": ["NEXUS", name]})


def test_an_edition_cannot_make_skyvault_an_authority():
    with pytest.raises(ContractError, match="never the one who decides"):
        validate_edition(
            {**load_edition("commercial"), "decision_authorities": ["SkyVault"]}
        )


def test_a_handoff_cannot_name_skyvault_and_skyvault_never_decides():
    package = SkyVaultEngine(load_scenario(REFERENCE)).run()
    with pytest.raises(ContractError):
        authority_handoff(
            handoff_triggers(result=package), result=package, authorities=("SKYVAULT",)
        )
    with pytest.raises(PermissionError, match="never decides"):
        decide(reference_handoff(), "SKYVAULT", "accept")
    # even a handoff made by hand, past the contract, with SKYVAULT in its list
    forged = {**reference_handoff(), "decision_authority": ["SKYVAULT"]}
    with pytest.raises(PermissionError, match="never decides"):
        decide(forged, "SKYVAULT", "accept")
    with pytest.raises(ContractError):
        validate_authority_handoff(
            {
                **reference_handoff(),
                "decided_by": "Sky Vault",
                "status": "decided",
                "decision": "x",
            }
        )


def test_a_conflict_cannot_be_decided_by_skyvault_even_when_listed():
    record = {
        "conflict_id": "conflict_000001",
        "status": "awaiting_decision",
        "branches": {"none": []},
        "handoff": {"decision_authority": ["SKYVAULT", "NEXUS"]},
    }
    with pytest.raises(PermissionError, match="never decides"):
        decide_conflict(record, "none", "SKYVAULT")


def test_an_authority_still_decides_and_the_defaults_are_unchanged():
    decided = decide(reference_handoff(), "SOVEREIGN", "accept")
    assert decided["status"] == "decided" and decided["decided_by"] == "SOVEREIGN"
    assert validate_governance(POLICY) == POLICY
    assert reference_handoff()["decision_authority"] == ["NEXUS", "SOVEREIGN"]


@pytest.mark.parametrize("edition_id", ["internal", "commercial"])
def test_both_editions_state_the_boundary(edition_id):
    edition = load_edition(edition_id)
    client = TestClient(create_edition_service(edition, SQLiteStore(), None, POLICY))
    stated = client.get("/api/boundary").json()
    assert stated["role"] == ROLE
    assert len(stated["may"]) == 6 and len(stated["may_not"]) == 5
    assert leaks(stated, load_edition("commercial")) == [] or edition_id == "internal"


# ── the acceptance, run together ─────────────────────────────────────────────


def test_every_criterion_must_have_and_boundary_check_passes_with_evidence():
    result = accepted()
    assert result["counts"] == {
        "acceptance": {"passed": 15, "of": 15},
        "must_have": {"passed": 14, "of": 14},
        "may": {"passed": 6, "of": 6},
        "may_not": {"passed": 5, "of": 5},
    }
    assert result["passed"] is True
    rows = (
        result["acceptance"]
        + result["must_have"]
        + result["boundary"]["may"]
        + result["boundary"]["may_not"]
    )
    assert all(row["evidence"] and "error" not in row["evidence"] for row in rows)


def test_the_evidence_is_what_a_reader_can_look_up():
    rows = {r["id"]: r["evidence"] for r in accepted()["acceptance"]}
    # the system baseline (Phase 21): military_urban_001 v0.2
    assert rows["normal_simulation"]["output_hash"] == "78aa3fe5bbdf"
    assert rows["normal_simulation"]["events"] == 528
    assert rows["normal_simulation"]["result"] == "no_winner_duration_limit"
    assert rows["high_risk_handoff"]["triggers"] == ["high_risk_outcome"]
    assert rows["failure_to_authority"]["decision_authority"] == ["NEXUS", "SOVEREIGN"]
    assert rows["replay"]["reproduced"] is True
    assert rows["role_boundary"]["skyvault_deciding"] == 403
    may_not = {r["id"]: r["evidence"] for r in accepted()["boundary"]["may_not"]}
    assert may_not["override_nexus"]["decided_by"] == "NEXUS"
    assert may_not["override_startx"]["intent_as_submitted"] == ["hold_line"]


def test_every_listed_item_has_a_check():
    listed = load_list()
    result = accepted()
    assert [r["id"] for r in result["acceptance"]] == [
        i["id"] for i in listed["acceptance"]
    ]
    assert [r["id"] for r in result["must_have"]] == [
        i["id"] for i in listed["must_have"]
    ]


class Broken:
    """A service on which SKYVAULT's decision would be accepted."""

    def post(self, path, body=None):
        class Answer:
            status_code = 200

        return Answer()


def test_the_acceptance_sees_a_broken_boundary():
    outcome = sovereign_decision(Broken(), {"handoff_run": "job_000001"})
    assert outcome["passed"] is False
    assert set(outcome["evidence"].values()) == {200}


def test_a_check_that_breaks_fails_with_its_error_and_nothing_is_skipped(monkeypatch):
    import skyvault.acceptance.run as run_module

    listed = copy.deepcopy(load_list())
    listed["acceptance"].append({"id": "teleport", "title": "SKYVAULT can teleport"})
    monkeypatch.setattr(run_module, "load_list", lambda: listed)

    class Dead:
        def __getattr__(self, name):
            raise ConnectionError("the service is down")

    result = run_module.run_acceptance(Dead())
    assert result["passed"] is False
    assert len(result["acceptance"]) == 16
    assert all(not row["passed"] for row in result["acceptance"])
    assert result["acceptance"][-1]["evidence"] == {
        "error": "LookupError: no check for 'teleport'"
    }
    assert result["acceptance"][0]["evidence"]["error"].startswith("ConnectionError")


def test_the_report_says_accepted_and_shows_each_line():
    text = acceptance_report(accepted())
    assert text.startswith("# SKYVAULT v2.0 acceptance")
    assert "**ACCEPTED** — 15/15 acceptance criteria, 14/14 must-haves" in text
    assert text.count("| ✅ |") == 40 and "❌" not in text
    failed = copy.deepcopy(accepted())
    failed["passed"] = False
    failed["acceptance"][0]["passed"] = False
    shown = acceptance_report(failed)
    assert "**NOT ACCEPTED**" in shown and shown.count("| ❌ |") == 1


def test_run_v2_acceptance_writes_the_evidence_and_the_report(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_v2_acceptance.py"),
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ACCEPTED" in done.stdout and "acceptance  15/15" in done.stdout
    saved = json.loads((tmp_path / "acceptance.json").read_text())
    assert saved["passed"] is True
    assert (
        (tmp_path / "acceptance.md")
        .read_text()
        .startswith("# SKYVAULT v2.0 acceptance")
    )


# ── the layers, as one positive list ─────────────────────────────────────────


def test_every_package_has_a_layer_and_an_unnamed_one_is_core():
    assert layer_of(SRC / "engine.py") == "core"
    assert layer_of(SRC / "boundary.py") == "core"
    assert layer_of(SRC / "contracts" / "base.py") == "core"
    assert layer_of(SRC / "acceptance" / "run.py") == "acceptance"
    assert layer_of(SRC / "a_new_package" / "x.py") == "core"
    assert (
        RANK["acceptance"] > RANK["editions"] > RANK["interface"] > RANK["virtualtest"]
    )


def test_nothing_below_the_acceptance_imports_it():
    below = modules_below("acceptance")
    assert SRC / "editions" / "service.py" in below
    assert not any(layer_of(p) == "acceptance" for p in below)
    from layers import imported

    for module in below:
        assert not any("acceptance" in m for m in imported(module)), module


def test_the_acceptance_service_says_what_it_was_refused():
    from skyvault.acceptance.service import Service

    service = Service()
    with pytest.raises(RuntimeError, match="job refused: 404"):
        service.job({"kind": "scenario_run", "scenario": "no_such/v0.1"})
    with pytest.raises(RuntimeError, match="submission refused: 422"):
        service.submit({"system": "NEXUS", "kind": "nonsense"})
    with pytest.raises(RuntimeError, match="world refused"):
        service.world("no_such/v0.1")

    class Stuck:
        def wait_idle(self, timeout):
            return False

    service.queue = Stuck()
    with pytest.raises(TimeoutError):
        service.wait(0.01)


def test_skyvault_is_refused_before_anything_else_about_a_conflict():
    record = {
        "conflict_id": "conflict_000001",
        "status": "decided",
        "decided_by": "NEXUS",
        "branches": {"none": []},
        "handoff": {"decision_authority": ["SKYVAULT", "NEXUS"]},
    }
    # an already decided conflict would say ValueError; SKYVAULT is refused first
    with pytest.raises(PermissionError, match="never decides"):
        decide_conflict(record, "none", "SKYVAULT")


class Answers:
    """A service whose jobs end as the test says."""

    def __init__(self, summary):
        self.summary = summary

    def job(self, request):
        return {
            "job_id": "job_x",
            "lifecycle_state": "completed",
            "summary": self.summary,
        }


def test_a_simulation_that_drifts_from_the_baseline_hash_is_not_accepted():
    from skyvault.acceptance.checks import normal_simulation

    drifted = {
        "output_hash": "deadbeef0000",
        "result": "no_winner_duration_limit",
        "events": 528,
    }
    assert normal_simulation(Answers(drifted), {})["passed"] is False
    pinned = {**drifted, "output_hash": "78aa3fe5bbdfffff"}
    assert normal_simulation(Answers(pinned), {})["passed"] is True


def test_an_adapter_check_needs_every_system_carried_through():
    from skyvault.acceptance.checks import SYSTEMS, external_adapter

    assert external_adapter(None, {"systems": set(SYSTEMS)})["passed"] is True
    missing = set(SYSTEMS) - {"STARTX"}
    outcome = external_adapter(None, {"systems": missing})
    assert (
        outcome["passed"] is False
        and "STARTX" not in outcome["evidence"]["systems_carried_out"]
    )
