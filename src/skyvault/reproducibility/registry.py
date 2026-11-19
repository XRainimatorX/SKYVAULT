"""Run registry = an append-only log of every run and what it came from."""

import json
from pathlib import Path
from typing import Any


class RunRegistry:
    """
    One JSON object per line, one line per run.

    Important:
    The development plan names a run registry but no store; a JSON Lines file
    is the smallest thing that survives the process and diffs well. Entries
    are only ever appended. A run is found by run_id; runs of the same input
    share an input_hash and should share an output_hash.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, package: dict[str, Any]) -> dict[str, Any]:
        """Append the run behind this result package and return its entry."""
        block = package["reproducibility"]
        verdict = package["evaluation_result"]
        entry = {
            "run_id": block["run_id"],
            "scenario_id": block["scenario_id"],
            "scenario_version": block["scenario_version"],
            "random_seed": block["random_seed"],
            "runtime_version": block["runtime_version"],
            "ruleset_version": block["ruleset_version"],
            "input_hash": block["input_hash"],
            "output_hash": block["output_hash"],
            "started_at": block["run_metadata"]["started_at"],
            "profile_id": verdict["profile_id"],
            "outcome": verdict["winner_or_result"],
            "status": verdict["overall_judgement"]["status"],
            "overall_score": verdict["overall_score"],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        return entry

    def all(self) -> list[dict[str, Any]]:
        """Every recorded run, oldest first. An absent file is an empty registry."""
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    def get(self, run_id: str) -> dict[str, Any]:
        """The run with this id. Raises KeyError when there is none."""
        for entry in self.all():
            if entry["run_id"] == run_id:
                return entry
        raise KeyError(f"Unknown run_id: {run_id}")

    def by_input(self, input_hash: str) -> list[dict[str, Any]]:
        """Every run of this exact input, oldest first."""
        return [entry for entry in self.all() if entry["input_hash"] == input_hash]
