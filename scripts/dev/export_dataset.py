"""Export a state-action-outcome dataset from the military reference scenarios.

    python3 scripts/dev/export_dataset.py
    python3 scripts/dev/export_dataset.py --runs 5 \
        --scenario data/scenarios/military_squad_001/v0.1.json

Runs every scenario --runs times (seeds from the scenario's own, one up per
run) and writes one JSON line per decision to output/tac_angel_dataset.jsonl,
in scenario, run and event order.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.domains.military.dataset import build_dataset
from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario

REFERENCE = [
    SCENARIO_DIR / f"military_{name}_001" / "v0.1.json"
    for name in ("squad", "urban", "mountain", "junction")
]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export a TAC ANGEL dataset.")
    parser.add_argument("--scenario", type=Path, action="append", default=None)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "output" / "tac_angel_dataset.jsonl"
    )
    args = parser.parse_args(argv)

    lines = []
    for path in args.scenario or REFERENCE:
        scenario = load_scenario(path)
        for run in range(args.runs):
            seeded = copy.deepcopy(scenario)
            seeded["runtime"]["random_seed"] = scenario["runtime"]["random_seed"] + run
            package = SkyVaultEngine(seeded).run()
            records = build_dataset(package, seeded)
            lines += [
                json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records
            ]
            print(
                f"{scenario['scenario_id']} seed {seeded['runtime']['random_seed']}: "
                f"{len(records)} decisions"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Records: {len(lines)}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
