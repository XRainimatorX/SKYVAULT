"""What the UI shows, read from the world service's store (Phase 21).

Important:
A run is a finished job that kept a result package: a scenario run, a
persistent world or a replay. Its workspace — what the screens and the
briefing read, keyed as views.load_workspace — is that package, plus the
newest finished failure exploration and batch of the same scenario when
there are any: what used to be three scripts writing one folder.
"""

from typing import Any

from ..batch.aggregate import render_comparative_report
from ..failure import build_survival_conditions, render_recommended_modifications
from ..service import NoSuchRun
from ..views.workspace import JSON_FILES, TEXT_FILES
from .jobs import batch_for
from .store import JobStore

RUN_KINDS = ("scenario_run", "persistent_world", "replay")
LATEST = "latest"


def runs(store: JobStore) -> list[dict[str, Any]]:
    """Every run with a result package, newest first, in a line each."""
    found = []
    for job in reversed(store.list_jobs()):
        if job["request"]["kind"] not in RUN_KINDS:
            continue
        package = store.get_result(job["job_id"])
        if package is None:
            continue
        found.append(
            {
                "run": job["job_id"],
                "kind": job["request"]["kind"],
                "scenario_id": package["scenario_id"],
                "scenario_version": package["scenario_version"],
                "result": package["evaluation_result"]["winner_or_result"],
                "events": len(package["event_memory"]),
                "output_hash": package["reproducibility"]["output_hash"][:12],
                "created_at": job["created_at"],
            }
        )
    return found


def workspace_from_store(store: JobStore, run: str) -> dict[str, Any]:
    """
    The run's workspace. NoSuchRun when the run is unknown, is not a run,
    or kept no result ("latest" with no run at all included).
    """
    if run == LATEST:
        newest = runs(store)
        if not newest:
            raise NoSuchRun("No run yet: submit one (skyvault run <scenario>)")
        run = newest[0]["run"]
    try:
        job = store.get_job(run)
    except KeyError:
        raise NoSuchRun(f"no run {run}") from None
    if job["request"]["kind"] not in RUN_KINDS:
        raise NoSuchRun(f"{run} is a {job['request']['kind']} job, not a run")
    package = store.get_result(run)
    if package is None:
        raise NoSuchRun(f"{run} kept no result package ({job['lifecycle_state']})")

    workspace: dict[str, Any] = {key: None for key in [*JSON_FILES, *TEXT_FILES]}
    workspace["result_package"] = package
    scenario_id = package["scenario_id"]
    failure_map = _newest(store, "failure_exploration", scenario_id)
    if failure_map is not None:
        conditions = build_survival_conditions(failure_map)
        workspace["failure_map"] = failure_map
        workspace["survival_conditions"] = conditions
        workspace["recommended_modifications"] = render_recommended_modifications(
            failure_map, conditions
        )
    batch = _newest(store, "batch", scenario_id)
    if batch is not None:
        for key in ("batch_result", "branch_comparison", "conflict_package"):
            workspace[key] = batch[key]
        workspace["comparative_report"] = render_comparative_report(
            batch["batch_result"], batch["branch_comparison"], batch["conflict_package"]
        )
    return workspace


def _newest(store: JobStore, kind: str, scenario_id: str) -> dict[str, Any] | None:
    """The result of the newest finished job of kind on scenario_id, or None."""
    for job in reversed(store.list_jobs()):
        request = job["request"]
        if request["kind"] != kind or job["lifecycle_state"] != "completed":
            continue
        if _scenario_of(request) == scenario_id:
            result = store.get_result(job["job_id"])
            if result is not None:
                return result
    return None


def _scenario_of(request: dict[str, Any]) -> str | None:
    if request.get("scenario"):
        return str(request["scenario"]).split("/")[0]
    if request.get("batch"):
        try:
            return str(batch_for(request)["scenario_id"])
        except (OSError, ValueError, KeyError):
            return None
    return None
