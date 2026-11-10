"""Terrain = what the ground under a cell does: movement cost, cover, concealment.

Important:
Read-only helpers over world.environment (the map) and the military rule
set (the terrain table). Movement is weighted: a path's cost is the sum of
the move_cost of every cell entered, and rock or water cannot be entered.

A unit may carry capabilities.terrain_access (Phase 16: equipment that
cannot climb into a building or sinks into a forest floor): it then enters
and crosses only the terrain named there. Without it, every passable cell
is open to it, as before.
"""

import heapq
from typing import Any

from ...entity import Location
from ...world_state import WorldState

NEIGHBOURS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def cell_of(unit: Any) -> tuple[int, int]:
    """A unit's grid cell; raises for a unit with no position."""
    position = unit.position
    if not isinstance(position, tuple):
        raise ValueError(f"{unit.entity_id} has no grid position")
    return (int(position[0]), int(position[1]))


def military_rules(world: WorldState) -> dict[str, Any]:
    """rule_set.military of this world."""
    rules: dict[str, Any] = world.rules.require("military")
    return rules


def terrain_at(world: WorldState, cell: Location | None) -> dict[str, Any]:
    """The terrain profile of cell; open ground when the world has no map."""
    table = military_rules(world)["terrain"]
    terrain = world.environment.get("terrain")
    if terrain is None or not isinstance(cell, tuple):
        return dict(
            table.get("open", {"move_cost": 1, "cover": 0.0, "concealment": 0.0})
        )
    x, y = cell
    name = terrain["legend"][terrain["rows"][y][x]]
    return dict(table[name], name=name)


def allowed_terrain(unit: Any) -> set[str] | None:
    """The terrain a unit may enter (capabilities.terrain_access), or None: any."""
    access = unit.capabilities.get("terrain_access")
    return None if access is None else {str(name) for name in access}


def terrain_name(world: WorldState, cell: Location | None) -> str:
    """The name of the terrain at cell ("open" on a world without a map)."""
    return str(terrain_at(world, cell).get("name", "open"))


def reachable(
    world: WorldState,
    start: Location,
    budget: int,
    blocked: set[Any],
    allowed: set[str] | None = None,
) -> dict[tuple[int, int], int]:
    """
    Every cell reachable from start within budget, with its cheapest cost.

    blocked cells can be neither entered nor crossed (enemy units); with
    allowed, neither can terrain outside it. The start cell is included at
    cost 0. Ties in the queue break on the cell
    itself, so the result never depends on dictionary order.
    """
    if not isinstance(start, tuple):
        raise ValueError(f"reachable needs a grid cell, got {start!r}")
    origin = (int(start[0]), int(start[1]))
    best: dict[tuple[int, int], int] = {origin: 0}
    queue: list[tuple[int, tuple[int, int]]] = [(0, origin)]
    while queue:
        cost, (x, y) = heapq.heappop(queue)
        if cost > best.get((x, y), cost):
            continue
        for dx, dy in NEIGHBOURS:
            cell = (x + dx, y + dy)
            if not world.space.is_inside(cell) or cell in blocked:
                continue
            ground = terrain_at(world, cell)
            step = ground["move_cost"]
            if step is None or cost + step > budget:
                continue
            if allowed is not None and ground.get("name", "open") not in allowed:
                continue
            if cost + step < best.get(cell, budget + 1):
                best[cell] = cost + step
                heapq.heappush(queue, (cost + step, cell))
    return best


def path_cost(
    world: WorldState,
    start: Location,
    goal: Location,
    budget: int,
    blocked: set[Any],
    allowed: set[str] | None = None,
) -> int | None:
    """The cheapest cost from start to goal within budget, or None."""
    if not isinstance(goal, tuple):
        return None
    cells = reachable(world, start, budget, blocked, allowed)
    return cells.get((int(goal[0]), int(goal[1])))


def exhausted(world: WorldState, unit: Any) -> bool:
    """
    Whether a unit has spent its endurance (capabilities.endurance_ticks,
    Phase 16: the ticks its power lasts). Without it, never.
    """
    limit = unit.capabilities.get("endurance_ticks")
    return limit is not None and world.tick > int(limit)
