"""A surrogate model: a few tactical runs fitted, so nearby designs need none.

Important:
The tactical test runs whole scenarios; asking it about every redesign is
slow. The surrogate samples a handful of variants around the profile — each
of mass, power_requirement and energy_capacity × 0.8 and × 1.2, plus the
profile itself — runs the tactical test on them, and fits the mean change
in score against the baseline by least squares (numpy) on those three
parameters, each divided by the profile's own value.

It reports how well it fits (r²) and the range it was fitted on; a
prediction outside that range comes back marked out_of_range, because a
linear fit says nothing there.
"""

from collections.abc import Callable
from typing import Any

import numpy as np

from .profile import physical, with_param

FEATURES = ("mass", "power_requirement", "energy_capacity")
STEPS = (0.8, 1.2)
# the edge of the fitted range still counts as inside it
TOLERANCE = 1e-4


def variants(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """The profile and one variant per feature and step (features it gives only)."""
    found = [profile]
    for feature in FEATURES:
        value = physical(profile, feature)
        if not value:
            continue
        for step in STEPS:
            found.append(
                with_param(
                    profile, "physical_parameters", feature, round(value * step, 6)
                )
            )
    return found


def _features(profile: dict[str, Any], reference: dict[str, Any]) -> list[float]:
    row = []
    for feature in FEATURES:
        base = physical(reference, feature)
        value = physical(profile, feature)
        row.append(1.0 if not base or value is None else value / base)
    return row


def fit(
    profile: dict[str, Any],
    measure: Callable[[dict[str, Any]], float],
) -> dict[str, Any]:
    """
    {features, coefficients, intercept, r2, samples, range}: measure(variant)
    is the tactical value to model (the mean Δscore); it is called once per
    variant.
    """
    samples = variants(profile)
    x = np.array([_features(v, profile) for v in samples], dtype=float)
    y = np.array([float(measure(v)) for v in samples], dtype=float)
    design = np.hstack([np.ones((len(samples), 1)), x])
    solution, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ solution
    spread = float(np.sum((y - y.mean()) ** 2))
    residual = float(np.sum((y - predicted) ** 2))
    # a measure that never moves is fitted exactly by its mean
    r2 = 1.0 if spread < 1e-12 else 1 - residual / spread
    return {
        "features": list(FEATURES),
        "intercept": round(float(solution[0]), 6),
        "coefficients": [round(float(c), 6) for c in solution[1:]],
        "r2": round(r2, 4),
        "samples": [
            {"x": [round(float(v), 4) for v in row], "y": round(float(target), 6)}
            for row, target in zip(x, y, strict=True)
        ],
        "range": [
            [round(float(x[:, i].min()), 4), round(float(x[:, i].max()), 4)]
            for i in range(len(FEATURES))
        ],
        "reference": {f: physical(profile, f) for f in FEATURES},
    }


def predict(model: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """{value, out_of_range}: the fitted value for another profile."""
    row = []
    for feature in model["features"]:
        base = model["reference"][feature]
        value = physical(profile, feature)
        row.append(1.0 if not base or value is None else value / base)
    value = model["intercept"] + sum(
        c * v for c, v in zip(model["coefficients"], row, strict=True)
    )
    outside = any(
        not low - TOLERANCE <= v <= high + TOLERANCE
        for v, (low, high) in zip(row, model["range"], strict=True)
    )
    return {"value": round(value, 6), "out_of_range": outside}
