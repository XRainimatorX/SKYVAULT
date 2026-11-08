"""Turn SKYVAULT runs into training data for TAC ANGEL / STARTX.

    python3 scripts/build_training_data.py
    python3 scripts/build_training_data.py --workers 4

Runs every source in the sources file, labels each run for score gaming,
and writes to output/training/: clean_training_dataset, risky_behavior_dataset
and rejected_behavior_dataset (.jsonl and .parquet), anti_gaming_report.json,
branch_evaluation.jsonl and rag_index.json. The export is recorded in
runs/training_registry.jsonl.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.training.export import to_jsonl, write_jsonl, write_parquet
from skyvault.training.pipeline import build_training_data
from skyvault.training.registry import TrainingRegistry, dataset_id

DATASETS = (
    "clean_training_dataset",
    "risky_behavior_dataset",
    "rejected_behavior_dataset",
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build SKYVAULT training data.")
    parser.add_argument(
        "--sources", type=Path, default=REPO_ROOT / "data" / "training" / "sources.json"
    )
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "output" / "training"
    )
    parser.add_argument(
        "--registry", type=Path, default=REPO_ROOT / "runs" / "training_registry.jsonl"
    )
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)

    with args.sources.open(encoding="utf-8") as file:
        sources = json.load(file)
    data = build_training_data(
        sources,
        REPO_ROOT / "data" / "scenarios",
        REPO_ROOT / "data" / "batches",
        workers=args.workers,
    )

    out = args.output
    for name in DATASETS:
        write_jsonl(out / f"{name}.jsonl", data[name])
        write_parquet(out / f"{name}.parquet", data[name])
    write_jsonl(out / "branch_evaluation.jsonl", data["branch_evaluation"])
    for name in ("anti_gaming_report", "rag_index"):
        (out / f"{name}.json").write_text(
            json.dumps(data[name], indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    report = data["anti_gaming_report"]
    contents = {name: to_jsonl(data[name]) for name in DATASETS}
    entry = {
        "dataset_id": dataset_id(sources["dataset"], contents),
        "sources": (
            str(args.sources.relative_to(REPO_ROOT))
            if args.sources.is_relative_to(REPO_ROOT)
            else str(args.sources)
        ),
        "runs": [
            {"input_hash": e["input_hash"], "output_hash": e["output_hash"]}
            for e in report["entries"]
        ],
        "records": {name: len(data[name]) for name in DATASETS},
        "branch_records": len(data["branch_evaluation"]),
        "buckets": report["buckets"],
        "success_types": report["success_types"],
        "label_counts": report["label_counts"],
    }
    TrainingRegistry(args.registry).record(entry)

    print(f"Dataset: {entry['dataset_id']}")
    print(f"Runs: {report['runs']} {report['buckets']}")
    print(f"Success: {report['success_types']}")
    print("Records: " + ", ".join(f"{k} {v}" for k, v in entry["records"].items()))
    print(f"Branch records: {entry['branch_records']}")
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
