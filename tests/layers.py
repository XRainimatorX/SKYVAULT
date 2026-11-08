"""The layers of src/skyvault, as one positive list the layering tests share.

Important:
Phase 19 change 3: every "the core imports no X" test used to name the
folders it skipped, so a new upper layer had to be added to each of them.
Here each top-level package of src/skyvault has a rank; a module may import
from its own rank or below, never above. Anything not named is core
(rank 0), so a new package is checked from the day it is added.

Not a conftest.py (see tests/worldservice/service_fixtures.py): tests load
it by putting tests/ on sys.path.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "skyvault"

RANK = {
    "domains": 1,
    "virtualtest": 2,
    "interface": 3,
    "worldservice": 3,
    "editions": 4,
    "acceptance": 5,
}


def layer_of(path: Path) -> str:
    """The layer a source file belongs to: its top-level package, or core."""
    parts = path.relative_to(SRC).parts
    return parts[0] if len(parts) > 1 and parts[0] in RANK else "core"


def rank(layer: str) -> int:
    return RANK.get(layer, 0)


def modules_below(layer: str) -> list[Path]:
    """Every source file that must not import from layer (all of lower rank)."""
    return sorted(
        path for path in SRC.rglob("*.py") if rank(layer_of(path)) < rank(layer)
    )


def imported(path: Path) -> set[str]:
    """The modules a file imports from (`from X import` and `import X`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    found |= {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    return found
