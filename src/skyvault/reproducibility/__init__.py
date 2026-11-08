"""
Reproducibility = proof that a run can be repeated, and of what it came from
(Formal Spec sections 11 and 12).

Important:
hashing and versioning only read data; neither imports the engine. Rerunning
a package to check it lives in skyvault.verification, which does.
"""

from .hashing import canonical_json, content_hash, input_hash, output_hash
from .versioning import (
    CHANGE_CATEGORIES,
    RUNTIME_VERSION,
    compare_runs,
    compare_scenarios,
    ruleset_version,
    seed_policy,
)

__all__ = [
    "CHANGE_CATEGORIES",
    "RUNTIME_VERSION",
    "canonical_json",
    "compare_runs",
    "compare_scenarios",
    "content_hash",
    "input_hash",
    "output_hash",
    "ruleset_version",
    "seed_policy",
]
