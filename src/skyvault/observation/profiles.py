"""Observer profiles = how each outside system looks at the world (data/observers/)."""

import json
from pathlib import Path
from typing import Any

from ..contracts import ObserverProfile, validate_observer_profile

OBSERVER_DIR = Path(__file__).resolve().parents[3] / "data" / "observers"

# The systems of the development plan's Phase 5, by observer_id
OBSERVERS = ("TAC_ANGEL", "STARTX", "NEXUS", "HADES", "AEROGRID")


def load_observer_profile(name_or_path: str | Path) -> dict[str, Any]:
    """
    An observer profile by observer id (data/observers/<id>.json) or by path.

    Important:
    The profile passes the observer_profile contract and comes back with
    every default filled in, so callers never guess a missing field.
    """
    path = Path(name_or_path)
    if path.suffix != ".json":
        path = OBSERVER_DIR / f"{str(name_or_path).lower()}.json"
    if not path.exists():
        raise FileNotFoundError(f"observer profile not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_observer_profile(data)
    return ObserverProfile.model_validate(data).model_dump(mode="json")
