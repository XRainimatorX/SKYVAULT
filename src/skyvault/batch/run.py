"""Run a batch = build its variants, run them, aggregate and compare.

Important:
This module sits above the engine, with runner. It turns a validated batch
request into the three batch outputs; conflicting proposals, when present,
become branches here and are summarised in a conflict package.
"""

import copy
from pathlib import Path
from typing import Any

from ..contracts import (
    validate_batch_result,
    validate_batch_spec,
    validate_conflict_package,
)
from ..scenario_loader import (
    PROFILE_DIR,
    load_evaluation_profile,
    load_scenario,
    scenario_perspective,
)
from ..verification import SCENARIO_DIR
from .aggregate import aggregate, compare_branches
from .conflicts import (
    branch_id,
    build_conflict_package,
    compatible_sets,
    detect_conflicts,
)
from .runner import run_jobs
from .variants import Variant, branch_variant, build_variants


def run_batch(
    batch: dict[str, Any],
    scenarios_dir: Path = SCENARIO_DIR,
    profile_dir: Path = PROFILE_DIR,
    repeats: int | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """
    Every variant the request names, repeat_count runs each, compared.

    repeats and workers override the request's. Returns batch_result,
    branch_comparison and conflict_package (None without conflicts).
    """
    request = _with_defaults(validate_batch_spec(batch))
    if repeats is not None:
        request["run_policy"]["repeat_count"] = repeats
    if workers is not None:
        request["workers"] = workers

    base = load_scenario(
        scenarios_dir / request["scenario_id"] / f"{request['base_version']}.json"
    )
    profile = load_evaluation_profile(profile_dir / f"{request['profile']}.json")
    perspective = (
        request["perspective"] or profile["perspective"] or scenario_perspective(base)
    )
    if perspective is None:
        raise ValueError("the batch has no perspective to compare runs from")
    profile["perspective"] = perspective
    seeds = _seeds(base, request)

    variants = planned_variants(request, base, scenarios_dir)
    proposals = (request["conflicts"] or {}).get("proposals", [])
    conflicts = detect_conflicts(base, proposals)
    sets = compatible_sets(proposals, conflicts)
    records = run_jobs(variants, profile, seeds, request["workers"])
    stats = aggregate(records, perspective) if records else []

    batch_result = validate_batch_result(
        {
            "batch_id": request["batch_id"],
            "scenario_id": request["scenario_id"],
            "base_version": request["base_version"],
            "profile_id": profile["profile_id"],
            "perspective": perspective,
            "repeat_count": request["run_policy"]["repeat_count"],
            "seeds": seeds,
            "workers": request["workers"],
            "total_runs": len(records),
            "variants": stats,
            "runs": records,
        }
    )
    package = None
    if request["conflicts"] is not None:
        by_variant = {entry["variant_id"]: entry for entry in stats}
        package = validate_conflict_package(
            build_conflict_package(
                base,
                proposals,
                conflicts,
                [by_variant[f"branch:{branch_id(chosen)}"] for chosen in sets],
                by_variant["branch:none"],
            )
        )
    return {
        "batch_result": batch_result,
        "branch_comparison": compare_branches(stats),
        "conflict_package": package,
    }


def planned_variants(
    request: dict[str, Any], base: dict[str, Any], scenarios_dir: Path = SCENARIO_DIR
) -> list[Variant]:
    """
    Every variant a batch runs: its versions and sweep points, then one branch
    per compatible set of proposals and the baseline with none. The world
    service counts a batch's runs with this, so the count cannot drift from
    what run_batch does.
    """
    request = _with_defaults(validate_batch_spec(request))
    variants: list[Variant] = build_variants(request, scenarios_dir)
    if request["conflicts"] is not None:
        proposals = request["conflicts"]["proposals"]
        sets = compatible_sets(proposals, detect_conflicts(base, proposals))
        by_id = {p["proposal_id"]: p for p in proposals}
        for chosen in [*sets, []]:
            variants.append(
                branch_variant(base, branch_id(chosen), [by_id[p] for p in chosen])
            )
    return variants


def _with_defaults(request: dict[str, Any]) -> dict[str, Any]:
    """
    The request with every optional field present.

    Important:
    Contract validation returns only supplied fields (Phase 9 postmortem,
    change 1), so the defaults are restated where the request is read.
    """
    filled = copy.deepcopy(request)
    filled.setdefault("description", "")
    filled.setdefault("perspective", None)
    filled.setdefault("workers", 1)
    filled.setdefault("variants", [])
    filled.setdefault("sweeps", [])
    filled.setdefault("conflicts", None)
    return filled


def _seeds(base: dict[str, Any], request: dict[str, Any]) -> list[int]:
    seed = int(base["runtime"]["random_seed"])
    count = request["run_policy"]["repeat_count"]
    if request["run_policy"]["random_seed_policy"] == "fixed":
        return [seed] * count
    return [seed + offset for offset in range(count)]
