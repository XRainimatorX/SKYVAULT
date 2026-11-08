"""Sensing = which enemy units a side sees, and how sure it is (pure)."""

from collections.abc import Callable
from typing import Any

Concealment = Callable[[Any], float] | None


def grid_distance(space: dict[str, Any] | None, a: Any, b: Any) -> float:
    """
    Distance between two grid cells under the space's distance model.

    Important:
    The same three models as the runtime's grid (chebyshev by default).
    Observation is only defined on grids, as the tactical engine is.
    """
    model = (space or {}).get("distance_model") or "chebyshev"
    if (space or {}).get("type", "grid") != "grid":
        raise ValueError("observation needs a grid space")
    ax, ay = a
    bx, by = b
    if model == "manhattan":
        return float(abs(ax - bx) + abs(ay - by))
    if model == "euclidean_floor":
        return float(int(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5))
    return float(max(abs(ax - bx), abs(ay - by)))


def sensor_range(unit: dict[str, Any], profile: dict[str, Any]) -> float:
    """A unit's sensor_range capability, else the profile's default."""
    return float(
        unit["capabilities"].get("sensor_range", profile["default_sensor_range"])
    )


def is_active(unit: dict[str, Any]) -> bool:
    return bool(unit["state"].get("status", "active") == "active")


def visible_contacts(
    units: dict[str, Any],
    faction: str,
    profile: dict[str, Any],
    concealment: Concealment,
    space: dict[str, Any] | None = None,
) -> dict[str, float]:
    """
    {enemy id: confidence} for every enemy faction's living sensors see.

    Important:
    A living own unit sees an enemy (living or a wreck) within its sensor
    range × (1 − concealment of the enemy's cell). Confidence is
    1 − 0.5 × distance / that range, the best among the units that see it,
    to four places. Concealment comes from the domain pack; none means 0.
    """
    sensors = [
        unit
        for unit in units.values()
        if unit["faction"] == faction and is_active(unit) and unit["position"]
    ]
    seen: dict[str, float] = {}
    for target in units.values():
        if target["faction"] == faction or target["position"] is None:
            continue
        hidden = concealment(target["position"]) if concealment else 0.0
        for sensor in sensors:
            reach = sensor_range(sensor, profile) * (1.0 - hidden)
            distance = grid_distance(space, sensor["position"], target["position"])
            if distance > reach:
                continue
            confidence = round(1.0 - 0.5 * distance / reach, 4) if reach else 1.0
            entity_id = target["entity_id"]
            seen[entity_id] = max(seen.get(entity_id, 0.0), confidence)
    return dict(sorted(seen.items()))
