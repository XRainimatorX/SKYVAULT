"""The external interface's HTTP routes (development plan Phase 12).

Important:
The paths are the development plan's: /scenario/submit, /world/create,
/action/submit, /run/{run_id} (+ /events, /result), /failure_exploration/run,
/branch_compare/run, /branch_conflict/resolve and /conflict/{id} (+ /branches,
/package). run_id is the world service's job id; a persistent world's id is
its job id too. Added: /submission/{id} — what a system gets back for its
submission (Formal Spec section 9) — /run/{run_id}/state_action_outcome and
/run/{run_id}/decision for a run's own handoff.

They live on the world service's app and share its store, queue, worlds and
admission. Nobody but a decision authority decides: SKYVAULT, or anyone
else, deciding a conflict or a handoff is refused with 403; a world waiting
on a conflict does not advance (409).
"""

from collections.abc import Collection
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException

from ..contracts import ContractError
from ..training.transitions import build_transitions
from ..worldservice.jobs import execute_job, new_job, plan, scenario_for
from ..worldservice.queues import JobQueue
from ..worldservice.store import JobStore
from ..worldservice.worlds import PersistentWorld, WorldClosed
from .handoff import decide
from .systems import to_request, to_return

JSONBody = Annotated[dict[str, Any], Body()]
FINISHED = ("completed", "failed", "archived", "replayed", "deleted")


def run_submission(
    submission: dict[str, Any], store: JobStore, policy: dict[str, Any]
) -> dict[str, Any]:
    """
    A submission carried out here and now, without a queue: every job
    planned (governance still admits it), run on this thread and read back.
    Returns {request, results, returned}; a job that fails raises
    RuntimeError with its error.
    """
    request = to_request(submission)
    results = []
    for job_request in request["jobs"]:
        planned = plan(job_request, policy, 0, store)
        job = new_job(store, job_request, planned, policy)
        execute_job(job["job_id"], store, policy)
        job = store.get_job(job["job_id"])
        if job["lifecycle_state"] != "completed":
            raise RuntimeError(f"{job['job_id']} failed: {job['error']}")
        results.append(
            {
                "job": job,
                "result": store.get_result(job["job_id"]),
                "scenario": scenario_for(job["request"]),
            }
        )
    returned = (
        to_return(results, submission)
        if request["supported"]
        else {"system": request["system"], "supported": False, "gaps": request["gaps"]}
    )
    return {"request": request, "results": results, "returned": returned}


def problem(status: int, reason: str, detail: str) -> HTTPException:
    return HTTPException(status, {"reason": reason, "detail": detail})


def add_external_routes(
    app: FastAPI,
    store: JobStore,
    queue: JobQueue,
    policy: dict[str, Any],
    systems: Collection[str] | None = None,
) -> None:
    """
    Add the external interface to a world service app (create_world_service).

    systems: the only systems whose submissions are taken (Phase 19: an
    edition's); others get 403 not_licensed. None takes every system.
    """
    worlds: dict[str, PersistentWorld] = app.state.worlds

    def refuse(error: Exception) -> HTTPException:
        if isinstance(error, PermissionError):
            return problem(403, "not_an_authority", str(error))
        if isinstance(error, WorldClosed):
            return problem(409, "closed", str(error))
        refused: HTTPException = app.state.refuse(error)
        return refused

    def queued(request: dict[str, Any]) -> dict[str, Any]:
        job: dict[str, Any] = app.state.admit(request)
        queue.submit(job["job_id"], job["priority"])
        return job

    def queued_together(
        requests: list[dict[str, Any]], submission: dict[str, Any]
    ) -> list[str]:
        """
        Admit every job of one submission, then queue them: a refused job
        fails the ones admitted before it, so nothing runs half a submission.
        The submission is recorded in each job before a worker can see it.
        """
        admitted: list[dict[str, Any]] = []
        try:
            for request in requests:
                admitted.append(app.state.admit(request))
        except HTTPException:
            for job in admitted:
                store.update_job(
                    job["job_id"],
                    lifecycle_state="failed",
                    error="another job of its submission was refused",
                )
            raise
        if not admitted:
            return []
        submission_id = admitted[0]["job_id"]
        for job in admitted:
            store.update_job(
                job["job_id"],
                summary_fields={
                    "submission_id": submission_id,
                    "external_submission": submission,
                },
            )
        for job in admitted:
            queue.submit(job["job_id"], job["priority"])
        return [job["job_id"] for job in admitted]

    def job_or_404(run_id: str) -> dict[str, Any]:
        try:
            return store.get_job(run_id)
        except KeyError as error:
            raise refuse(error) from None

    def world_or_404(world_id: str) -> PersistentWorld:
        world = worlds.get(world_id)
        if world is None:
            raise problem(404, "not_found", f"no live world {world_id}")
        return world

    def result_or_error(run_id: str) -> dict[str, Any]:
        job = job_or_404(run_id)
        result = store.get_result(run_id)
        if result is None:
            if job["lifecycle_state"] in FINISHED:
                raise problem(404, "no_result", job["error"] or "no result was kept")
            raise problem(409, "not_ready", f"the run is {job['lifecycle_state']}")
        return result

    def conflict_or_404(conflict_id: str) -> dict[str, Any]:
        try:
            return store.get_conflict(conflict_id)
        except KeyError as error:
            raise refuse(error) from None

    # ── submissions ──────────────────────────────────────────────────────────

    @app.post("/scenario/submit", status_code=202)
    def submit_scenario(submission: JSONBody) -> dict[str, Any]:
        """
        Any system's submission (external_submission): its jobs are queued,
        its world actions go into the world's window, and what has no model
        comes back as gaps without anything running.
        """
        if systems is not None and submission.get("system") not in systems:
            raise problem(
                403,
                "not_licensed",
                f"this service takes submissions from {', '.join(sorted(systems))}",
            )
        try:
            planned = to_request(submission)
        except (ContractError, ValueError) as error:
            raise refuse(error) from None
        proposals = []
        if planned["world_actions"] is not None:
            target = planned["world_actions"]
            world = world_or_404(target["world_id"])
            for action in target["actions"]:
                order = {
                    k: v
                    for k, v in action.items()
                    if k not in ("tick", "actor_id", "system_id")
                }
                try:
                    proposals.append(
                        world.submit(
                            planned["system"],
                            action["tick"],
                            action["actor_id"],
                            order,
                        )
                    )
                except (WorldClosed, KeyError, ValueError, ContractError) as error:
                    raise refuse(error) from None
        run_ids = queued_together(planned["jobs"], submission)
        return {
            "submission_id": run_ids[0] if run_ids else None,
            "system": planned["system"],
            "supported": planned["supported"],
            "run_ids": run_ids,
            "proposals": proposals,
            "gaps": planned["gaps"],
            # what has no model is answered now: nothing will run for it
            "returned": (
                None
                if planned["supported"]
                else {
                    "system": planned["system"],
                    "supported": False,
                    "gaps": planned["gaps"],
                }
            ),
        }

    @app.get("/submission/{submission_id}")
    def submission_return(submission_id: str) -> dict[str, Any]:
        """What the system gets back, once every run of its submission is done."""
        jobs = sorted(
            (
                j
                for j in store.list_jobs()
                if j["summary"].get("submission_id") == submission_id
            ),
            key=lambda j: j["job_id"],
        )
        if not jobs:
            raise problem(404, "not_found", f"no submission {submission_id}")
        waiting = [j["job_id"] for j in jobs if j["lifecycle_state"] not in FINISHED]
        if waiting:
            raise problem(409, "not_ready", f"still running: {', '.join(waiting)}")
        failed = [j for j in jobs if j["lifecycle_state"] == "failed"]
        if failed:
            raise problem(
                409, "failed", f"{failed[0]['job_id']} failed: {failed[0]['error']}"
            )
        results = [
            {
                "job": job,
                "result": store.get_result(job["job_id"]),
                "scenario": scenario_for(job["request"]),
            }
            for job in jobs
        ]
        return to_return(results, jobs[0]["summary"]["external_submission"])

    @app.post("/world/create", status_code=201)
    def create_world(request: JSONBody) -> dict[str, Any]:
        """A persistent world outside systems can submit actions into."""
        state: dict[str, Any] = app.state.create_world(request)
        return state

    @app.post("/action/submit", status_code=202)
    def submit_action(body: JSONBody) -> dict[str, Any]:
        """{world_id, system, tick, actor_id, order}: queued for that tick."""
        missing = sorted(
            {"world_id", "system", "tick", "actor_id", "order"} - set(body)
        )
        if missing:
            raise problem(422, "invalid_request", f"missing {missing}")
        world = world_or_404(body["world_id"])
        try:
            return world.submit(
                body["system"], body["tick"], body["actor_id"], body["order"]
            )
        except (WorldClosed, KeyError, ValueError, ContractError) as error:
            raise refuse(error) from None

    @app.post("/failure_exploration/run", status_code=202)
    def failure_exploration(request: JSONBody) -> dict[str, Any]:
        return queued({**request, "kind": "failure_exploration"})

    @app.post("/branch_compare/run", status_code=202)
    def branch_compare(request: JSONBody) -> dict[str, Any]:
        return queued({**request, "kind": "branch_compare"})

    # ── runs ─────────────────────────────────────────────────────────────────

    @app.get("/run/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        job = job_or_404(run_id)
        world = worlds.get(run_id)
        return {
            **job,
            "handoff": job["summary"].get("handoff"),
            "world": world.state() if world is not None else None,
            "events": store.events(run_id),
        }

    @app.get("/run/{run_id}/events")
    def run_events(run_id: str) -> dict[str, Any]:
        """The run's event memory (a live world's so far) and its job events."""
        job_or_404(run_id)
        world = worlds.get(run_id)
        result = store.get_result(run_id)
        if result is not None:
            memory = result["event_memory"]
        elif world is not None:
            memory = world.events()
        else:
            memory = None
        return {
            "run_id": run_id,
            "event_memory": memory,
            "job_events": store.events(run_id),
        }

    @app.get("/run/{run_id}/result")
    def run_result(run_id: str) -> dict[str, Any]:
        return result_or_error(run_id)

    @app.get("/run/{run_id}/state_action_outcome")
    def state_action_outcome(run_id: str, system: str | None = None) -> dict[str, Any]:
        """State-action-outcome records of a finished run, one system's if named."""
        package = result_or_error(run_id)
        if "event_memory" not in package:
            raise problem(422, "invalid_request", "this run has no single event memory")
        records = build_transitions(
            package, scenario_for(job_or_404(run_id)["request"])
        )
        if system is not None:
            records = [r for r in records if r["action"]["system_id"] == system]
        return {"run_id": run_id, "system": system, "state_action_outcome": records}

    @app.post("/run/{run_id}/decision")
    def run_decision(run_id: str, body: JSONBody) -> dict[str, Any]:
        """An authority's decision on the handoff a run raised."""
        job = job_or_404(run_id)
        handoff = job["summary"].get("handoff")
        if handoff is None:
            raise problem(404, "no_handoff", f"{run_id} raised no handoff")
        if not str(body.get("decision", "")).strip():
            raise problem(422, "invalid_request", "a decision says what was decided")
        try:
            decided = decide(handoff, str(body.get("decided_by")), body["decision"])
        except PermissionError as error:
            raise refuse(error) from None
        except ValueError as error:
            raise problem(409, "decided", str(error)) from None
        store.merge_summary(run_id, handoff=decided)
        store.log(run_id, f"{decided['decided_by']} decided the handoff")
        return decided

    # ── conflicts ────────────────────────────────────────────────────────────

    @app.get("/conflict/{conflict_id}")
    def conflict(conflict_id: str) -> dict[str, Any]:
        return conflict_or_404(conflict_id)

    @app.get("/conflict/{conflict_id}/branches")
    def conflict_branches(conflict_id: str) -> dict[str, Any]:
        record = conflict_or_404(conflict_id)
        return {
            "conflict_id": conflict_id,
            "branches": record["branches"],
            "branch_comparison": record["branch_comparison"],
        }

    @app.get("/conflict/{conflict_id}/package")
    def conflict_package(conflict_id: str) -> dict[str, Any]:
        record = conflict_or_404(conflict_id)
        return {
            **record["conflict_package"],
            "conflict_id": conflict_id,
            "world_id": record["world_id"],
            "tick": record["tick"],
            "status": record["status"],
        }

    @app.post("/branch_conflict/resolve")
    def resolve_conflict(body: JSONBody) -> dict[str, Any]:
        """{conflict_id, branch_id, decided_by}: only a decision authority."""
        record = conflict_or_404(str(body.get("conflict_id")))
        world = world_or_404(record["world_id"])
        try:
            return world.decide(
                record["conflict_id"],
                str(body.get("branch_id")),
                str(body.get("decided_by")),
            )
        except PermissionError as error:
            raise refuse(error) from None
        except ValueError as error:
            raise problem(409, "decided", str(error)) from None
        except KeyError as error:
            raise refuse(error) from None
