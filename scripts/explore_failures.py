"""Deliberately stress a plan and write where, why and how it fails.

    python3 scripts/explore_failures.py
    python3 scripts/explore_failures.py --repeats 3

The plan is a scenario (default: military_urban_001 v0.2) judged under an
evaluation profile (default: balanced). The stress request is the scenario's
own failure_exploration block; --repeats overrides its repeat_count.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_failure_map
from skyvault.failure import (
    build_collapse_sequence,
    build_failure_map,
    build_survival_conditions,
    explore_failures,
    render_recommended_modifications,
)
from skyvault.scenario_loader import (
    default_evaluation_profile,
    load_evaluation_profile,
    load_scenario,
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Explore how a plan fails.")
    parser.add_argument(
        "--scenario",
        type=Path,
        default=SCENARIO_DIR / "military_urban_001" / "v0.2.json",
    )
    parser.add_argument("--profile", type=Path, default=None)
    parser.add_argument("--repeats", type=int, default=None)
    args = parser.parse_args(argv)

    scenario = load_scenario(args.scenario)
    profile = (
        load_evaluation_profile(args.profile)
        if args.profile
        else default_evaluation_profile(scenario)
    )
    request = copy.deepcopy(scenario["failure_exploration"])
    if args.repeats is not None:
        request["run_policy"]["repeat_count"] = args.repeats

    exploration = explore_failures(scenario, profile, request)
    failure_map = validate_failure_map(build_failure_map(exploration))
    conditions = build_survival_conditions(failure_map)

    output_dir = REPO_ROOT / "output"
    write_json(output_dir / "failure_map.json", failure_map)
    write_json(
        output_dir / "collapse_sequence.json", build_collapse_sequence(exploration)
    )
    write_json(output_dir / "survival_conditions.json", conditions)
    (output_dir / "recommended_modifications.md").write_text(
        render_recommended_modifications(failure_map, conditions), encoding="utf-8"
    )

    baseline = failure_map["baseline"]
    print(f"Plan: {failure_map['scenario_id']} {failure_map['scenario_version']}")
    print(f"Runs per stressed plan: {failure_map['repeat_count']}")
    print(f"Survives without stress: {baseline['survival_rate']:.0%}")
    print(f"Crushed by: {failure_map['crushing_variable']}")
    print(f"Best alternative: {failure_map['best_alternative']}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
