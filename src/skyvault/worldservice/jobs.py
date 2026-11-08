"""Jobs = what the world service runs: one scenario, a batch, an exploration, a replay.

Important:
plan() looks at a request before it is queued: it finds what the request
names (only under data/, never an arbitrary path), estimates the cost and
lets governance refuse it. execute_job() runs a queued job on a worker,
under the policy, and leaves its result and its record in the store. A job
that fails is recorded as failed with the error; it never takes the worker
down. Runs that are stopped early still leave their partial result.
"""

import copy
import json
import time
from pathlib import Path
from typing import Any

from ..batch.aggregate import aggregate, compare_branches
from ..batch.run import planned_variants, run_batch
from ..batch.runner import run_jobs
from ..batch.variants import Variant, branch_variant
from ..contracts import (
    JobRequest,
    validate_failure_map,
    validate_job_request,
    validate_scenario,
)
from ..engine import SkyVaultTacticalReferenceEngine
from ..failure import build_failure_map, explore_failures
from ..interface.handoff import authority_handoff, handoff_triggers
from ..replay import build_replay_state_at_tick
from ..scenario_loader import (
    default_evaluation_profile,
    load_evaluation_profile,
    scenario_perspective,
)
from .governance import (
    Governor,
    admit,
    clamp_duration,
    estimate_run,
    limits,
    scale,
)
from .store import JobStore, now

DATA = Path(__file__).resolve().parents[3] / "data"
SCENARIOS_DIR = DATA / "scenarios"
BATCHES_DIR = DATA / "batches"
PROFILES_DIR = DATA / "evaluation_profiles"

# runtime fields a request may override; anything else is the scenario's own
RUNTIME_OVERRIDES = {
    "max_ticks",
    "random_seed",
    "random_seed_policy",
    "policy",
    "participants",
    "scheduled_actions",
}


class NotFound(ValueError):
    """A request names something SKYVAULT does not have."""


def _named(folder: Path, name: str, suffix: str = ".json") -> Path:
    """folder/name.json, refused unless it exists inside folder."""
    path = (folder / f"{name}{suffix}").resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise NotFound(f"nothing named {name!r} in data/{folder.name}")
    return path


def scenario_for(
    request: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
) -> dict[str, Any]:
    """
    The scenario a request names, with its runtime overrides, unit changes
    and data provenance, checked.
    """
    scenario = json.loads(
        _named(scenarios_dir, request["scenario"]).read_text(encoding="utf-8")
    )
    extra = set(request.get("runtime", {})) - RUNTIME_OVERRIDES
    if extra:
        raise ValueError(f"runtime fields a request may not set: {sorted(extra)}")
    scenario["runtime"].update(copy.deepcopy(request.get("runtime", {})))
    scenario = changed_entities(scenario, request.get("entity_changes"))
    if request.get("data_provenance"):
        provenance = copy.deepcopy(request["data_provenance"])
        provenance["scenario_id"] = (
            provenance.get("scenario_id") or scenario["scenario_id"]
        )
        scenario["data_provenance"] = provenance
    return validate_scenario(scenario)


def changed_entities(
    scenario: dict[str, Any], changes: dict[str, Any] | None
) -> dict[str, Any]:
    """
    A copy of scenario with units changed: name and type replaced,
    capabilities and state merged key by key.

    Important:
    A change to a unit the scenario does not have is refused with NotFound —
    a request may change what SKYVAULT has, never add to it.
    """
    if not changes:
        return scenario
    changed = copy.deepcopy(scenario)
    units = {unit["entity_id"]: unit for unit in changed["entities"]}
    unknown = sorted(set(changes) - set(units))
    if unknown:
        raise NotFound(f"{scenario['scenario_id']} has no units {unknown}")
    for entity_id, change in changes.items():
        unit = units[entity_id]
        for field in ("name", "entity_type"):
            if change.get(field) is not None:
                unit[field] = change[field]
        for field in ("capabilities", "state"):
            unit[field] = {**unit.get(field, {}), **change.get(field, {})}
    return changed


def profile_for(request: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """The evaluation profile a request names, else the scenario's default."""
    if request.get("profile"):
        return load_evaluation_profile(_named(PROFILES_DIR, request["profile"]))
    return default_evaluation_profile(scenario)


def batch_for(
    request: dict[str, Any], batches_dir: Path = BATCHES_DIR
) -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(
        _named(batches_dir, request["batch"]).read_text(encoding="utf-8")
    )
    if request.get("repeat_count"):
        spec["run_policy"]["repeat_count"] = request["repeat_count"]
    return spec


def exploration_runs(scenario: dict[str, Any], repeats: int | None) -> int:
    """
    Runs one failure exploration makes: the plan's baseline, every variable at
    every level and one branch; each alternative's baseline and every variable
    at every level (no branch); all repeated. An upper bound only when a
    variable does not apply to a plan and skips its levels.
    """
    config = scenario["failure_exploration"]
    levels = len(config.get("stress_levels", [])) or 4
    sweep = 1 + len(config["failure_variables"]) * levels
    alternatives = len(config.get("alternatives", []))
    runs_once = sweep + 1 + sweep * alternatives
    return runs_once * (repeats or config["run_policy"]["repeat_count"])


def compare_variants(
    request: dict[str, Any], scenarios_dir: Path = SCENARIOS_DIR
) -> list[Variant]:
    """
    A branch_compare's variants: one per named branch and the baseline with
    none. A branch schedules its actions and changes its units
    (entity_changes). Each branch's scenario passes the scenario contract,
    so a branch that orders one unit twice at one tick is refused at the door.
    """
    base = scenario_for(request, scenarios_dir)
    variants = []
    for branch in request["branches"]:
        proposals = [
            {
                **action,
                "system_id": action.get("system_id", request["source_system"]),
                "proposal_id": f"{branch['branch_id']}:{n}",
            }
            for n, action in enumerate(branch.get("actions", []), 1)
        ]
        variant = branch_variant(base, branch["branch_id"], proposals)
        changed = changed_entities(variant.scenario, branch.get("entity_changes"))
        validate_scenario(changed)
        variants.append(Variant(variant.variant_id, variant.kind, changed))
    variants.append(branch_variant(base, "none", []))
    return variants


def full_request(request: dict[str, Any]) -> dict[str, Any]:
    """A request checked against its contract, every default filled in."""
    validate_job_request(request)
    full: dict[str, Any] = JobRequest.model_validate(request).model_dump(mode="json")
    return full


def plan(
    request: dict[str, Any],
    policy: dict[str, Any],
    queue_length: int,
    store: JobStore | None = None,
    scenarios_dir: Path = SCENARIOS_DIR,
    batches_dir: Path = BATCHES_DIR,
) -> dict[str, Any]:
    """
    What a request will cost, or Rejected / NotFound / ContractError.

    Returns {estimated_cost, duration_clamped_from}.
    """
    request = full_request(request)
    kind = request["kind"]
    clamped = None
    if kind in ("scenario_run", "persistent_world", "failure_exploration"):
        scenario = scenario_for(request, scenarios_dir)
        clamped = clamp_duration(scenario, policy)
        estimate = estimate_run(scenario)
        if kind == "failure_exploration":
            estimate = scale(
                estimate, exploration_runs(scenario, request.get("repeat_count"))
            )
    elif kind == "branch_compare":
        variants = compare_variants(request, scenarios_dir)
        estimate = scale(
            estimate_run(variants[0].scenario),
            len(variants) * (request.get("repeat_count") or 1),
        )
    elif kind == "batch":
        spec = batch_for(request, batches_dir)
        base = json.loads(
            _named(
                scenarios_dir, f"{spec['scenario_id']}/{spec['base_version']}"
            ).read_text()
        )
        variants = planned_variants(spec, base, scenarios_dir)
        estimate = scale(
            estimate_run(base), len(variants) * spec["run_policy"]["repeat_count"]
        )
    else:
        if store is None:
            raise ValueError("a replay needs the store to find its job")
        original = store.get_job(request["replay"])
        if store.get_result(original["job_id"]) is None:
            raise NotFound(f"job {original['job_id']} has no result to replay")
        estimate = original["estimated_cost"] or {
            "runs": 1,
            "decisions": 0,
            "seconds": 0.0,
        }
    admit(estimate, policy, queue_length)
    return {"estimated_cost": estimate, "duration_clamped_from": clamped}


def execute_job(
    job_id: str,
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path = SCENARIOS_DIR,
    batches_dir: Path = BATCHES_DIR,
) -> None:
    """Run a queued job on this worker and record how it went."""
    job = store.get_job(job_id)
    if job["summary"].get("cancel_requested"):
        store.update_job(
            job_id, lifecycle_state="failed", error="cancelled before it ran"
        )
        store.log(job_id, "cancelled before it ran")
        return
    store.update_job(job_id, lifecycle_state="running")
    store.log(job_id, f"running on a worker ({job['request']['kind']})")
    governed = dict(policy, run_priority=job["priority"])
    try:
        runner = {
            "scenario_run": _scenario_run,
            "batch": _batch,
            "failure_exploration": _failure_exploration,
            "replay": _replay,
            "branch_compare": _branch_compare,
        }[job["request"]["kind"]]
        runner(job, store, governed, scenarios_dir, batches_dir)
    except Exception as error:  # a failed job is recorded, never raised on the worker
        store.update_job(
            job_id, lifecycle_state="failed", error=f"{type(error).__name__}: {error}"
        )
        store.log(job_id, f"failed: {type(error).__name__}: {error}")


def _governor(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenario: dict[str, Any],
    clamped: int | None,
) -> Governor:
    def cancelled() -> bool:
        return bool(store.get_job(job["job_id"])["summary"].get("cancel_requested"))

    return Governor(
        policy,
        scenario_perspective(scenario),
        estimated_cost=job["estimated_cost"],
        duration_clamped_from=clamped,
        cancel_check=cancelled,
    )


def run_scenario(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
) -> dict[str, Any]:
    """One governed run of the job's scenario; its result package."""
    scenario = scenario_for(job["request"], scenarios_dir)
    clamped = clamp_duration(scenario, policy)
    engine = SkyVaultTacticalReferenceEngine(
        scenario,
        evaluation_profile=profile_for(job["request"], scenario),
        governor=_governor(job, store, policy, scenario, clamped),
    )
    return engine.run()


def _finish_run(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    package: dict[str, Any],
    **summary: Any,
) -> None:
    record = package["reproducibility"]["run_metadata"]["resource_compute_governance"]
    keep = not record["partial"] or policy["partial_result_export"]
    if keep:
        store.save_result(job["job_id"], package)
    verdict = package["evaluation_result"]
    store.update_job(
        job["job_id"],
        lifecycle_state="completed",
        governance=record,
        summary={
            **job["summary"],
            "result": verdict["winner_or_result"],
            "termination_reason": verdict["termination_reason"],
            "events": len(package["event_memory"]),
            "output_hash": package["reproducibility"]["output_hash"],
            "partial": record["partial"],
            "result_kept": keep,
            "handoff": authority_handoff(
                handoff_triggers(result=package), result=package
            ),
            **summary,
        },
    )
    stop = f", stopped: {record['stop_reason']}" if record["stopped"] else ""
    store.log(job["job_id"], f"completed: {verdict['winner_or_result']}{stop}")


def _scenario_run(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
) -> None:
    _finish_run(job, store, policy, run_scenario(job, store, policy, scenarios_dir))


def _many_runs_record(
    policy: dict[str, Any], job: dict[str, Any], runs: int, events: int, seconds: float
) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "run_priority": policy["run_priority"],
        "limits": {
            **limits(policy),
            "max_batch_count": policy["max_batch_count"],
            "max_parallel_runs": policy["max_parallel_runs"],
        },
        "usage": {
            "runs": runs,
            "ticks": None,
            "decisions": None,
            "events": events,
            "runtime_seconds": round(seconds, 6),
        },
        "estimated_cost": job["estimated_cost"],
        "stopped": False,
        "stop_reason": None,
        "partial": False,
        "duration_clamped_from": None,
    }


def _batch(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
) -> None:
    spec = batch_for(job["request"], batches_dir)
    workers = min(int(spec.get("workers", 1)), policy["max_parallel_runs"])
    started = time.monotonic()
    out = run_batch(spec, scenarios_dir, PROFILES_DIR, workers=workers)
    runs = out["batch_result"]["runs"]
    store.save_result(job["job_id"], out)
    store.update_job(
        job["job_id"],
        lifecycle_state="completed",
        governance=_many_runs_record(
            policy,
            job,
            len(runs),
            sum(r["event_count"] for r in runs),
            time.monotonic() - started,
        ),
        summary={
            **job["summary"],
            "runs": len(runs),
            "workers": workers,
            "variants": len(out["batch_result"]["variants"]),
            "handoff": authority_handoff(
                handoff_triggers(conflict_package=out["conflict_package"]),
                branch_comparison=out["branch_comparison"],
                conflict_package=out["conflict_package"],
            ),
        },
    )
    store.log(job["job_id"], f"completed: {len(runs)} runs on {workers} workers")


def _failure_exploration(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
) -> None:
    scenario = scenario_for(job["request"], scenarios_dir)
    config = copy.deepcopy(scenario["failure_exploration"])
    if job["request"].get("repeat_count"):
        config["run_policy"]["repeat_count"] = job["request"]["repeat_count"]
    started = time.monotonic()
    exploration = explore_failures(
        scenario, profile_for(job["request"], scenario), config, scenarios_dir
    )
    failure_map = validate_failure_map(build_failure_map(exploration))
    store.save_result(job["job_id"], failure_map)
    runs = job["estimated_cost"]["runs"]
    store.update_job(
        job["job_id"],
        lifecycle_state="completed",
        governance=_many_runs_record(policy, job, runs, 0, time.monotonic() - started),
        summary={
            **job["summary"],
            "crushing_variable": failure_map["crushing_variable"],
            "survival_rate": failure_map["baseline"]["survival_rate"],
            "handoff": authority_handoff(
                handoff_triggers(failure_map=failure_map), failure_map=failure_map
            ),
        },
    )
    store.log(
        job["job_id"], f"completed: crushed by {failure_map['crushing_variable']}"
    )


def _branch_compare(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
) -> None:
    """STARTX's branches, each run repeat_count times, compared with the baseline."""
    request = job["request"]
    variants = compare_variants(request, scenarios_dir)
    base = variants[-1].scenario
    profile = profile_for(request, base)
    perspective = profile.get("perspective") or scenario_perspective(base) or ""
    seed = int(base["runtime"]["random_seed"])
    seeds = [seed + n for n in range(request.get("repeat_count") or 1)]
    started = time.monotonic()
    records = run_jobs(
        variants,
        dict(profile, perspective=perspective),
        seeds,
        policy["max_parallel_runs"],
    )
    stats = aggregate(records, perspective)
    store.save_result(
        job["job_id"],
        {
            "variants": stats,
            "branch_comparison": compare_branches(stats),
            "runs": records,
        },
    )
    store.update_job(
        job["job_id"],
        lifecycle_state="completed",
        governance=_many_runs_record(
            policy,
            job,
            len(records),
            sum(r["event_count"] for r in records),
            time.monotonic() - started,
        ),
        summary={
            **job["summary"],
            "runs": len(records),
            "branches": [v.variant_id for v in variants],
        },
    )
    store.log(job["job_id"], f"completed: {len(variants)} branches x {len(seeds)} runs")


def _replay(
    job: dict[str, Any],
    store: JobStore,
    policy: dict[str, Any],
    scenarios_dir: Path,
    batches_dir: Path,
) -> None:
    """
    Run the original job's request again and compare: same output hash means
    the history replays exactly. The replay frames come from the stored run.
    """
    original = store.get_job(job["request"]["replay"])
    stored = store.get_result(original["job_id"])
    if stored is None or original["request"]["kind"] != "scenario_run":
        raise NotFound(f"job {original['job_id']} is not a run with a result")
    again = run_scenario(
        {**original, "job_id": job["job_id"], "summary": job["summary"]},
        store,
        policy,
        scenarios_dir,
    )
    frames = build_replay_state_at_tick(
        stored["initial_world_state"],
        stored["event_memory"],
        stored["final_world_state"],
    )
    reproduced = (
        again["reproducibility"]["output_hash"]
        == stored["reproducibility"]["output_hash"]
    )
    store.save_result(
        job["job_id"],
        {
            "replay_of": original["job_id"],
            "reproduced": reproduced,
            "original_output_hash": stored["reproducibility"]["output_hash"],
            "replayed_output_hash": again["reproducibility"]["output_hash"],
            "replay": frames,
        },
    )
    store.update_job(original["job_id"], lifecycle_state="replayed")
    store.update_job(
        job["job_id"],
        lifecycle_state="completed",
        governance=again["reproducibility"]["run_metadata"][
            "resource_compute_governance"
        ],
        summary={
            **job["summary"],
            "replay_of": original["job_id"],
            "reproduced": reproduced,
        },
    )
    store.log(
        job["job_id"],
        f"completed: replay of {original['job_id']} reproduced={reproduced}",
    )


def new_job(
    store: JobStore,
    request: dict[str, Any],
    planned: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """The record of an admitted request, saved as created."""
    request = full_request(request)
    stamp = now()
    job = {
        "job_id": store.next_job_id(),
        "request": request,
        "priority": request.get("priority") or policy["run_priority"],
        "lifecycle_state": "created",
        "world_instance": None,
        "governance": None,
        "estimated_cost": planned["estimated_cost"],
        "summary": {"duration_clamped_from": planned["duration_clamped_from"]},
        "error": None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    store.create_job(job)
    store.log(job["job_id"], f"created by {request['source_system']}")
    return job
