"""The Phase 12 submissions, carried through the world service's jobs synchronously."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from skyvault.interface.systems import KINDS, to_request, to_return
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import execute_job, new_job, plan, scenario_for
from skyvault.worldservice.store import SQLiteStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "external"
SUBMISSIONS = json.loads((FIXTURE / "submissions.json").read_text(encoding="utf-8"))
NAMES = {
    "NEXUS": "nexus_task",
    "STARTX": "startx_branches",
    "TAC_ANGEL": "tac_angel_plan",
    "EIDEN_01": "eiden_intel",
    "AEROGRID": "aerogrid_airspace",
    "SKYFOX": "skyfox_mission",
    "HADES": "hades_defence",
    "CYBERHOUND": "cyberhound_environment",
    "STAR_GUARD": "starguard_equipment",
}


def submission(system: str, **content: Any) -> dict[str, Any]:
    """The fixture's submission for system as an external_submission."""
    raw = copy.deepcopy(SUBMISSIONS[NAMES[system]])
    raw.pop("system")
    scenario = raw.pop("scenario", None)
    raw.update(content)
    return {
        "system": system,
        "kind": KINDS[system],
        "scenario": scenario,
        "content": raw,
    }


def carry_out(sub: dict[str, Any]) -> tuple[dict, list[dict], dict]:
    """(request, results, returned): every job planned, run and read back."""
    store, policy = SQLiteStore(), load_governance()
    request = to_request(sub)
    results = []
    for job_request in request["jobs"]:
        job = new_job(store, job_request, plan(job_request, policy, 0, store), policy)
        execute_job(job["job_id"], store, policy)
        job = store.get_job(job["job_id"])
        assert job["lifecycle_state"] == "completed", job["error"]
        results.append(
            {
                "job": job,
                "result": store.get_result(job["job_id"]),
                "scenario": scenario_for(job["request"]),
            }
        )
    return request, results, to_return(results, sub)


@cache
def fixture_run(system: str) -> tuple[dict, list[dict], dict]:
    """The fixture submission of system, carried out once per test session."""
    return carry_out(submission(system))
