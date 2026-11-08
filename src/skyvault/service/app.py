"""The UI backend: the workspace's screens over HTTP, the replay over a WebSocket.

Important:
Reading only. The server never simulates: every response is a view or the
briefing, built from the workspace folder on each request, so regenerating
the outputs is reflected without a restart. A workspace with no result
package is refused when the app is created. The Next.js build, when given,
is served at / from the same origin as the API.
"""

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from ..report import build_briefing, render_docx, render_markdown, render_pdf
from ..views import (
    causal_view,
    comparison_view,
    failure_view,
    load_workspace,
    map_view,
    overview_view,
    package_view,
    timeline_view,
)

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_INTERVAL_MS = 500


def create_app(workspace_dir: Path, ui_dir: Path | None = None) -> FastAPI:
    """
    The FastAPI app for one workspace folder.

    Raises FileNotFoundError at once when the folder has no result package.
    ui_dir, when it holds an index.html, is served at /.
    """
    workspace_dir = Path(workspace_dir)
    load_workspace(workspace_dir)
    app = FastAPI(title="SKYVAULT", docs_url="/api/docs", openapi_url="/api/openapi")

    def workspace() -> dict[str, Any]:
        return load_workspace(workspace_dir)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        loaded = workspace()
        return {
            "status": "ok",
            "scenario_id": loaded["result_package"]["scenario_id"],
            "has_failure_exploration": loaded["failure_map"] is not None,
            "has_batch": loaded["batch_result"] is not None,
        }

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        return overview_view(workspace()["result_package"])

    @app.get("/api/timeline")
    def timeline() -> dict[str, Any]:
        return timeline_view(workspace()["result_package"])

    @app.get("/api/map")
    def world_map() -> dict[str, Any]:
        return map_view(workspace()["result_package"])

    @app.get("/api/causal")
    def causal() -> dict[str, Any]:
        return causal_view(workspace()["result_package"])

    @app.get("/api/package")
    def package() -> dict[str, Any]:
        return package_view(workspace()["result_package"])

    @app.get("/api/failure")
    def failure() -> dict[str, Any]:
        view = failure_view(workspace())
        if view is None:
            raise HTTPException(
                404,
                "No failure exploration in this workspace: "
                "run scripts/explore_failures.py",
            )
        return view

    @app.get("/api/comparison")
    def comparison() -> dict[str, Any]:
        view = comparison_view(workspace())
        if view is None:
            raise HTTPException(
                404, "No batch in this workspace: run scripts/run_batch.py"
            )
        return view

    @app.get("/api/report.md")
    def report_markdown() -> Response:
        return _download(
            render_markdown(build_briefing(workspace())).encode("utf-8"),
            "text/markdown; charset=utf-8",
            "briefing.md",
        )

    @app.get("/api/report.pdf")
    def report_pdf() -> Response:
        return _download(
            render_pdf(build_briefing(workspace())), "application/pdf", "briefing.pdf"
        )

    @app.get("/api/report.docx")
    def report_docx() -> Response:
        return _download(
            render_docx(build_briefing(workspace())), DOCX_TYPE, "briefing.docx"
        )

    @app.websocket("/ws/replay")
    async def replay(socket: WebSocket) -> None:
        await socket.accept()
        frames = map_view(workspace()["result_package"])["frames"]
        await _replay(socket, frames)

    if ui_dir is not None and (Path(ui_dir) / "index.html").is_file():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _replay(socket: WebSocket, frames: list[dict[str, Any]]) -> None:
    """
    The replay protocol: frames on request, one tick at a time.

    Important:
    On connect the server sends {type: ready, first, last}. The client sends
    {type: seek, tick} for one frame, {type: play, from, interval_ms} to
    stream frames in tick order until the last ({type: end}) or a
    {type: pause} ({type: paused, tick}). A tick outside the run gets
    {type: error}. Messages are read by a separate task, so a pause arrives
    while frames are being streamed.
    """
    by_tick = {frame["tick"]: frame for frame in frames}
    ticks = sorted(by_tick)
    inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def read() -> None:
        try:
            while True:
                await inbox.put(await socket.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            await inbox.put(None)

    reader = asyncio.create_task(read())
    try:
        await socket.send_json({"type": "ready", "first": ticks[0], "last": ticks[-1]})
        message = await inbox.get()
        while message is not None:
            message = await _handle(socket, message, by_tick, ticks, inbox)
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader


async def _handle(
    socket: WebSocket,
    message: dict[str, Any],
    by_tick: dict[int, dict[str, Any]],
    ticks: list[int],
    inbox: "asyncio.Queue[dict[str, Any] | None]",
) -> dict[str, Any] | None:
    """Answer one message; return the next one to handle (None = closed)."""
    kind = message.get("type")
    if kind == "seek":
        tick = message.get("tick")
        if tick not in by_tick:
            await socket.send_json(
                {"type": "error", "message": f"no tick {tick} in this run"}
            )
        else:
            await socket.send_json({"type": "frame", "frame": by_tick[tick]})
    elif kind == "play":
        start = message.get("from", ticks[0])
        if start not in by_tick:
            await socket.send_json(
                {"type": "error", "message": f"no tick {start} in this run"}
            )
            return await inbox.get()
        interval = message.get("interval_ms", DEFAULT_INTERVAL_MS) / 1000
        for tick in [t for t in ticks if t >= start]:
            await socket.send_json({"type": "frame", "frame": by_tick[tick]})
            if tick == ticks[-1]:
                await socket.send_json({"type": "end", "tick": tick})
                break
            try:
                interrupt = await asyncio.wait_for(inbox.get(), timeout=interval)
            except TimeoutError:
                continue
            if interrupt is None:
                return None
            if interrupt.get("type") == "pause":
                await socket.send_json({"type": "paused", "tick": tick})
                break
            return interrupt
    elif kind == "pause":
        await socket.send_json({"type": "paused", "tick": None})
    else:
        await socket.send_json(
            {"type": "error", "message": f"unknown message type {kind!r}"}
        )
    return await inbox.get()
