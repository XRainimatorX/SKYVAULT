"""Workspace = the folder of run outputs the UI and the briefing read.

Important:
Reading only. The result package is required; the failure exploration and
batch outputs are optional and come back as None when they were not written.
Nothing is simulated here.
"""

import json
from pathlib import Path
from typing import Any

# key -> file name; the result package is the only required one
JSON_FILES = {
    "result_package": "result_package.json",
    "failure_map": "failure_map.json",
    "collapse_sequence": "collapse_sequence.json",
    "survival_conditions": "survival_conditions.json",
    "batch_result": "batch_result.json",
    "branch_comparison": "branch_comparison.json",
    "conflict_package": "conflict_package.json",
}
TEXT_FILES = {
    "recommended_modifications": "recommended_modifications.md",
    "comparative_report": "comparative_report.md",
}


def load_workspace(directory: Path) -> dict[str, Any]:
    """
    Every output in directory, keyed as in JSON_FILES and TEXT_FILES.

    Raises FileNotFoundError when result_package.json is missing: without it
    there is no run to show. Every other missing file is None.
    """
    directory = Path(directory)
    package_path = directory / JSON_FILES["result_package"]
    if not package_path.is_file():
        raise FileNotFoundError(f"no result package in {directory}")

    workspace: dict[str, Any] = {}
    for key, name in JSON_FILES.items():
        path = directory / name
        if path.is_file():
            with path.open(encoding="utf-8") as file:
                workspace[key] = json.load(file)
        else:
            workspace[key] = None
    for key, name in TEXT_FILES.items():
        path = directory / name
        workspace[key] = path.read_text(encoding="utf-8") if path.is_file() else None
    return workspace
