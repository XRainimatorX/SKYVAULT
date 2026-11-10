"""The UI's routes: a run's screens over HTTP, its replay over a WebSocket.

Important:
Reading only. The routes never simulate: every response is a view or the
briefing, built on each request from the workspace a run has (its result
package, and the failure exploration and batch of its scenario when they
exist). Where a workspace comes from is the caller's: the world service
reads it from its store (Phase 21; skyvault.worldservice.views). A run
that is not there is a 404. The Next.js build, when given, is served at /
from the same origin — mounted last, after every other route.
"""

import asyncio
import contextlib
from collections.abc import Callable
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
    map_view,
    overview_view,
    package_view,
    timeline_view,
)

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_INTERVAL_MS = 500

Workspaces = Callable[[str], dict[str, Any]]


class NoSuchRun(Exception):
    """A run the caller cannot show: unknown, not a run, or without a result.

    Its own class, not LookupError: a KeyError from a broken result must
    surface as the error it is, not as a 404.
    """


def add_view_routes(app: FastAPI, workspace_for: Workspaces) -> None:
    """
    /api/runs/{run}/<screen> and /ws/replay?run=<run> on app.

    workspace_for(run) returns the run's workspace (keys as load_workspace)
    and raises NoSuchRun when there is no such run; "latest" names the
    newest run.
    """

    def workspace(run: str) -> dict[str, Any]:
        try:
            return workspace_for(run)
        except NoSuchRun as error:
            raise HTTPException(404, str(error)) from None

    @app.get("/api/runs/{run}/overview")
    def overview(run: str) -> dict[str, Any]:
        return overview_view(workspace(run)["result_package"])

    @app.get("/api/runs/{run}/timeline")
    def timeline(run: str) -> dict[str, Any]:
        return timeline_view(workspace(run)["result_package"])

    @app.get("/api/runs/{run}/map")
    def world_map(run: str) -> dict[str, Any]:
        return map_view(workspace(run)["result_package"])

    @app.get("/api/runs/{run}/causal")
    def causal(run: str) -> dict[str, Any]:
        return causal_view(workspace(run)["result_package"])

    @app.get("/api/runs/{run}/package")
    def package(run: str) -> dict[str, Any]:
        return package_view(workspace(run)["result_package"])

    @app.get("/api/runs/{run}/failure")
    def failure(run: str) -> dict[str, Any]:
        loaded = workspace(run)
        view = failure_view(loaded)
        if view is None:
            scenario = loaded["result_package"]["scenario_id"]
            raise HTTPException(
                404,
                f"No failure exploration of {scenario} yet: "
                f"skyvault explore {scenario}/<version>",
            )
        return view

    @app.get("/api/runs/{run}/comparison")
    def comparison(run: str) -> dict[str, Any]:
        loaded = workspace(run)
        view = comparison_view(loaded)
        if view is None:
            scenario = loaded["result_package"]["scenario_id"]
            raise HTTPException(
                404, f"No batch on {scenario} yet: skyvault batch <batch name>"
            )
        return view

    @app.get("/api/runs/{run}/report.md")
    def report_markdown(run: str) -> Response:
        return _download(
            render_markdown(build_briefing(workspace(run))).encode("utf-8"),
            "text/markdown; charset=utf-8",
            "briefing.md",
        )

    @app.get("/api/runs/{run}/report.pdf")
    def report_pdf(run: str) -> Response:
        return _download(
            render_pdf(build_briefing(workspace(run))),
            "application/pdf",
            "briefing.pdf",
        )

    @app.get("/api/runs/{run}/report.docx")
    def report_docx(run: str) -> Response:
        return _download(
            render_docx(build_briefing(workspace(run))), DOCX_TYPE, "briefing.docx"
        )

    @app.websocket("/ws/replay")
    async def replay(socket: WebSocket, run: str = "latest") -> None:
        await socket.accept()
        try:
            frames = map_view(workspace_for(run)["result_package"])["frames"]
        except NoSuchRun as error:
            await socket.send_json({"type": "error", "message": str(error)})
            await socket.close()
            return
        await _replay(socket, frames)


def mount_ui(app: FastAPI, ui_dir: Path | None) -> bool:
    """Serve the UI build at / when ui_dir holds one; call it after every route."""
    if ui_dir is None or not (Path(ui_dir) / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return True


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
            # asyncio.TimeoutError, not TimeoutError: they are one class only
            # from Python 3.11 on, and wait_for raises the asyncio one on 3.10
            except asyncio.TimeoutError:  # noqa: UP041
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
