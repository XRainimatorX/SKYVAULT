"""The military / tactical domain pack (development plan Phase 13).

This is not SKYVAULT core: it is the first formal domain pack. It adds
nine profiles, a scenario builder, terrain / suppression / morale rules,
a baseline policy with three doctrines and command delay, mission
outcomes and a state-action-outcome dataset.
"""

from .mission import mission_outcome
from .pack import MILITARY
from .profiles import load_profiles, validate_profiles
from .scenario import build_scenario

__all__ = [
    "MILITARY",
    "build_scenario",
    "load_profiles",
    "mission_outcome",
    "validate_profiles",
]
