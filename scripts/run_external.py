"""Carry every outside system's fixture submission through SKYVAULT (Phase 12).

    python3 scripts/run_external.py

Writes output/external/: what each of the nine systems gets back
(<system>.json, NEXUS's briefing as nexus_briefing.md), and a conflict in a
running world — the conflict package, its authority handoff and the record
once NEXUS has decided (conflict_*.json; this script stands in for NEXUS
and keeps the first branch by name). Everything runs here, on an
in-memory store, under the default governance; nothing is decided by
SKYVAULT.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.interface.api import run_submission  # noqa: E402
from skyvault.interface.systems import KINDS  # noqa: E402
from skyvault.worldservice.governance import load_governance  # noqa: E402
from skyvault.worldservice.jobs import full_request, new_job, plan  # noqa: E402
from skyvault.worldservice.store import SQLiteStore  # noqa: E402
from skyvault.worldservice.worlds import PersistentWorld  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "external" / "submissions.json"
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


def submission(raw: dict) -> dict:
    """A fixture entry as an external_submission."""
    content = copy.deepcopy(raw)
    system = content.pop("system")
    return {
        "system": system,
        "kind": KINDS[system],
        "scenario": content.pop("scenario", None),
        "content": content,
    }


def write(folder: Path, name: str, data: object) -> None:
    (folder / name).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def conflict(fixtures: dict, policy: dict, folder: Path) -> str:
    """The fixture's conflicting actions in a running world, decided by NEXUS."""
    store = SQLiteStore()
    request = {"kind": "persistent_world", "scenario": "tactical_reference_001/v0.1"}
    job = new_job(store, request, plan(request, policy, 0, store), policy)
    world = PersistentWorld(job["job_id"], full_request(request), policy, store)
    for action in fixtures["conflicting_actions"]:
        order = {
            k: v for k, v in action.items() if k not in ("system", "tick", "actor_id")
        }
        world.submit(action["system"], action["tick"], action["actor_id"], order)
    held = world.advance(5)
    record = store.get_conflict(held["awaiting_decision"])
    write(folder, "conflict_package.json", record["conflict_package"])
    write(folder, "conflict_handoff.json", record["handoff"])
    branch = sorted(record["branches"])[0]
    decided = world.decide(record["conflict_id"], branch, "NEXUS")
    world.advance(1)
    write(
        folder,
        "conflict_decided.json",
        {k: v for k, v in decided.items() if k not in ("conflict_package",)},
    )
    world.finish()
    return f"{record['conflict_id']} at tick {record['tick']}: NEXUS kept {branch}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "external"))
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads(FIXTURE.read_text(encoding="utf-8"))
    policy = load_governance()

    for system, name in NAMES.items():
        done = run_submission(submission(fixtures[name]), SQLiteStore(), policy)
        returned = done["returned"]
        if returned.get("briefing"):
            (folder / "nexus_briefing.md").write_text(returned["briefing"], "utf-8")
        write(folder, f"{system.lower()}.json", returned)
        runs = len(done["request"]["jobs"])
        state = "supported" if returned["supported"] else "not supported"
        print(f"{system:<11} {runs} job(s), {state}, {len(returned['gaps'])} gap(s)")
    print("conflict   ", conflict(fixtures, policy, folder))
    print(f"wrote {folder}")


if __name__ == "__main__":
    main()
