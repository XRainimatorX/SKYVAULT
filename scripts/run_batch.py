"""Run many plans many times, compare them, and branch conflicting orders.

    python3 scripts/run_batch.py
    python3 scripts/run_batch.py --repeats 10 --workers 2

The batch request (default: data/batches/military_doctrine.json) names
the versions, parameter sweeps and conflicting proposals to run; --repeats
and --workers override its run_policy.repeat_count and workers.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
BATCH_DIR = REPO_ROOT / "data" / "batches"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.batch.aggregate import render_comparative_report
from skyvault.batch.run import run_batch


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run and compare a batch.")
    parser.add_argument(
        "--batch", type=Path, default=BATCH_DIR / "military_doctrine.json"
    )
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)

    with args.batch.open(encoding="utf-8") as file:
        request = json.load(file)
    result = run_batch(request, repeats=args.repeats, workers=args.workers)
    batch_result = result["batch_result"]
    comparison = result["branch_comparison"]
    package = result["conflict_package"]

    output_dir = REPO_ROOT / "output"
    write_json(output_dir / "batch_result.json", batch_result)
    write_json(output_dir / "branch_comparison.json", comparison)
    if package is not None:
        write_json(output_dir / "conflict_package.json", package)
    (output_dir / "comparative_report.md").write_text(
        render_comparative_report(batch_result, comparison, package),
        encoding="utf-8",
    )

    print(f"Batch: {batch_result['batch_id']}")
    print(
        f"Runs: {batch_result['total_runs']} "
        f"({len(batch_result['variants'])} variants × {batch_result['repeat_count']}, "
        f"{batch_result['workers']} workers)"
    )
    print(f"Best mean score: {comparison['best']['mean_score']}")
    if package is not None:
        print(
            f"Conflicts: {len(package['conflicts'])}; branches: "
            + ", ".join(b["branch_id"] for b in package["branch_runs"])
            + "; decision required: "
            + str(package["recommendation_to_nexus"]["required_decision"])
        )
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
