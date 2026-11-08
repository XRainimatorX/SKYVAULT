"""Rerun a recorded result package and check it reproduces.

    python3 scripts/verify_run.py output/result_package.json

The scenario and profile are found from the package itself (its scenario_id,
scenario_version and profile_id). Exits 0 when the rerun reproduces the
recorded output hash, 1 when it does not.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.verification import locate_inputs, verify_reproducibility


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rerun a result package.")
    parser.add_argument("package", type=Path, help="result_package.json to verify")
    args = parser.parse_args(argv)

    with args.package.open(encoding="utf-8") as file:
        package = json.load(file)

    scenario, profile = locate_inputs(package)
    report = verify_reproducibility(package, scenario, profile)

    block = package["reproducibility"]
    print(f"Run: {block['run_id']}")
    print(f"Scenario: {block['scenario_id']} {block['scenario_version']}")
    print(f"Recorded output: {report['recorded_output_hash']}")
    print(f"Rerun output:    {report['actual_output_hash']}")
    print(f"Reproduced: {'yes' if report['reproduced'] else 'no'}")
    return 0 if report["reproduced"] else 1


if __name__ == "__main__":
    sys.exit(main())
