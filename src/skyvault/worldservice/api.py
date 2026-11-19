"""The world service's HTTP API (Formal Spec section 10, development plan Phase 11).

Important:
Jobs: submit (planned and admitted, then queued), list, look up, download
the result, cancel, replay. Persistent worlds: create, advance, look up,
checkpoints, finish, delete; a world waiting for a decision on a conflict
does not advance (409). The external interface's routes (Phase 12) are
added to the same app. Status: the service's mode and health, the
queue and what runs. The API only plans and queues; workers run jobs. A
refusal says why: 404 for something SKYVAULT does not have, 422 for a
malformed request or one governance refuses, 429 when the queue is full,
409 for a result that is not ready or a job that cannot be cancelled.
"""

import threading
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException

from ..boundary import declaration
from ..contracts import ContractError, validate_world_service_contract
from ..contracts.service import OPERATION_MODES, SERVICE_ACTIONS
from ..interface.api import add_external_routes
from ..service import add_view_routes
from .governance import Rejected
from .jobs import (
    NotFound,
    execute_job,
    full_request,
    new_job,
    plan,
    scenario_for,
)
from .monitoring import add_monitor_routes
from .queues import InProcessQueue, JobQueue
from .store import JobStore
from .views import runs, workspace_from_store
from .worlds import (
    LIVE,
    PersistentWorld,
    WorldAwaiting,
    WorldClosed,
    WorldPaused,
)

# A request body: any JSON object; the job contract checks it
JSONBody = Annotated[dict[str, Any], Body()]
FINISHED = ("completed", "failed", "archived", "replayed", "deleted")
MODE_OF = {
    "failure_exploration": "failure_exploration",
    "batch": "batch",
    "scenario_run": "running",
    "replay": "running",
}


def in_process_queue(store: JobStore, policy: dict[str, Any]) -> InProcessQueue:
    """The default queue: this process's threads, under the policy's limits."""
    return InProcessQueue(
        lambda job_id: execute_job(job_id, store, policy),
        policy["max_parallel_runs"],
        policy["queue_policy"],
    )


def create_world_service(
    store: JobStore,
    queue: JobQueue,
    policy: dict[str, Any],
    external_routes: bool = True,
    gate: Callable[[dict[str, Any]], None] | None = None,
) -> FastAPI:
    """
    The world service app over one store, one queue and one policy.

    external_routes=False leaves the external interface (Phase 12) off;
    gate(request) is asked about every job before it is planned and raises
    PermissionError (403 not_licensed) for one it does not allow (Phase 19:
    an edition's job kinds and domains). The defaults change nothing.
    """
    app = FastAPI(
        title="SKYVAULT world service",
        docs_url="/api/docs",
        openapi_url="/api/openapi",
    )
    worlds: dict[str, PersistentWorld] = {}
    worlds_lock = threading.Lock()
    # Formal Spec 10: a world outlives the process that ran it. Every world
    # still live in the store is rebuilt from its inputs; one that does not
    # rebuild to its last checkpoint is marked failed.
    for job in store.list_jobs():
        if job["request"]["kind"] != "persistent_world":
            continue
        if job["lifecycle_state"] not in LIVE:
            continue
        try:
            worlds[job["job_id"]] = PersistentWorld.restore(job, policy, store)
        except Exception as error:
            store.update_job(
                job["job_id"], lifecycle_state="failed", error=f"restore: {error}"
            )
            store.log(job["job_id"], f"could not be restored: {error}")

    def refuse(error: Exception) -> HTTPException:
        if isinstance(error, PermissionError):
            return HTTPException(403, {"reason": "not_licensed", "detail": str(error)})
        if isinstance(error, Rejected):
            status = 429 if error.reason == "queue_full" else 422
            return HTTPException(
                status, {"reason": error.reason, "detail": error.detail}
            )
        if isinstance(error, NotFound | KeyError):
            return HTTPException(
                404, {"reason": "not_found", "detail": str(error).strip("'\"")}
            )
        return HTTPException(422, {"reason": "invalid_request", "detail": str(error)})

    def job_or_404(job_id: str) -> dict[str, Any]:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise refuse(error) from None

    def admit(request: dict[str, Any], ahead: int = 0) -> dict[str, Any]:
        """
        Record a request the gate and the policy allow. ahead: jobs of the
        same submission admitted before it but not queued yet — they count
        toward max_queue_length too.
        """
        try:
            if gate is not None:
                gate(request)
                if request.get("kind") == "replay":
                    gate(store.get_job(str(request.get("replay")))["request"])
            planned = plan(request, policy, queue.depth() + ahead, store)
            return new_job(store, request, planned, policy)
        except (
            PermissionError,
            Rejected,
            NotFound,
            KeyError,
            ContractError,
            ValueError,
        ) as error:
            raise refuse(error) from None

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/boundary")
    def boundary() -> dict[str, Any]:
        """The Final Authority Boundary (Phase 20): role, may, may_not."""
        return declaration()

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        jobs = store.list_jobs()
        running = [j for j in jobs if j["lifecycle_state"] == "running"]
        with worlds_lock:
            everyone = list(worlds.values())
        live = [w for w in everyone if w.lifecycle in LIVE]
        finished = [j for j in jobs if j["lifecycle_state"] in FINISHED][-10:]
        failed = sum(1 for j in finished if j["lifecycle_state"] == "failed")
        if finished and failed == len(finished) and len(finished) >= 3:
            health = "failed"
        elif finished and failed * 2 >= len(finished):
            health = "degraded"
        else:
            health = "normal"
        modes = [
            MODE_OF[j["request"]["kind"]]
            for j in running
            if j["request"]["kind"] in MODE_OF
        ]
        if live:
            modes.append("persistent")
        order = ["failure_exploration", "batch", "persistent", "running"]
        mode = next((m for m in order if m in modes), "standby")
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job["lifecycle_state"]] = counts.get(job["lifecycle_state"], 0) + 1
        return {
            "service_status": {"mode": mode, "health": health},
            "queue": {"depth": queue.depth(), "running": queue.running()},
            "jobs": dict(sorted(counts.items())),
            "worlds": sorted(w.world_id for w in live),
            "policy_id": policy["policy_id"],
        }

    @app.get("/api/service")
    def service_contract() -> dict[str, Any]:
        """Formal Spec 10.4 world_service_contract: what the service is and does."""
        jobs = store.list_jobs()
        tasks = [j for j in jobs if j["request"]["kind"] != "monitor"]
        last = tasks[-1] if tasks else None
        instances = [j["world_instance"] for j in jobs if j["world_instance"]]
        return validate_world_service_contract(
            {
                "service_status": status()["service_status"],
                "task_intake": {
                    "source_system": last["request"]["source_system"] if last else None,
                    "task_type": last["request"]["kind"] if last else None,
                    "priority": last["priority"] if last else None,
                    "required_result_package": (
                        last["request"].get("required_result_package", True)
                        if last
                        else None
                    ),
                },
                "world_instance": instances[-1] if instances else None,
                "service_actions": list(SERVICE_ACTIONS),
                "operation_modes": list(OPERATION_MODES),
                "routes": {
                    "receive_task": "POST /api/jobs",
                    "create_world_instance": "POST /api/worlds",
                    "run_scenario": "POST /api/jobs {kind: scenario_run}",
                    "pause_world": "POST /api/worlds/{world_id}/pause",
                    "resume_world": "POST /api/worlds/{world_id}/resume",
                    "branch_world": "POST /api/worlds/{world_id}/branch",
                    "terminate_world": "POST /api/worlds/{world_id}/terminate",
                    "archive_world": "POST /api/worlds/{world_id}/archive",
                    "export_result_package": "GET /api/jobs/{job_id}/result",
                },
            }
        )

    @app.post("/api/jobs", status_code=202)
    def submit(request: JSONBody) -> dict[str, Any]:
        if request.get("kind") == "persistent_world":
            raise HTTPException(
                422,
                {
                    "reason": "invalid_request",
                    "detail": "create persistent worlds at /api/worlds",
                },
            )
        job = admit(request)
        queue.submit(job["job_id"], job["priority"])
        explore = _map_required(job)
        if explore is not None:
            linked = admit(explore)
            queue.submit(linked["job_id"], linked["priority"])
            store.update_job(
                job["job_id"], summary_fields={"failure_map_job": linked["job_id"]}
            )
            job = store.get_job(job["job_id"])
        return job

    def _map_required(job: dict[str, Any]) -> dict[str, Any] | None:
        """
        Formal Spec 3.3 output.failure_map_required: a scenario run that asks
        for a failure map brings its failure exploration along, as a job of
        its own (linked from the run's summary).
        """
        request = job["request"]
        if request["kind"] != "scenario_run":
            return None
        scenario = scenario_for(request)
        output = scenario.get("output") or {}
        if not (output.get("failure_map_required") and scenario["failure_exploration"]):
            return None
        return {
            "kind": "failure_exploration",
            "scenario": request["scenario"],
            "source_system": request["source_system"],
        }

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return store.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return {**job_or_404(job_id), "events": store.events(job_id)}

    @app.get("/api/jobs/{job_id}/result")
    def get_result(job_id: str) -> dict[str, Any]:
        job = job_or_404(job_id)
        result = store.get_result(job_id)
        if result is None:
            if job["lifecycle_state"] in FINISHED:
                raise HTTPException(
                    404,
                    {
                        "reason": "no_result",
                        "detail": job["error"] or "this job kept no result",
                    },
                )
            raise HTTPException(
                409,
                {
                    "reason": "not_ready",
                    "detail": f"the job is {job['lifecycle_state']}",
                },
            )
        return result

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        job = job_or_404(job_id)
        if job["lifecycle_state"] in FINISHED:
            raise HTTPException(
                409,
                {
                    "reason": "finished",
                    "detail": f"the job is {job['lifecycle_state']}",
                },
            )
        with worlds_lock:
            world = worlds.get(job_id)
        if world is not None:
            # a persistent world runs on request, not on a worker: close it now
            world.finish()
            store.log(job_id, "cancelled: the world was finished early")
            return store.get_job(job_id)
        if queue.cancel(job_id):
            store.log(job_id, "cancelled while waiting")
            return store.update_job(
                job_id, lifecycle_state="failed", error="cancelled before it ran"
            )
        store.log(job_id, "cancel requested")
        return store.merge_summary(job_id, cancel_requested=True)

    @app.post("/api/jobs/{job_id}/replay", status_code=202)
    def replay(job_id: str) -> dict[str, Any]:
        job_or_404(job_id)
        return submit({"kind": "replay", "replay": job_id, "source_system": "user"})

    @app.post("/api/worlds", status_code=201)
    def create_world(request: JSONBody) -> dict[str, Any]:
        job = admit({**request, "kind": "persistent_world"})
        try:
            world = PersistentWorld(
                job["job_id"], full_request(job["request"]), policy, store
            )
        except Exception as error:
            store.update_job(job["job_id"], lifecycle_state="failed", error=str(error))
            raise refuse(error) from None
        with worlds_lock:
            worlds[world.world_id] = world
        store.update_job(
            world.world_id,
            lifecycle_state="initialized",
            world_instance={
                "world_id": world.world_id,
                "scenario_id": world.scenario_id,
                "lifecycle_state": "initialized",
            },
        )
        return world.state()

    def world_or_404(world_id: str) -> PersistentWorld:
        with worlds_lock:
            world = worlds.get(world_id)
        if world is None:
            raise HTTPException(
                404, {"reason": "not_found", "detail": f"no live world {world_id}"}
            )
        return world

    @app.post("/api/worlds/{world_id}/advance")
    def advance(world_id: str, body: JSONBody) -> dict[str, Any]:
        ticks = body.get("ticks")
        if not isinstance(ticks, int) or ticks < 1:
            raise HTTPException(
                422,
                {
                    "reason": "invalid_request",
                    "detail": "ticks must be a whole number >= 1",
                },
            )
        try:
            return world_or_404(world_id).advance(ticks)
        except WorldClosed as error:
            raise HTTPException(
                409, {"reason": "closed", "detail": str(error)}
            ) from None
        except WorldPaused as error:
            raise HTTPException(
                409, {"reason": "paused", "detail": str(error)}
            ) from None
        except WorldAwaiting as error:
            raise HTTPException(
                409, {"reason": "awaiting_decision", "detail": str(error)}
            ) from None

    @app.get("/api/worlds/{world_id}")
    def world_state(world_id: str) -> dict[str, Any]:
        return world_or_404(world_id).state()

    @app.get("/api/worlds/{world_id}/checkpoints")
    def checkpoints(world_id: str) -> list[dict[str, Any]]:
        world_or_404(world_id)
        return store.checkpoints(world_id)

    @app.post("/api/worlds/{world_id}/finish")
    def finish(world_id: str) -> dict[str, Any]:
        return world_or_404(world_id).finish()

    def world_action(world_id: str, act: Callable[[PersistentWorld], Any]) -> Any:
        """Run one Formal Spec 10.4 service action; a refusal is 409 with why."""
        try:
            return act(world_or_404(world_id))
        except WorldClosed as error:
            raise HTTPException(
                409, {"reason": "closed", "detail": str(error)}
            ) from None
        except ValueError as error:
            raise HTTPException(
                409, {"reason": "invalid_state", "detail": str(error)}
            ) from None

    @app.post("/api/worlds/{world_id}/pause")
    def pause(world_id: str) -> dict[str, Any]:
        return dict(world_action(world_id, lambda world: world.pause()))

    @app.post("/api/worlds/{world_id}/resume")
    def resume(world_id: str) -> dict[str, Any]:
        return dict(world_action(world_id, lambda world: world.resume()))

    @app.post("/api/worlds/{world_id}/terminate")
    def terminate(world_id: str) -> dict[str, Any]:
        return dict(world_action(world_id, lambda world: world.terminate()))

    @app.post("/api/worlds/{world_id}/archive")
    def archive(world_id: str) -> dict[str, Any]:
        archived = dict(world_action(world_id, lambda world: world.archive()))
        with worlds_lock:
            worlds.pop(world_id, None)
        return archived

    @app.post("/api/worlds/{world_id}/branch", status_code=201)
    def branch(world_id: str) -> dict[str, Any]:
        source = world_or_404(world_id)
        job = admit({**source.request, "kind": "persistent_world"})
        try:
            twin = world_action(world_id, lambda world: world.branch(job["job_id"]))
        except HTTPException:
            store.update_job(job["job_id"], lifecycle_state="failed", error="branch")
            raise
        with worlds_lock:
            worlds[twin.world_id] = twin
        return dict(twin.state())

    @app.delete("/api/worlds/{world_id}")
    def delete(world_id: str) -> dict[str, Any]:
        world = world_or_404(world_id)
        world.delete()
        with worlds_lock:
            worlds.pop(world_id, None)
        return {"world_id": world_id, "lifecycle_state": "deleted"}

    # Formal Spec 10.2 Monitoring Mode: outside data that may call for a rerun
    add_monitor_routes(app, store, admit, queue)

    # What the external interface (Phase 12) shares with these routes
    app.state.worlds = worlds
    app.state.worlds_lock = worlds_lock
    app.state.admit = admit
    app.state.refuse = refuse
    app.state.create_world = create_world

    # the UI's screens, read from this store (Phase 21): no workspace folder
    @app.get("/api/runs")
    def run_list() -> list[dict[str, Any]]:
        return runs(store)

    add_view_routes(app, lambda run: workspace_from_store(store, run))
    if external_routes:
        add_external_routes(app, store, queue, policy)
    return app
