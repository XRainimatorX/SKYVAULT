"""Write what every observer saw of one run, tick by tick.

    python3 scripts/observe_run.py
    python3 scripts/observe_run.py \
        --scenario data/scenarios/military_urban_001/v0.1.json --faction BLUE

Runs the scenario and writes output/observations/<observer>.json for the
five observers of data/observers/ (TAC_ANGEL, STARTX, NEXUS, HADES,
AEROGRID), all from the same side. The local and threat views follow one
unit: --actor, else the side's first unit in scenario order.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
REFERENCE = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultEngine
from skyvault.observation import OBSERVERS, load_observer_profile, observations_for_run
from skyvault.scenario_loader import load_scenario, scenario_perspective


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Observe a run as each system.")
    parser.add_argument("--scenario", type=Path, default=REFERENCE)
    parser.add_argument("--faction", default=None, help="default: the perspective")
    parser.add_argument("--actor", default=None, help="default: the side's first")
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "output" / "observations"
    )
    args = parser.parse_args(argv)

    scenario = load_scenario(args.scenario)
    faction = args.faction or scenario_perspective(scenario)
    side = [e["entity_id"] for e in scenario["entities"] if e["faction"] == faction]
    if not side:
        raise SystemExit(f"no unit of faction {faction!r} in the scenario")
    actor = args.actor or side[0]
    package = SkyVaultEngine(scenario).run()

    args.output.mkdir(parents=True, exist_ok=True)
    viewpoint = {"faction": faction, "actor_id": actor}
    for observer in OBSERVERS:
        observations = observations_for_run(
            package, scenario, load_observer_profile(observer), viewpoint
        )
        document = {
            "observer_id": observer,
            "scenario_id": package["scenario_id"],
            "scenario_version": package["scenario_version"],
            "output_hash": package["reproducibility"]["output_hash"],
            "viewpoint": viewpoint,
            "observations": observations,
        }
        path = args.output / f"{observer}.json"
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        hidden = sum(1 for o in observations if o["hidden_state"]["exists"])
        print(
            f"{observer}: {len(observations)} observations, "
            f"{hidden} with hidden state → {path}"
        )


if __name__ == "__main__":
    main()
