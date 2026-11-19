"""Monitoring Mode = Formal Spec 10.2: take in outside data, decide whether to rerun.

Important:
A monitor watches one scenario for one outside system. Each delivery of
data (unit changes, as a scenario_run request carries them, with the data's
provenance) is compared with the last delivery: the first delivery, a new
unit, a changed non-numeric value or a numeric value that moved by at least
the monitor's threshold (relative) calls for a rerun, and the monitor
submits a scenario_run of the scenario with that data. Anything smaller is
recorded and nothing runs. A monitor runs nothing of its own and costs no
compute; the reruns it submits are governed like any other job.
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException

from .jobs import scenario_for
from .queues import JobQueue
from .store import JobStore

JSONBody = Annotated[dict[str, Any], Body()]
DEFAULT_THRESHOLD = 0.1


def material_changes(
    before: dict[str, Any] | None, after: dict[str, Any], threshold: float
) -> list[str]:
    """What moved enough between two deliveries to call for a rerun."""
    if before is None:
        return ["first data for this scenario"]
    changes: list[str] = []
    for unit, fields in sorted(after.items()):
        if unit not in before:
            changes.append(f"{unit}: new unit")
            continue
        changes += _compare(unit, before[unit], fields, threshold)
    return changes


def _compare(path: str, old: Any, new: Any, threshold: float) -> list[str]:
    if isinstance(new, dict) and isinstance(old, dict):
        found: list[str] = []
        for key in sorted(new):
            if key not in old:
                found.append(f"{path}.{key}: newly reported")
            else:
                found += _compare(f"{path}.{key}", old[key], new[key], threshold)
        return found
    numeric = (int, float)
    if isinstance(new, numeric) and isinstance(old, numeric):
        if isinstance(new, bool) or isinstance(old, bool):
            return [] if new == old else [f"{path}: {old!r} -> {new!r}"]
        base = abs(float(old)) or 1.0
        moved = abs(float(new) - float(old)) / base
        if moved >= threshold:
            return [f"{path}: {old:g} -> {new:g} ({moved:.0%})"]
        return []
    return [] if new == old else [f"{path}: {old!r} -> {new!r}"]


def add_monitor_routes(
    app: FastAPI,
    store: JobStore,
    admit: Callable[..., dict[str, Any]],
    queue: JobQueue,
) -> None:
    """POST /api/monitors, POST /api/monitors/{id}/data, GET and DELETE one."""

    def monitor_or_404(monitor_id: str) -> dict[str, Any]:
        try:
            job = store.get_job(monitor_id)
        except KeyError:
            job = None
        if job is None or job["request"]["kind"] != "monitor":
            raise HTTPException(
                404, {"reason": "not_found", "detail": f"no monitor {monitor_id}"}
            )
        return job

    @app.post("/api/monitors", status_code=201)
    def create_monitor(request: JSONBody) -> dict[str, Any]:
        threshold = request.get("threshold", DEFAULT_THRESHOLD)
        if not isinstance(threshold, int | float) or not 0 < threshold <= 1:
            raise HTTPException(
                422,
                {"reason": "invalid_request", "detail": "threshold is in (0, 1]"},
            )
        job = admit(
            {
                "kind": "monitor",
                "scenario": request.get("scenario"),
                "source_system": request.get("source_system", "user"),
            }
        )
        store.update_job(
            job["job_id"],
            lifecycle_state="running",
            summary_fields={
                "monitor": {"threshold": threshold, "last_data": None, "reruns": []}
            },
        )
        store.log(job["job_id"], f"monitoring {job['request']['scenario']}")
        return store.get_job(job["job_id"])

    @app.get("/api/monitors/{monitor_id}")
    def get_monitor(monitor_id: str) -> dict[str, Any]:
        return monitor_or_404(monitor_id)

    @app.post("/api/monitors/{monitor_id}/data")
    def deliver(monitor_id: str, body: JSONBody) -> dict[str, Any]:
        job = monitor_or_404(monitor_id)
        if job["lifecycle_state"] != "running":
            raise HTTPException(
                409, {"reason": "closed", "detail": f"{monitor_id} is stopped"}
            )
        data = body.get("entity_changes")
        if not isinstance(data, dict) or not data:
            raise HTTPException(
                422,
                {"reason": "invalid_request", "detail": "send entity_changes"},
            )
        state = job["summary"]["monitor"]
        changes = material_changes(state["last_data"], data, state["threshold"])
        decision: dict[str, Any] = {"rerun": bool(changes), "changes": changes}
        if changes:
            rerun = admit(
                {
                    "kind": "scenario_run",
                    "scenario": job["request"]["scenario"],
                    "source_system": body.get(
                        "source_system", job["request"]["source_system"]
                    ),
                    "entity_changes": data,
                    **(
                        {"data_provenance": body["data_provenance"]}
                        if body.get("data_provenance")
                        else {}
                    ),
                }
            )
            queue.submit(rerun["job_id"], rerun["priority"])
            decision["job_id"] = rerun["job_id"]
            state["reruns"].append(rerun["job_id"])
        else:
            decision["reason"] = (
                f"nothing moved by {state['threshold']:.0%} or more since the last data"
            )
        state["last_data"] = data
        store.update_job(monitor_id, summary_fields={"monitor": state})
        store.log(
            monitor_id,
            "rerun " + decision["job_id"] if changes else "no rerun needed",
        )
        return decision

    @app.delete("/api/monitors/{monitor_id}")
    def stop_monitor(monitor_id: str) -> dict[str, Any]:
        monitor_or_404(monitor_id)
        store.update_job(monitor_id, lifecycle_state="completed")
        store.log(monitor_id, "stopped")
        return {"monitor_id": monitor_id, "lifecycle_state": "completed"}

    # a monitor names a scenario SKYVAULT has, like any job
    app.state.monitor_scenario = scenario_for
