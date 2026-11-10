"""Job runner = every (variant, seed) pair run once, in parallel if asked.

Important:
This module sits above the engine. Results always come back in the same
order, variant by variant in request order and seed by seed, however many
workers ran them, so a parallel batch is identical to a sequential one.
"""

import copy
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from ..engine import SkyVaultEngine
from .variants import Variant

Job = tuple[str, str, dict[str, Any], dict[str, Any], int]


def run_jobs(
    variants: list[Variant],
    profile: dict[str, Any],
    seeds: list[int],
    workers: int = 1,
) -> list[dict[str, Any]]:
    """
    Run every variant once per seed and return one record per run.

    workers 1 runs in this process; more uses a process pool. The order of
    the records never depends on which worker finished first.
    """
    jobs: list[Job] = [
        (variant.variant_id, variant.kind, variant.scenario, profile, seed)
        for variant in variants
        for seed in seeds
    ]
    if workers <= 1:
        return [run_job(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(run_job, jobs, chunksize=max(1, len(jobs) // (workers * 4)))
        )


def run_job(job: Job) -> dict[str, Any]:
    """One run, reduced to what a batch compares."""
    variant_id, kind, scenario, profile, seed = job
    seeded = copy.deepcopy(scenario)
    seeded["runtime"]["random_seed"] = seed
    package = SkyVaultEngine(seeded, profile).run()
    verdict = package["evaluation_result"]
    breakdown = package["score_breakdown"]
    return {
        "variant_id": variant_id,
        "kind": kind,
        "scenario_version": scenario["scenario_version"],
        "seed": seed,
        "outcome": verdict["winner_or_result"],
        "status": verdict["overall_judgement"]["status"],
        "score": verdict["overall_score"],
        "hp_lost": breakdown["resource_cost"]["raw"],
        "risk_events": breakdown["risk_growth"]["raw"],
        "event_count": verdict["event_count"],
        "output_hash": package["reproducibility"]["output_hash"],
    }
