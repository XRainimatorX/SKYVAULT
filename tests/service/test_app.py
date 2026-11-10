"""The UI routes on the world service: a run's views, briefing and replay (Phase 21)."""

import ast
import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


import json

from skyvault.report import build_briefing, render_pdf
from skyvault.service import mount_ui
from skyvault.views import (
    causal_view,
    comparison_view,
    failure_view,
    load_workspace,
    map_view,
    overview_view,
    package_view,
    timeline_view,
)
from skyvault.worldservice.api import create_world_service, in_process_queue
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore, now
from skyvault.worldservice.views import runs, workspace_from_store

REFERENCE_RUN = "tactical_reference_001/v0.1"


def record(store, request, result=None, state="completed"):
    """A finished job with its result, as the worker would have left it."""
    job = store.create_job(
        {
            "request": {"source_system": "user", **request},
            "priority": "normal",
            "lifecycle_state": state,
            "world_instance": None,
            "governance": None,
            "estimated_cost": None,
            "summary": {},
            "error": None,
            "created_at": now(),
            "updated_at": now(),
        }
    )
    if result is not None:
        store.save_result(job["job_id"], result)
    return job["job_id"]


def service(store, ui=None):
    app = create_world_service(
        store, in_process_queue(store, load_governance()), load_governance()
    )
    mount_ui(app, ui)
    return TestClient(app)


def read(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seeded(reference_workspace):
    """The reference run, its failure exploration and its batch, in a store."""
    store = SQLiteStore()
    record(
        store,
        {"kind": "failure_exploration", "scenario": REFERENCE_RUN},
        read(reference_workspace, "failure_map.json"),
    )
    record(
        store,
        {"kind": "batch", "batch": "tactical_reference_001"},
        {
            k: read(reference_workspace, f"{k}.json")
            for k in ("batch_result", "branch_comparison", "conflict_package")
        },
    )
    run = record(
        store,
        {"kind": "scenario_run", "scenario": REFERENCE_RUN},
        read(reference_workspace, "result_package.json"),
    )
    return store, run


@pytest.fixture(scope="module")
def client(seeded):
    return service(seeded[0])


@pytest.fixture(scope="module")
def run(seeded):
    return seeded[1]


@pytest.fixture(scope="module")
def workspace(seeded):
    return workspace_from_store(*seeded)


def test_a_run_s_workspace_is_what_the_three_scripts_used_to_write(
    workspace, reference_workspace
):
    folder = load_workspace(reference_workspace)
    for key in (
        "result_package",
        "failure_map",
        "survival_conditions",
        "recommended_modifications",
        "batch_result",
        "branch_comparison",
        "conflict_package",
        "comparative_report",
    ):
        assert workspace[key] == folder[key], key


# ── the runs and the screens ─────────────────────────────────────────────────


def test_the_runs_are_listed_newest_first_with_what_they_came_to(client, seeded):
    store, run = seeded
    listed = client.get("/api/runs").json()

    assert listed == runs(store)
    assert [r["run"] for r in listed] == [run]
    assert listed[0]["scenario_id"] == "tactical_reference_001"
    assert listed[0]["result"] == "RED_survived" and listed[0]["events"] == 97


@pytest.mark.parametrize(
    ("screen", "view", "needs"),
    [
        ("overview", overview_view, "package"),
        ("timeline", timeline_view, "package"),
        ("map", map_view, "package"),
        ("causal", causal_view, "package"),
        ("package", package_view, "package"),
        ("failure", failure_view, "workspace"),
        ("comparison", comparison_view, "workspace"),
    ],
)
def test_each_endpoint_is_its_view(client, run, workspace, screen, view, needs):
    expected = view(workspace["result_package"] if needs == "package" else workspace)
    for name in (run, "latest"):
        response = client.get(f"/api/runs/{name}/{screen}")
        assert response.status_code == 200
        assert response.json() == expected


def test_a_run_that_is_not_there_is_a_404_that_says_why(seeded):
    store = SQLiteStore()
    empty = service(store)
    assert "No run yet" in empty.get("/api/runs/latest/overview").json()["detail"]
    batch = record(store, {"kind": "batch", "batch": "military_doctrine"}, {})
    lost = record(
        store,
        {"kind": "scenario_run", "scenario": "military_squad_001/v0.1"},
        state="failed",
    )
    checks = {
        "job_999999": "no run job_999999",
        batch: f"{batch} is a batch job, not a run",
        lost: f"{lost} kept no result package (failed)",
    }
    for name, why in checks.items():
        response = empty.get(f"/api/runs/{name}/overview")
        assert (response.status_code, response.json()["detail"]) == (404, why)


@pytest.mark.parametrize(
    ("screen", "command"),
    [("failure", "skyvault explore"), ("comparison", "skyvault batch")],
)
def test_a_missing_exploration_or_batch_is_a_404_that_says_how_to_make_it(
    reference_workspace, screen, command
):
    store = SQLiteStore()
    run = record(
        store,
        {"kind": "scenario_run", "scenario": REFERENCE_RUN},
        read(reference_workspace, "result_package.json"),
    )
    response = service(store).get(f"/api/runs/{run}/{screen}")

    assert response.status_code == 404
    assert command in response.json()["detail"]
    assert "tactical_reference_001" in response.json()["detail"]


def test_a_new_exploration_shows_up_without_a_restart(reference_workspace):
    store = SQLiteStore()
    run = record(
        store,
        {"kind": "scenario_run", "scenario": REFERENCE_RUN},
        read(reference_workspace, "result_package.json"),
    )
    live = service(store)
    assert live.get(f"/api/runs/{run}/failure").status_code == 404
    # another scenario's exploration, or one that has not finished, is not this run's
    record(
        store,
        {"kind": "failure_exploration", "scenario": "military_urban_001/v0.2"},
        {"x": 1},
    )
    record(
        store,
        {"kind": "failure_exploration", "scenario": REFERENCE_RUN},
        state="running",
    )
    assert live.get(f"/api/runs/{run}/failure").status_code == 404

    record(
        store,
        {"kind": "failure_exploration", "scenario": REFERENCE_RUN},
        read(reference_workspace, "failure_map.json"),
    )

    assert live.get(f"/api/runs/{run}/failure").json()["crushing_variable"] == (
        "communication_failure"
    )


def test_only_a_finished_exploration_of_the_run_s_own_scenario_counts(
    reference_workspace,
):
    store = SQLiteStore()
    failure_map = read(reference_workspace, "failure_map.json")
    run = record(
        store,
        {"kind": "scenario_run", "scenario": REFERENCE_RUN},
        read(reference_workspace, "result_package.json"),
    )
    live = service(store)
    # a whole failure map, but of another scenario, or kept by a failed job
    record(
        store,
        {"kind": "failure_exploration", "scenario": "military_urban_001/v0.2"},
        failure_map,
    )
    record(
        store,
        {"kind": "failure_exploration", "scenario": REFERENCE_RUN},
        failure_map,
        state="failed",
    )

    assert live.get(f"/api/runs/{run}/failure").status_code == 404


def test_a_broken_result_is_an_error_not_a_missing_run(reference_workspace):
    store = SQLiteStore()
    run = record(
        store,
        {"kind": "scenario_run", "scenario": REFERENCE_RUN},
        read(reference_workspace, "result_package.json"),
    )
    record(
        store, {"kind": "failure_exploration", "scenario": REFERENCE_RUN}, {"broken": 1}
    )
    client = TestClient(service(store).app, raise_server_exceptions=False)

    assert client.get(f"/api/runs/{run}/failure").status_code == 500


# ── the briefing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "media_type", "filename", "magic"),
    [
        ("report.md", "text/markdown", "briefing.md", b"# SKYVAULT briefing"),
        ("report.pdf", "application/pdf", "briefing.pdf", b"%PDF"),
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "briefing.docx",
            b"PK",
        ),
    ],
)
def test_the_briefing_downloads_in_three_formats(
    client, run, path, media_type, filename, magic
):
    response = client.get(f"/api/runs/{run}/{path}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{filename}"'
    )
    assert response.content.startswith(magic)


def test_the_downloaded_briefing_is_the_rendered_one(client, run, workspace):
    assert client.get(f"/api/runs/{run}/report.pdf").content == render_pdf(
        build_briefing(workspace)
    )
    docx = zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/runs/{run}/report.docx").content)
    )
    assert "word/document.xml" in docx.namelist()


# ── the static UI ────────────────────────────────────────────────────────────


def test_the_ui_build_is_served_at_the_root_after_every_route(tmp_path):
    ui = tmp_path / "out"
    (ui / "timeline").mkdir(parents=True)
    (ui / "index.html").write_text("<p>overview</p>", encoding="utf-8")
    (ui / "timeline" / "index.html").write_text("<p>timeline</p>", encoding="utf-8")
    served = service(SQLiteStore(), ui)

    assert served.get("/").text == "<p>overview</p>"
    assert served.get("/timeline/").text == "<p>timeline</p>"
    assert served.get("/api/health").json()["status"] == "ok"
    assert served.get("/api/runs").json() == []
    assert served.get("/api/boundary").status_code == 200


def test_without_a_build_only_the_api_is_served(tmp_path):
    served = service(SQLiteStore(), tmp_path / "missing")

    assert served.get("/").status_code == 404
    assert served.get("/api/health").status_code == 200


# ── the replay WebSocket ─────────────────────────────────────────────────────


def ticks_of(messages):
    return [m["frame"]["tick"] for m in messages if m["type"] == "frame"]


def test_the_replay_announces_the_ticks_and_seeks_one(client, run, workspace):
    expected = map_view(workspace["result_package"])["frames"][6]
    with client.websocket_connect(f"/ws/replay?run={run}") as socket:
        assert socket.receive_json() == {"type": "ready", "first": 0, "last": 10}
        socket.send_json({"type": "seek", "tick": 6})

        assert socket.receive_json() == {"type": "frame", "frame": expected}


def test_play_streams_every_tick_in_order_to_the_end(client, run):
    with client.websocket_connect(f"/ws/replay?run={run}") as socket:
        socket.receive_json()
        socket.send_json({"type": "play", "from": 7, "interval_ms": 0})
        messages = [socket.receive_json() for _ in range(5)]

    assert ticks_of(messages) == [7, 8, 9, 10]
    assert messages[-1] == {"type": "end", "tick": 10}


def test_pause_stops_the_stream_where_it_is(client, run):
    with client.websocket_connect(f"/ws/replay?run={run}") as socket:
        socket.receive_json()
        socket.send_json({"type": "play", "from": 2, "interval_ms": 10_000})
        first = socket.receive_json()
        socket.send_json({"type": "pause"})

        assert first["frame"]["tick"] == 2
        assert socket.receive_json() == {"type": "paused", "tick": 2}
        # still listening after the pause
        socket.send_json({"type": "seek", "tick": 3})
        assert socket.receive_json()["frame"]["tick"] == 3


def test_a_seek_while_playing_takes_over(client, run):
    with client.websocket_connect(f"/ws/replay?run={run}") as socket:
        socket.receive_json()
        socket.send_json({"type": "play", "from": 0, "interval_ms": 10_000})
        socket.receive_json()
        socket.send_json({"type": "seek", "tick": 9})

        assert socket.receive_json()["frame"]["tick"] == 9


@pytest.mark.parametrize(
    ("message", "error"),
    [
        ({"type": "seek", "tick": 11}, "no tick 11 in this run"),
        ({"type": "play", "from": -1}, "no tick -1 in this run"),
        ({"type": "rewind"}, "unknown message type 'rewind'"),
    ],
)
def test_a_bad_request_gets_an_error_and_the_socket_stays_open(
    client, run, message, error
):
    with client.websocket_connect(f"/ws/replay?run={run}") as socket:
        socket.receive_json()
        socket.send_json(message)
        assert socket.receive_json() == {"type": "error", "message": error}

        socket.send_json({"type": "pause"})
        assert socket.receive_json() == {"type": "paused", "tick": None}


def test_the_replay_of_no_run_says_so_and_closes(client):
    with client.websocket_connect("/ws/replay?run=job_999999") as socket:
        assert socket.receive_json() == {
            "type": "error",
            "message": "no run job_999999",
        }


def test_the_replay_without_a_run_plays_the_latest(client, workspace):
    with client.websocket_connect("/ws/replay") as socket:
        assert socket.receive_json() == {"type": "ready", "first": 0, "last": 10}


def test_the_ui_routes_never_reach_the_simulation():
    for path in (SRC_PATH / "skyvault" / "service").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert node.module in ("report", "views", "app"), (path, node.module)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("skyvault")
