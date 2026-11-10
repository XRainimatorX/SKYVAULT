"""Phase 21: skyvault, the one command SKYVAULT is started and used with."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skyvault import cli
from skyvault.editions.manifest import load_edition
from skyvault.editions.service import create_edition_service
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = "military_urban_001/v0.2"


@pytest.fixture
def service():
    """The internal edition's service in this process, as serve builds it."""
    app = create_edition_service(
        load_edition("internal"), SQLiteStore(), None, load_governance()
    )
    with TestClient(app) as client:
        yield client


def skyvault(service, *argv):
    return cli.main(list(argv), http=service)


def test_a_run_is_submitted_waited_for_and_shown(service, capsys):
    assert skyvault(service, "run", BASELINE) == 0
    out = capsys.readouterr().out

    assert "job_000001  scenario_run  queued" in out
    assert "job_000001  completed" in out
    assert "result: no_winner_duration_limit" in out and "events: 528" in out


def test_without_waiting_the_job_is_only_queued(service, capsys):
    assert skyvault(service, "run", BASELINE, "--seed", "43", "--no-wait") == 0
    out = capsys.readouterr().out
    assert out.strip() == "job_000001  scenario_run  queued"
    job = service.get("/api/jobs/job_000001").json()
    assert job["request"]["runtime"] == {"random_seed": 43}


def test_runs_briefing_result_and_status_read_the_service(service, capsys, tmp_path):
    skyvault(service, "runs")
    assert "No run yet" in capsys.readouterr().out
    skyvault(service, "run", "military_squad_001/v0.1", "--profile", "tactical")
    capsys.readouterr()

    assert skyvault(service, "runs") == 0
    assert "job_000001  military_squad_001 v0.1" in capsys.readouterr().out
    assert skyvault(service, "briefing") == 0
    assert capsys.readouterr().out.startswith(
        "# SKYVAULT briefing — military_squad_001 v0.1"
    )
    out = tmp_path / "b.docx"
    assert (
        skyvault(
            service, "briefing", "job_000001", "--format", "docx", "--out", str(out)
        )
        == 0
    )
    assert out.read_bytes()[:2] == b"PK"
    result = tmp_path / "result.json"
    assert skyvault(service, "result", "job_000001", "--out", str(result)) == 0
    assert json.loads(result.read_text())["scenario_id"] == "military_squad_001"
    capsys.readouterr()
    assert skyvault(service, "result", "job_000001") == 0
    assert json.loads(capsys.readouterr().out)["scenario_version"] == "v0.1"
    assert skyvault(service, "status") == 0
    assert "completed: 1" in capsys.readouterr().out


def test_replay_cancel_and_worlds(service, capsys):
    skyvault(service, "run", "military_squad_001/v0.1")
    assert skyvault(service, "replay", "job_000001") == 0
    assert "reproduced: True" in capsys.readouterr().out

    assert skyvault(service, "world", "create", "military_squad_001/v0.1") == 0
    created = json.loads(capsys.readouterr().out)
    world = created["world_id"]
    assert skyvault(service, "world", "advance", world, "--ticks", "3") == 0
    assert json.loads(capsys.readouterr().out)["tick"] == 3
    assert skyvault(service, "cancel", world) == 0
    assert f"{world}  completed" in capsys.readouterr().out
    assert skyvault(service, "world", "finish", world) == 0
    assert json.loads(capsys.readouterr().out)["lifecycle_state"] == "completed"


def test_explore_and_batch_feed_the_run_s_screens(service, capsys):
    skyvault(service, "run", "military_squad_001/v0.1")
    assert skyvault(service, "batch", "military_doctrine", "--repeat", "2") == 0
    assert "variants: 3" in capsys.readouterr().out
    comparison = service.get("/api/runs/latest/comparison")
    assert comparison.status_code == 404  # the doctrine batch is the urban plan's

    skyvault(service, "run", BASELINE, "--no-wait")
    skyvault(service, "explore", BASELINE, "--repeat", "1")
    assert "failure_exploration  queued" in capsys.readouterr().out
    assert service.get("/api/runs/latest/failure").status_code == 200
    assert service.get("/api/runs/latest/comparison").json()["batch_id"] == (
        "military_urban_001_doctrine"
    )


def test_products_are_listed_and_run(service, capsys):
    assert skyvault(service, "products") == 0
    assert "crisis_planning" in capsys.readouterr().out
    assert skyvault(service, "products", "equipment_screening") == 0
    assert "Equipment Concept Screening" in capsys.readouterr().out


def test_a_refusal_or_no_service_is_a_reason_and_exit_1(service, capsys):
    assert skyvault(service, "run", "no_such_001/v0.1") == 1
    err = capsys.readouterr().err
    assert err.startswith("skyvault: POST /api/jobs → 404 not_found")

    assert cli.main(["status", "--url", "http://127.0.0.1:9"]) == 1
    assert "start one with: skyvault serve" in capsys.readouterr().err


def test_a_failed_job_is_a_failed_command(service, capsys, monkeypatch):
    from skyvault.worldservice import jobs

    def broken(*args, **kwargs):
        raise RuntimeError("the engine broke")

    monkeypatch.setattr(jobs, "run_scenario", broken)
    assert skyvault(service, "run", BASELINE) == 1
    assert (
        "job_000001 failed: RuntimeError: the engine broke" in capsys.readouterr().err
    )


def test_virtual_test_runs_here(capsys, tmp_path):
    assert cli.main(["virtual-test", "pax_test_001"]) == 0
    assert "PAX_TEST_001" in capsys.readouterr().out
    profile = tmp_path / "mine.json"
    source = REPO_ROOT / "data" / "virtualtest" / "profiles" / "exo_test_001.json"
    profile.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "found.json"
    assert cli.main(["virtual-test", str(profile), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["final_judgement"]["status"] == "continue"


def test_acceptance_runs_here_and_writes_its_report(capsys, tmp_path):
    assert cli.main(["acceptance", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "acceptance  15/15" in out and out.strip().endswith("ACCEPTED")
    assert (
        (tmp_path / "acceptance.md")
        .read_text()
        .startswith("# SKYVAULT v2.0 acceptance")
    )


def test_a_failing_acceptance_exits_1(capsys, monkeypatch):
    import skyvault.acceptance.run as run_module

    monkeypatch.setattr(
        run_module, "run_acceptance", lambda: {"counts": {}, "passed": False}
    )
    assert cli.main(["acceptance"]) == 1
    assert "NOT ACCEPTED" in capsys.readouterr().out


def test_serve_builds_the_edition_s_service_with_the_ui(tmp_path):
    ui = tmp_path / "out"
    ui.mkdir()
    (ui / "index.html").write_text("<p>ui</p>", encoding="utf-8")
    args = cli.parser().parse_args(
        [
            "serve",
            "--store",
            f"sqlite:///{tmp_path / 'here' / 'skyvault.sqlite'}",
            "--edition",
            "commercial",
            "--ui",
            str(ui),
        ]
    )
    client = TestClient(cli.build_app(args))

    assert client.get("/").text == "<p>ui</p>"
    assert client.get("/api/edition").json()["edition_id"] == "commercial"
    assert client.get("/api/runs").json() == []
    assert (tmp_path / "here" / "skyvault.sqlite").is_file()


def test_serve_and_worker_hand_their_options_to_the_service(monkeypatch, tmp_path):
    import uvicorn

    from skyvault.worldservice import queues

    served, worked = {}, {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(kw, app=app))

    class FakeQueue:
        def __init__(self, redis, store, governance, policy=None):
            worked.update(redis=redis, store=store, policy=policy)

        def worker(self, burst):
            return argparse.Namespace(work=lambda burst: worked.update(burst=burst))

    monkeypatch.setattr(queues, "RQQueue", FakeQueue)
    store = f"sqlite:///{tmp_path / 's.sqlite'}"
    assert cli.main(["serve", "--store", store, "--port", "8765", "--ui", ""]) == 0
    assert (served["host"], served["port"]) == ("127.0.0.1", 8765)
    assert cli.main(["serve", "--store", store, "--queue", "rq"]) == 0
    assert worked["policy"]["decision_authorities"] == ["NEXUS", "SOVEREIGN"]
    assert cli.main(["worker", "--store", store, "--burst"]) == 0
    assert worked["burst"] is True and worked["store"] == store


def test_the_command_is_installed_and_names_its_version():
    done = subprocess.run(
        [sys.executable, "-m", "skyvault.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    from skyvault import __version__

    assert done.stdout.strip() == f"skyvault {__version__}"
    assert (
        'skyvault = "skyvault.cli:main"' in (REPO_ROOT / "pyproject.toml").read_text()
    )
