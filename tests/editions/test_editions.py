"""Phase 19: two editions on one core — manifests, redaction, services, products."""

import ast
import copy
import json
import subprocess
import sys
import time
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skyvault.contracts import ContractError, validate_edition
from skyvault.editions.feedback import contribute, import_contribution
from skyvault.editions.manifest import allows, edition_ids, load_edition, public
from skyvault.editions.products import catalogue, product_report, run_product
from skyvault.editions.redact import leaks, redact, redact_text
from skyvault.editions.service import create_edition_service
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.failure import build_failure_map, explore_failures
from skyvault.scenario_loader import default_evaluation_profile, load_scenario
from skyvault.training.filter import split_runs
from skyvault.training.labels import run_labels
from skyvault.training.transitions import build_transitions
from skyvault.worldservice.api import create_world_service, in_process_queue
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/
from layers import imported, modules_below  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "skyvault"
INTERNAL = load_edition("internal")
COMMERCIAL = load_edition("commercial")
POLICY = load_governance()
NAMES = ("NEXUS", "STARTX", "TAC ANGEL", "SOVEREIGN", "HADES", "AEROGRID", "SKYFOX")


def service(edition: dict, systems: list[str] | None = None) -> TestClient:
    edition = copy.deepcopy(edition)
    if systems is not None:
        edition["systems"] = systems
    return TestClient(create_edition_service(edition, SQLiteStore(), None, POLICY))


def wait(client: TestClient, job_id: str) -> dict:
    for _ in range(1200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["lifecycle_state"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"{job_id} did not finish")


@cache
def product(product_id: str) -> dict:
    return run_product(product_id, COMMERCIAL, repeats=2)


# ── editions are data ────────────────────────────────────────────────────────


def test_the_two_committed_editions_are_editions():
    assert edition_ids() == ["commercial", "internal"]
    assert INTERNAL["systems"] == [
        "NEXUS",
        "STARTX",
        "TAC_ANGEL",
        "EIDEN_01",
        "AEROGRID",
        "SKYFOX",
        "HADES",
        "CYBERHOUND",
        "STAR_GUARD",
    ]
    assert COMMERCIAL["systems"] == [] and INTERNAL["redact"] == {}
    assert set(COMMERCIAL["products"]) == set(catalogue()) == set(INTERNAL["products"])


def test_an_unknown_edition_or_a_broken_manifest_is_refused():
    with pytest.raises(ValueError, match="unknown edition 'military'"):
        load_edition("military")
    with pytest.raises(ContractError):
        validate_edition({**COMMERCIAL, "systems": ["SKYNET"]})
    with pytest.raises(ContractError, match="decision_authorities"):
        validate_edition({**COMMERCIAL, "decision_authorities": []})


def test_an_edition_allows_only_what_it_lists():
    assert allows(INTERNAL, "system", "NEXUS")
    assert not allows(COMMERCIAL, "system", "NEXUS")
    assert allows(COMMERCIAL, "job_kind", "batch")
    assert not allows(COMMERCIAL, "job_kind", "branch_compare")
    assert allows(COMMERCIAL, "product", "risk_studio")
    assert public(COMMERCIAL) == {
        "edition_id": "commercial",
        "title": "SKYVAULT Studio",
        "domains": COMMERCIAL["domains"],
        "job_kinds": COMMERCIAL["job_kinds"],
        "products": COMMERCIAL["products"],
    }


# ── redaction ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("NEXUS or the user decides", "Decision Authority or the user decides"),
        ("tac_angel_adapter", "tactical_agent_adapter"),
        ("TAC ANGEL plans", "Tactical Agent plans"),
        ("Tac-Angel", "Tactical Agent"),
        ("recommendation_to_nexus", "recommendation_to_decision_authority"),
        ("hades_rules_of_engagement", "air_defence_operator_rules_of_engagement"),
        ("shades of grey", "shades of grey"),  # a name inside a word is not a name
        ("NEXUSES", "NEXUSES"),
    ],
)
def test_a_name_is_replaced_whole_in_the_style_it_was_written(text, expected):
    assert redact_text(text, COMMERCIAL) == expected


def test_redaction_changes_names_never_numbers_or_shape():
    data = {
        "recommendation_to_nexus": {"decision_reason": "NEXUS decides", "score": 0.5},
        "systems": ["HADES", "planner"],
        "count": 3,
        "flag": True,
        "none": None,
        "pair": ("STARTX", 1),
    }
    out = redact(data, COMMERCIAL)
    assert out == {
        "recommendation_to_decision_authority": {
            "decision_reason": "Decision Authority decides",
            "score": 0.5,
        },
        "systems": ["Air Defence Operator", "planner"],
        "count": 3,
        "flag": True,
        "none": None,
        "pair": ("Strategy Planner", 1),
    }
    assert leaks(data, COMMERCIAL) == ["HADES", "NEXUS", "STARTX", "nexus"]
    assert leaks(out, COMMERCIAL) == []


def test_the_internal_edition_redacts_nothing():
    data = {"recommendation_to_nexus": "NEXUS decides"}
    assert redact(data, INTERNAL) is data
    assert leaks(data, INTERNAL) == []


# ── acceptance 2: the internal core is not broken ────────────────────────────


def paths(app) -> set[tuple[str, frozenset]]:
    return {(r.path, frozenset(getattr(r, "methods", None) or ())) for r in app.routes}


def test_the_internal_edition_is_the_world_service_plus_three_edition_routes():
    store = SQLiteStore()
    plain = create_world_service(store, in_process_queue(store, POLICY), POLICY)
    internal = create_edition_service(INTERNAL, SQLiteStore(), None, POLICY)
    added = paths(internal.app if hasattr(internal, "app") else internal) - paths(plain)
    assert paths(plain) <= paths(internal)
    assert {p for p, _ in added} == {
        "/api/edition",
        "/api/products",
        "/api/products/{product_id}",
    }


def test_the_internal_edition_takes_every_system_and_names_the_core_s_authorities():
    client = service(INTERNAL)
    submitted = client.post(
        "/scenario/submit",
        json={
            "system": "NEXUS",
            "kind": "task",
            "scenario": "tactical_reference_001/v0.1",
            "content": {},
        },
    )
    assert submitted.status_code == 202
    job = wait(client, submitted.json()["run_ids"][0])
    assert job["summary"]["handoff"]["decision_authority"] == ["NEXUS", "SOVEREIGN"]


def test_an_edition_service_runs_the_same_core_to_the_same_hash():
    client = service(COMMERCIAL)
    job_id = client.post(
        "/api/jobs",
        json={"kind": "scenario_run", "scenario": "tactical_reference_001/v0.1"},
    ).json()["job_id"]
    assert wait(client, job_id)["summary"]["output_hash"].startswith("63090026e137")


def test_the_core_imports_no_edition():
    # every module below the editions layer (tests/layers.py: a positive list)
    below = modules_below("editions")
    assert below
    for module in below:
        assert not any("editions" in m for m in imported(module)), module


def test_products_bring_no_simulation_of_their_own():
    tree = ast.parse((SRC / "editions" / "products.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    plain = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    assert "random" not in plain
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert classes == []  # no engine, policy or handler of its own
    assert {"engine", "batch.run", "failure", "virtualtest.run"} <= {
        (m or "").lstrip(".") for m in imported
    }


# ── the commercial shell ─────────────────────────────────────────────────────


def test_the_commercial_shell_mounts_no_system_interface():
    client = service(COMMERCIAL)
    response = client.post(
        "/scenario/submit",
        json={"system": "NEXUS", "kind": "task", "scenario": "x/v0.1", "content": {}},
    )
    assert response.status_code == 404
    assert client.get("/api/edition").json()["edition_id"] == "commercial"


@pytest.mark.parametrize(
    "request_body,detail",
    [
        (
            {
                "kind": "branch_compare",
                "scenario": "tactical_reference_001/v0.1",
                "branches": [],
            },
            "does not run branch_compare jobs",
        ),
        (
            {"kind": "scenario_run", "scenario": "city_blackout_001/v0.1"},
            "does not run the city domain",
        ),
    ],
)
def test_the_commercial_shell_refuses_what_it_does_not_run(request_body, detail):
    narrow = copy.deepcopy(COMMERCIAL)
    narrow["domains"] = ["military"]
    client = TestClient(create_edition_service(narrow, SQLiteStore(), None, POLICY))
    response = client.post("/api/jobs", json=request_body)
    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "not_licensed"
    assert detail in response.json()["detail"]["detail"]


def test_naming_a_system_mounts_its_interface_again_for_it_alone():
    client = service(COMMERCIAL, systems=["NEXUS"])
    body = {"kind": "task", "scenario": "tactical_reference_001/v0.1", "content": {}}
    assert (
        client.post("/scenario/submit", json={"system": "NEXUS", **body}).status_code
        == 202
    )
    refused = client.post(
        "/scenario/submit", json={"system": "STARTX", "kind": "branches", **body}
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["reason"] == "not_licensed"


def test_nothing_the_commercial_shell_returns_names_an_internal_system():
    client = service(COMMERCIAL)
    job_id = client.post(
        "/api/jobs",
        json={"kind": "batch", "batch": "tactical_reference_001", "repeat_count": 2},
    ).json()["job_id"]
    job = wait(client, job_id)
    result = client.get(f"/api/jobs/{job_id}/result").json()
    assert job["lifecycle_state"] == "completed"
    assert leaks(job, COMMERCIAL) == [] and leaks(result, COMMERCIAL) == []
    assert job["summary"]["handoff"]["decision_authority"] == ["customer"]
    reason = result["conflict_package"]["recommendation_to_decision_authority"][
        "decision_reason"
    ]
    assert "Decision Authority or the user decides" in reason
    status = client.get("/api/status").json()
    assert leaks(status, COMMERCIAL) == []


def test_the_same_batch_on_the_internal_core_does_name_them():
    client = service(INTERNAL)
    job_id = client.post(
        "/api/jobs",
        json={"kind": "batch", "batch": "tactical_reference_001", "repeat_count": 2},
    ).json()["job_id"]
    wait(client, job_id)
    result = client.get(f"/api/jobs/{job_id}/result").json()
    assert "NEXUS" in leaks(result, COMMERCIAL)
    assert "recommendation_to_nexus" in result["conflict_package"]


# ── acceptance 1: the products show their value ──────────────────────────────


@pytest.mark.parametrize("product_id", sorted(catalogue()))
def test_every_product_answers_its_question_with_figures_from_a_real_run(product_id):
    result = product(product_id)
    assert result["title"] == catalogue()[product_id]["title"]
    assert result["question"] and result["conclusion"]
    assert result["kpis"] and all(v is not None for v in result["kpis"].values())
    assert leaks(result, COMMERCIAL) == []


def test_the_figures_are_the_core_s_own():
    crisis = product("crisis_planning")["kpis"]
    assert crisis["outcome"] == "order_not_restored"
    assert crisis["most_districts_dark"] == 7 and crisis["cascade_depth"] == 1
    ai = product("ai_scenario_testing")["kpis"]
    assert ai["highest_score"] == "scripted" and ai["flagged_for_gaming"] == [
        "scripted"
    ]
    assert ai["best_honest_agent"] != ai["highest_score"]
    screening = product("equipment_screening")["kpis"]
    assert screening["PAX_TEST_001"]["judgement"] == "redesign"
    resilience = product("urban_resilience")["kpis"]["order_restored_rate_by_delay"]
    assert resilience["1.0"] > resilience["3.0"]


def test_an_honest_winner_is_said_to_be_honest():
    scenario = load_scenario(
        ROOT / "data" / "scenarios" / "military_urban_001" / "v0.1.json"
    )
    result = run_product("ai_scenario_testing", COMMERCIAL, scenario=scenario)
    kpis = result["kpis"]
    if kpis["highest_score"] == kpis["best_honest_agent"]:
        assert "honestly" in result["conclusion"]
    else:
        assert "flagged as gamed" in result["conclusion"]


def test_an_edition_runs_only_its_own_products():
    narrow = {**COMMERCIAL, "products": ["risk_studio"]}
    with pytest.raises(PermissionError, match="does not offer 'crisis_planning'"):
        run_product("crisis_planning", narrow)
    client = TestClient(create_edition_service(narrow, SQLiteStore(), None, POLICY))
    assert [p["product"] for p in client.get("/api/products").json()] == ["risk_studio"]
    assert client.post("/api/products/crisis_planning").status_code == 403
    assert client.post("/api/products/teleport").status_code == 404


def test_a_product_runs_over_the_service_redacted():
    client = service(COMMERCIAL)
    returned = client.post("/api/products/equipment_screening").json()
    assert returned["product"] == "equipment_screening"
    assert leaks(returned, COMMERCIAL) == []


def test_the_report_reads_every_product_and_names_no_internal_system():
    text = product_report([product(p) for p in sorted(catalogue())], COMMERCIAL)
    assert text.startswith("# SKYVAULT Studio — products")
    for entry in catalogue().values():
        assert f"## {entry['title']}" in text
    assert leaks(text, COMMERCIAL) == []
    assert "at least half the runs" in text


def test_the_internal_edition_shows_the_same_product_unredacted():
    internal = run_product("equipment_screening", INTERNAL)
    assert internal["kpis"] == product("equipment_screening")["kpis"]


# ── acceptance 3: what a commercial scenario teaches flows back ──────────────


def customer_city() -> dict:
    """A customer's own variant: the blackout city with a sturdier south substation."""
    scenario = load_scenario(
        ROOT / "data" / "scenarios" / "city_blackout_001" / "v0.1.json"
    )
    scenario["scenario_id"] = "customer_city_001"
    south = next(e for e in scenario["entities"] if e["entity_id"] == "sub_south")
    south["capabilities"]["capacity"] = float(south["capabilities"]["capacity"]) * 2
    return scenario


def test_a_customer_scenario_comes_back_to_the_core_with_its_provenance():
    contribution = contribute(customer_city(), COMMERCIAL, "crisis_planning")
    assert contribution["contribution_id"].startswith("contribution_")
    assert contribution["source_edition"] == "commercial"
    assert leaks(contribution, COMMERCIAL) == []
    scenario = import_contribution(contribution, COMMERCIAL)
    (source,) = [
        s
        for s in scenario["data_provenance"]["sources"]
        if s["source_id"] == "commercial:crisis_planning"
    ]
    assert source["modified_by"] == "commercial edition"
    package = SkyVaultTacticalReferenceEngine(copy.deepcopy(scenario)).run()
    assert (
        package["reproducibility"]["output_hash"]
        == contribution["result"]["output_hash"]
    )


def test_the_core_explores_the_contributed_scenario_and_learns_from_its_runs():
    scenario = import_contribution(
        contribute(customer_city(), COMMERCIAL, "crisis_planning"), COMMERCIAL
    )
    config = copy.deepcopy(scenario["failure_exploration"])
    config["run_policy"]["repeat_count"] = 2
    config["failure_variables"] = ["supply_delay"]
    failure_map = build_failure_map(
        explore_failures(scenario, default_evaluation_profile(scenario), config)
    )
    assert failure_map["variables"][0]["variable"] == "supply_delay"
    package = SkyVaultTacticalReferenceEngine(copy.deepcopy(scenario)).run()
    labels = run_labels(package, scenario)
    buckets = split_runs([(package, scenario)])
    # every transition of the run lands in exactly one training bucket
    filled = [name for name, rows in buckets.items() if rows]
    assert len(filled) == 1
    assert len(buckets[filled[0]]) == len(build_transitions(package, scenario)) > 0
    assert "success_type" in labels


def test_aliases_written_by_a_customer_are_restored_to_internal_names():
    scenario = load_scenario(
        ROOT / "data" / "scenarios" / "airspace_defence_001" / "v0.1.json"
    )
    scenario["runtime"]["policy"] = {"name": "hades_rules", "params": {"salvo": 2}}
    contribution = contribute(scenario, COMMERCIAL, "risk_studio")
    assert contribution["scenario"]["runtime"]["policy"]["name"] == (
        "air_defence_operator_rules"
    )
    restored = import_contribution(contribution, COMMERCIAL)
    assert restored["runtime"]["policy"]["name"] == "hades_rules"
    SkyVaultTacticalReferenceEngine(copy.deepcopy(restored)).run()


def test_an_internal_contribution_needs_no_restoring():
    contribution = contribute(customer_city(), INTERNAL, "crisis_planning")
    assert contribution["source_edition"] == "internal"
    assert (
        import_contribution(contribution, INTERNAL)["scenario_id"]
        == "customer_city_001"
    )


# ── the script ───────────────────────────────────────────────────────────────


def test_run_products_writes_every_product_and_the_report(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_products.py"),
            "--output",
            str(tmp_path),
            "--repeats",
            "1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Risk Simulation Studio" in done.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [f"{p}.json" for p in catalogue()] + ["products.md"]
    )
    for path in tmp_path.glob("*.json"):
        assert leaks(json.loads(path.read_text()), COMMERCIAL) == [], path


def test_serve_world_serves_the_edition_it_is_given(monkeypatch, tmp_path):
    import importlib.util

    import uvicorn

    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: served.update(app=app))
    spec = importlib.util.spec_from_file_location(
        "serve_world", ROOT / "scripts" / "serve_world.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = f"sqlite:///{tmp_path / 'service.sqlite'}"
    module.main(["--edition", "commercial", "--store", store])
    commercial = TestClient(served["app"])
    assert commercial.get("/api/edition").json()["edition_id"] == "commercial"
    assert "/scenario/submit" not in {r.path for r in served["app"].routes}
    module.main(["--store", store])
    assert "/scenario/submit" in {r.path for r in served["app"].routes}


def test_a_page_that_is_not_json_passes_the_redaction_untouched():
    page = service(COMMERCIAL).get("/api/docs")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]


def test_a_product_passes_through_its_edition_s_redaction():
    renamed = {**COMMERCIAL, "redact": {"Red Alpha": "Team One"}}
    briefing = run_product("training_aar", renamed)["outputs"]["briefing"]
    assert "Team One Rifleman 1" in briefing and "Red Alpha" not in briefing


def test_exactly_half_the_runs_restoring_order_still_counts_as_holding():
    kpis = product("urban_resilience")["kpis"]
    assert kpis["order_restored_rate_by_delay"]["2.0"] == 0.5  # 1 of 2 runs
    assert kpis["longest_delay_order_holds"] == "2.0"
