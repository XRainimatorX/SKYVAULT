"""The airspace model as pure functions: flight, detection, engagement windows.

Important:
Nothing here touches a world or draws a random number: the handlers draw,
and ask these what the odds are. Distances are Chebyshev on the 2D grid
(the airspace is 2D first; altitude is an attribute, low or medium).
"""

from typing import Any

Cell = tuple[int, int]


def distance(a: Any, b: Any) -> int:
    """Chebyshev distance between two cells."""
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def step_toward(position: Any, target: Any, speed: int) -> list[int]:
    """
    Where something flying straight at target is after one tick: up to
    speed cells, each step one cell in x and/or y towards it.
    """
    x, y = int(position[0]), int(position[1])
    tx, ty = int(target[0]), int(target[1])
    for _ in range(max(0, int(speed))):
        if (x, y) == (tx, ty):
            break
        x += (tx > x) - (tx < x)
        y += (ty > y) - (ty < y)
    return [x, y]


def detection_probability(
    sensor: dict[str, Any], target: Any, altitude: str, falloff: float = 0.5
) -> float:
    """
    The chance a sensor sees a target this tick.

    sensor: {at, range, detection, low_altitude}. Zero beyond range;
    within it detection × (1 − falloff · d / range) — the shape of Phase 5's
    confidence — times low_altitude for a low flyer.
    """
    reach = float(sensor["range"])
    d = distance(sensor["at"], target)
    if reach <= 0 or d > reach:
        return 0.0
    p = float(sensor["detection"]) * (1 - falloff * d / reach)
    if altitude == "low":
        p *= float(sensor["low_altitude"])
    return round(max(0.0, min(1.0, p)), 6)


def covered(sensors: list[dict[str, Any]], size: Any) -> set[Cell]:
    """The cells inside at least one sensor's range."""
    width, height = int(size[0]), int(size[1])
    return {
        (x, y)
        for x in range(width)
        for y in range(height)
        if any(distance(s["at"], (x, y)) <= float(s["range"]) for s in sensors)
    }


def interception_window(
    path: dict[int, Any],
    interceptors: list[dict[str, Any]],
    engageable_from: int | None,
    until: int | None = None,
) -> list[int]:
    """
    The ticks a threat could be engaged: from when its track may be fired
    on (engageable_from) to before it hits (until), those at which it is
    within range of at least one interceptor. None engageable_from: never
    tracked, no window.

    path: {tick: cell}; interceptors: [{at, range}].
    """
    if engageable_from is None:
        return []
    return sorted(
        tick
        for tick, cell in path.items()
        if tick >= engageable_from
        and (until is None or tick < until)
        and any(distance(i["at"], cell) <= float(i["range"]) for i in interceptors)
    )
