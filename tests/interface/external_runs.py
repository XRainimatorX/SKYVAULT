"""The Phase 12 submissions, carried through the world service's jobs synchronously."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from skyvault.interface.api import run_submission
from skyvault.interface.systems import KINDS
from skyvault.worldservice.governance import load_governance
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
    done = run_submission(sub, SQLiteStore(), load_governance())
    return done["request"], done["results"], done["returned"]


@cache
def fixture_run(system: str) -> tuple[dict, list[dict], dict]:
    """The fixture submission of system, carried out once per test session."""
    return carry_out(submission(system))
