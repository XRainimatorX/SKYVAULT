"""Phase 21: SKYVAULT runs on the finished system alone.

Important:
The Phase 0 reference slice (its policy, scenarios and batch) and the
development scripts are tools for building SKYVAULT, not parts of it: no
file SKYVAULT ships or starts from names the slice, and no module in src/
imports or reads anything from tests/ or scripts/.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "skyvault"
WORDS = ("tactical_reference", "TacticalReference")


def shipped_files() -> list[Path]:
    """Every text file SKYVAULT ships or is started from."""
    files = [
        p
        for folder in (REPO_ROOT / "src", REPO_ROOT / "data")
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        # what pip writes on install is not shipped
        and not any(part.endswith(".egg-info") for part in p.parts)
    ]
    for name in ("Dockerfile", "docker-compose.yml", "pyproject.toml"):
        if (REPO_ROOT / name).is_file():
            files.append(REPO_ROOT / name)
    return files


def test_nothing_skyvault_ships_names_the_phase_0_reference_slice():
    named = [
        str(path.relative_to(REPO_ROOT))
        for path in shipped_files()
        if any(
            word in path.read_text(encoding="utf-8", errors="ignore") for word in WORDS
        )
    ]
    assert named == []
    assert len(shipped_files()) > 200  # the scan saw the whole system


def test_the_guard_sees_a_file_that_names_the_slice(tmp_path, monkeypatch):
    planted = REPO_ROOT / "data" / "planted_for_the_guard.json"
    planted.write_text('{"scenario": "tactical_reference_001/v0.1"}', encoding="utf-8")
    try:
        found = [
            path
            for path in shipped_files()
            if "tactical_reference" in path.read_text(encoding="utf-8", errors="ignore")
        ]
        assert found == [planted]
    finally:
        planted.unlink()


def test_no_module_imports_or_reads_tests_or_scripts():
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("tests", "scripts")), path
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(("tests", "scripts")), path
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in ("tests", "scripts"), path
                assert not node.value.startswith(("tests/", "scripts/")), path


def test_the_reference_slice_lives_in_the_tests_alone():
    slice_ = REPO_ROOT / "tests" / "fixtures" / "reference"
    assert (slice_ / "policy.py").is_file()
    assert sorted(
        p.name for p in (slice_ / "scenarios" / "tactical_reference_001").glob("*.json")
    ) == [
        "v0.1-spread.json",
        "v0.1-support-rear.json",
        "v0.1.json",
        "v0.2.json",
    ]
    assert not (REPO_ROOT / "data" / "scenarios" / "tactical_reference_001").exists()
    assert not (SRC / "tactical_reference_policy.py").exists()
