"""
Observation = what each outside system sees of the world (development plan Phase 5).

Important:
Pure functions over snapshots of units, tick by tick. Nothing here runs a
simulation or imports the engine: the engine hands its history in, and a
finished run's history is rebuilt from its result package.
"""

from .history import (
    available_actions,
    concealment_for,
    context_for,
    history_from_package,
    observations_for_run,
)
from .observe import observe
from .profiles import OBSERVER_DIR, OBSERVERS, load_observer_profile
from .sensing import grid_distance, visible_contacts

__all__ = [
    "OBSERVERS",
    "OBSERVER_DIR",
    "available_actions",
    "concealment_for",
    "context_for",
    "grid_distance",
    "history_from_package",
    "load_observer_profile",
    "observations_for_run",
    "observe",
    "visible_contacts",
]
