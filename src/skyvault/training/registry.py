"""Training data registry = what was exported, from which runs, with which labels.

Important:
JSON Lines, one entry per exported dataset, like the run registry (Phase 8).
dataset_id is derived from the content, so exporting the same runs twice
gives the same id — and records it twice, as two exports of one dataset.
"""

import json
from pathlib import Path
from typing import Any

from ..reproducibility import content_hash


def dataset_id(name: str, files: dict[str, str]) -> str:
    """name plus the first 16 hex digits of the hash of every file's content."""
    return f"{name}-{content_hash(files)[:16]}"


class TrainingRegistry:
    """Append-only list of exported datasets."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def get(self, wanted: str) -> dict[str, Any]:
        """The latest entry for dataset_id wanted. Raises KeyError."""
        for entry in reversed(self.all()):
            if entry["dataset_id"] == wanted:
                return entry
        raise KeyError(f"no dataset {wanted!r} in {self.path}")
