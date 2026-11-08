"""Run the airspace scenario, HADES behaviours and AEROGRID configurations.

    python3 scripts/run_airspace.py

Writes output/airspace/: the reference run's detection gap, response times
and failure points (outcome_<scenario>.json), the comparison of HADES rules
of engagement (behaviors.json) and of AEROGRID sensor configurations
(configs.json), all through the same submissions the external interface
takes, and airspace_report.md for a person to read.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.domains.airspace.pack import AIRSPACE  # noqa: E402
from skyvault.domains.airspace.report import airspace_report  # noqa: E402
from skyvault.engine import SkyVaultTacticalReferenceEngine  # noqa: E402
from skyvault.interface.api import run_submission  # noqa: E402
from skyvault.scenario_loader import load_scenario  # noqa: E402
from skyvault.worldservice.governance import load_governance  # noqa: E402
from skyvault.worldservice.store import SQLiteStore  # noqa: E402

NAME = "airspace_defence_001"
BEHAVIORS = {
    "baseline": {},
    "salvo 2": {"salvo": 2},
    "first tracked": {"priority": "first_tracked"},
    "close in (engage_at 0.5)": {"engage_at": 0.5},
    "hold fire below 0.6": {"hold_fire_below": 0.6},
}
CONFIGS = {
    "as built": {},
    "spare radar west": {"radar_spare": {"position": [5, 10], "online": True}},
    "spare radar east": {"radar_spare": {"position": [16, 4], "online": True}},
    "south radar off": {"radar_south": {"online": False}},
}


def write(folder: Path, name: str, data: object) -> None:
    (folder / name).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def compare(system: str, kind: str, key: str, options: dict, runs: int) -> dict:
    """Each option submitted as that system would, over the same seeds."""
    rows = {}
    for label, option in options.items():
        returned = run_submission(
            {
                "system": system,
                "kind": kind,
                "scenario": f"{NAME}/v0.1",
                "content": {key: option, "repeat_count": runs},
            },
            SQLiteStore(),
            load_governance(),
        )["returned"]
        summary = returned["airspace"]
        rows[label] = {k: v for k, v in summary.items() if k != "runs"}
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "airspace"))
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)

    scenario = load_scenario(REPO_ROOT / "data" / "scenarios" / NAME / "v0.1.json")
    package = SkyVaultTacticalReferenceEngine(scenario).run()
    outcome = AIRSPACE.airspace_outcome(package, scenario)
    write(folder, f"outcome_{NAME}.json", outcome)
    print(
        f"{NAME}: {outcome['outcome']}, {outcome['leaks']} leak(s), "
        f"{outcome['detection_gap']['uncovered_share']:.0%} uncovered, "
        f"reaction {outcome['response_time']['mean_reaction'] or 0:.1f} ticks"
    )

    behaviors = compare("HADES", "defence", "behavior", BEHAVIORS, args.runs)
    configs = compare("AEROGRID", "airspace", "sensors", CONFIGS, args.runs)
    write(folder, "behaviors.json", behaviors)
    write(folder, "configs.json", configs)
    for label, row in {**behaviors, **configs}.items():
        print(
            f"{label:<26} defended {row['defended_rate']:.0%}, "
            f"leaks {row['mean_leaks']:.1f}"
        )

    summary = {
        "scenario": NAME,
        "seed": int(scenario["runtime"]["random_seed"]),
        "runs": args.runs,
        "reference": outcome,
        "behaviors": behaviors,
        "configs": configs,
    }
    (folder / "airspace_report.md").write_text(airspace_report(summary), "utf-8")
    print(f"wrote {folder}")


if __name__ == "__main__":
    main()
