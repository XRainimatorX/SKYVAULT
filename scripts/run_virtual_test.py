"""Run every committed equipment profile through the virtual test.

    python3 scripts/run_virtual_test.py

Writes output/virtual_test/: one equipment_test_result per profile
(<equipment_id>.json, Formal Spec section 18) and virtual_test_report.md for
a person to read. --surrogate also fits the surrogate model for each
profile; --seeds sets how many seeds each military scenario runs.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.virtualtest.profile import load_rules, reference_profiles  # noqa: E402
from skyvault.virtualtest.report import virtual_test_report  # noqa: E402
from skyvault.virtualtest.run import virtual_test  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "virtual_test"))
    parser.add_argument("--seeds", type=int, default=None)
    parser.add_argument("--surrogate", action="store_true")
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)

    rules = load_rules()
    seeds = rules["tactical"]["seeds"][: args.seeds] if args.seeds else None
    results = []
    for equipment_id, profile in reference_profiles().items():
        result = virtual_test(profile, rules, seeds=seeds, surrogate=args.surrogate)
        results.append(result)
        (folder / f"{equipment_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        judgement = result["final_judgement"]
        print(
            f"{equipment_id:<14} physical {result['physical_possibility']['score']:.2f}"
            f"  engineering {result['engineering_feasibility']['score']:.2f}"
            f"  → {judgement['status']}"
        )
    (folder / "virtual_test_report.md").write_text(
        virtual_test_report(results), encoding="utf-8"
    )
    print(f"wrote {folder}")


if __name__ == "__main__":
    main()
