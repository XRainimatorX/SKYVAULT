"""The UI backend: views over HTTP, the briefing as downloads, replay over WebSocket."""

import ast
import io
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.report import build_briefing, render_pdf
from skyvault.service import create_app
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


@pytest.fixture(scope="module")
def client(reference_workspace):
    return TestClient(create_app(reference_workspace))


@pytest.fixture(scope="module")
def workspace(reference_workspace):
    return load_workspace(reference_workspace)


def test_a_folder_without_a_result_package_is_refused_at_once(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path)


# ── the screens ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "view", "needs"),
    [
        ("/api/overview", overview_view, "package"),
        ("/api/timeline", timeline_view, "package"),
        ("/api/map", map_view, "package"),
        ("/api/causal", causal_view, "package"),
        ("/api/package", package_view, "package"),
        ("/api/failure", failure_view, "workspace"),
        ("/api/comparison", comparison_view, "workspace"),
    ],
)
def test_each_endpoint_is_its_view(client, workspace, path, view, needs):
    response = client.get(path)

    expected = view(workspace["result_package"] if needs == "package" else workspace)
    assert response.status_code == 200
    assert response.json() == expected


def test_health_says_what_the_workspace_holds(client, run_only_workspace):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "scenario_id": "tactical_reference_001",
        "has_failure_exploration": True,
        "has_batch": True,
    }
    only = TestClient(create_app(run_only_workspace)).get("/api/health").json()
    assert (only["has_failure_exploration"], only["has_batch"]) == (False, False)


@pytest.mark.parametrize(
    ("path", "script"),
    [("/api/failure", "explore_failures.py"), ("/api/comparison", "run_batch.py")],
)
def test_a_missing_optional_output_is_a_404_that_says_how_to_make_it(
    run_only_workspace, path, script
):
    response = TestClient(create_app(run_only_workspace)).get(path)

    assert response.status_code == 404
    assert script in response.json()["detail"]


def test_new_outputs_show_up_without_a_restart(
    run_only_workspace, reference_workspace, tmp_path
):
    folder = tmp_path / "live"
    shutil.copytree(run_only_workspace, folder)
    live = TestClient(create_app(folder))
    assert live.get("/api/failure").status_code == 404

    shutil.copy(reference_workspace / "failure_map.json", folder)

    assert live.get("/api/failure").json()["crushing_variable"] == (
        "communication_failure"
    )


# ── the briefing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "media_type", "filename", "magic"),
    [
        ("/api/report.md", "text/markdown", "briefing.md", b"# SKYVAULT briefing"),
        ("/api/report.pdf", "application/pdf", "briefing.pdf", b"%PDF"),
        (
            "/api/report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "briefing.docx",
            b"PK",
        ),
    ],
)
def test_the_briefing_downloads_in_three_formats(
    client, path, media_type, filename, magic
):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{filename}"'
    )
    assert response.content.startswith(magic)


def test_the_downloaded_briefing_is_the_rendered_one(client, workspace):
    assert client.get("/api/report.pdf").content == render_pdf(
        build_briefing(workspace)
    )
    docx = zipfile.ZipFile(io.BytesIO(client.get("/api/report.docx").content))
    assert "word/document.xml" in docx.namelist()


# ── the static UI ────────────────────────────────────────────────────────────


def test_the_ui_build_is_served_at_the_root(run_only_workspace, tmp_path):
    ui = tmp_path / "out"
    (ui / "timeline").mkdir(parents=True)
    (ui / "index.html").write_text("<p>overview</p>", encoding="utf-8")
    (ui / "timeline" / "index.html").write_text("<p>timeline</p>", encoding="utf-8")
    served = TestClient(create_app(run_only_workspace, ui))

    assert served.get("/").text == "<p>overview</p>"
    assert served.get("/timeline/").text == "<p>timeline</p>"
    assert served.get("/api/health").json()["status"] == "ok"


def test_without_a_build_only_the_api_is_served(run_only_workspace, tmp_path):
    served = TestClient(create_app(run_only_workspace, tmp_path / "missing"))

    assert served.get("/").status_code == 404
    assert served.get("/api/health").status_code == 200


# ── the replay WebSocket ─────────────────────────────────────────────────────


def ticks_of(messages):
    return [m["frame"]["tick"] for m in messages if m["type"] == "frame"]


def test_the_replay_announces_the_ticks_and_seeks_one(client, workspace):
    expected = map_view(workspace["result_package"])["frames"][6]
    with client.websocket_connect("/ws/replay") as socket:
        assert socket.receive_json() == {"type": "ready", "first": 0, "last": 10}
        socket.send_json({"type": "seek", "tick": 6})

        assert socket.receive_json() == {"type": "frame", "frame": expected}


def test_play_streams_every_tick_in_order_to_the_end(client):
    with client.websocket_connect("/ws/replay") as socket:
        socket.receive_json()
        socket.send_json({"type": "play", "from": 7, "interval_ms": 0})
        messages = [socket.receive_json() for _ in range(5)]

    assert ticks_of(messages) == [7, 8, 9, 10]
    assert messages[-1] == {"type": "end", "tick": 10}


def test_pause_stops_the_stream_where_it_is(client):
    with client.websocket_connect("/ws/replay") as socket:
        socket.receive_json()
        socket.send_json({"type": "play", "from": 2, "interval_ms": 10_000})
        first = socket.receive_json()
        socket.send_json({"type": "pause"})

        assert first["frame"]["tick"] == 2
        assert socket.receive_json() == {"type": "paused", "tick": 2}
        # still listening after the pause
        socket.send_json({"type": "seek", "tick": 3})
        assert socket.receive_json()["frame"]["tick"] == 3


def test_a_seek_while_playing_takes_over(client):
    with client.websocket_connect("/ws/replay") as socket:
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
def test_a_bad_request_gets_an_error_and_the_socket_stays_open(client, message, error):
    with client.websocket_connect("/ws/replay") as socket:
        socket.receive_json()
        socket.send_json(message)
        assert socket.receive_json() == {"type": "error", "message": error}

        socket.send_json({"type": "pause"})
        assert socket.receive_json() == {"type": "paused", "tick": None}


def test_the_service_never_reaches_the_simulation():
    for path in (SRC_PATH / "skyvault" / "service").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert node.module in ("report", "views", "app"), (path, node.module)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("skyvault")
