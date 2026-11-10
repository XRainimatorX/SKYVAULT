"""
Failure exploration = deliberately make a plan fail, to find what to fix
before acting (Formal Spec section 14).

Important:
variables and analysis never import the engine; explore does, to run the
stressed plans. Nothing below the engine imports this package.
"""

from .analysis import (
    build_collapse_sequence,
    build_failure_map,
    build_survival_conditions,
    render_recommended_modifications,
)
from .explore import explore_failures
from .variables import FAILURE_VARIABLES, STRESS_LEVELS, FailureVariable, apply_stress

__all__ = [
    "FAILURE_VARIABLES",
    "STRESS_LEVELS",
    "FailureVariable",
    "apply_stress",
    "build_collapse_sequence",
    "build_failure_map",
    "build_survival_conditions",
    "explore_failures",
    "render_recommended_modifications",
]
