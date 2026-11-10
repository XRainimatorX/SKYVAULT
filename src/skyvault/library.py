"""Library = where SKYVAULT finds a scenario or a batch request by its name.

Important:
SKYVAULT's own data folders (data/scenarios, data/batches) come first; a
deployment adds its own folders with SKYVAULT_SCENARIO_PATH and
SKYVAULT_BATCH_PATH (folders separated by os.pathsep, searched in order).
A name is looked up only where its kind lives and must resolve inside the
folder it is found in, so "../" never reaches anything else.

A caller that names its own folder (a test, a script with --scenarios) is
searched there alone: the library path applies to SKYVAULT's own folders.
"""

import os
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
OWN = {"scenarios": DATA / "scenarios", "batches": DATA / "batches"}
ENVIRONMENT = {"scenarios": "SKYVAULT_SCENARIO_PATH", "batches": "SKYVAULT_BATCH_PATH"}


def folders(kind: str) -> list[Path]:
    """SKYVAULT's own folder for kind, then every folder the environment adds."""
    extra = os.environ.get(ENVIRONMENT[kind], "")
    return [OWN[kind], *(Path(part) for part in extra.split(os.pathsep) if part)]


def search(base: Path) -> list[Path]:
    """The folders a lookup under base searches: the library path for one of
    SKYVAULT's own folders, base alone for any other."""
    for kind, own in OWN.items():
        if base.resolve() == own.resolve():
            return folders(kind)
    return [base]


def find(base: Path, name: str) -> Path | None:
    """The file or folder name under base (see search), or None."""
    for folder in search(base):
        path = (folder / name).resolve()
        if path.is_relative_to(folder.resolve()) and path.exists():
            return path
    return None


def scenario_folder(base: Path, scenario_id: str) -> Path:
    """The folder holding scenario_id's versions (base/scenario_id when none has it)."""
    return find(base, scenario_id) or base / scenario_id
