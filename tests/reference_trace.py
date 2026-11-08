"""The reference run reduced to what must never change by accident.

Important:
trace() keeps, per event, the time, type, actor, target and data. digest()
hashes the whole result package after replacing every event or action id with
its order of first appearance. Ids were uuid4 until Phase 8 and are a per-run
counter since; the renumbering makes both hash the same, so the digest pins
behaviour across that change.

If a phase changes the simulation on purpose, regenerate the committed file
and record old and new numbers in that phase's completion report:

    python3 tests/reference_trace.py > tests/fixtures/reference_trace.json
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

ID_PATTERN = re.compile(r"(event|action)_[0-9a-f]{10}")


def trace(package: dict[str, Any]) -> list[list[Any]]:
    return [
        [
            event["time"],
            event["event_type"],
            event["source"]["actor_id"],
            event["target_entity_id"],
            event["data"],
        ]
        for event in package["event_memory"]
    ]


def digest(package: dict[str, Any]) -> str:
    # The reproducibility block records when the run happened; leave it out
    produced = {
        key: value for key, value in package.items() if key != "reproducibility"
    }
    text = json.dumps(produced, sort_keys=True)
    seen: dict[str, str] = {}

    def number(match: re.Match[str]) -> str:
        return seen.setdefault(match.group(0), f"{match.group(1)}_{len(seen):04d}")

    return hashlib.sha256(ID_PATTERN.sub(number, text).encode()).hexdigest()


def reference_package() -> dict[str, Any]:
    from skyvault.engine import SkyVaultTacticalReferenceEngine
    from skyvault.scenario_loader import load_scenario

    scenario = load_scenario(
        REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"
    )
    return SkyVaultTacticalReferenceEngine(scenario).run()


if __name__ == "__main__":
    package = reference_package()
    print(json.dumps({"digest": digest(package), "trace": trace(package)}, indent=1))
