"""Stand-ins = simple outside systems that let the triangle loop run end to end.

Important:
STARTX and TAC ANGEL are not part of SKYVAULT, and SKYVAULT must never
decide for them. These stand-ins exist so the Definition's triangle loop
(interface/triangle.py) can be checked on SKYVAULT's side without the real
systems: each is a few fixed rules, marked as a stand-in wherever it
appears, and each decides only through the interface any real system
uses. Nothing in SKYVAULT's runs or judgements reads them.
"""

from typing import Any

from ..observation.history import history_from_package
from ..observation.sensing import grid_distance
from ..scenario_loader import scenario_perspective


def _side(world: dict[str, Any], faction: str) -> list[dict[str, Any]]:
    return sorted(
        (e for e in world["entities"] if e["faction"] == faction and e["position"]),
        key=lambda e: (e["position"][0], e["entity_id"]),
    )


class StandInSTARTX:
    """
    A stand-in STARTX: three branches for the perspective side — commit
    the western half of its units, the eastern half, or all of them — and
    a re-evaluation that prefers the branch with the best mean score, then
    the lowest failure frequency.
    """

    system = "STARTX (stand-in)"

    def propose(self, order: str, world: dict[str, Any]) -> list[dict[str, Any]]:
        faction = scenario_perspective(world) or world["entities"][0]["faction"]
        units = [u["entity_id"] for u in _side(world, faction)]
        half = len(units) // 2
        return [
            {
                "plan_id": "west_axis",
                "description": "commit the western group; the rest hold",
                "committed": units[:half],
            },
            {
                "plan_id": "east_axis",
                "description": "commit the eastern group; the rest hold",
                "committed": units[half:],
            },
            {
                "plan_id": "broad_front",
                "description": "commit every unit on a broad front",
                "committed": units,
            },
        ]

    def reevaluate(self, plans: list[dict[str, Any]]) -> dict[str, Any]:
        ranked = sorted(
            plans,
            key=lambda p: (
                -p["score"]["mean"],
                p["risk"]["failure_frequency"],
                p["plan_id"],
            ),
        )
        best = ranked[0]
        return {
            "ranking": [p["plan_id"] for p in ranked],
            "preferred": best["plan_id"],
            "reason": (
                f"{best['plan_id']}: mean score {best['score']['mean']:.3f}, "
                f"failure frequency {best['risk']['failure_frequency']:.2f}"
            ),
        }


class StandInTACAngel:
    """
    A stand-in TAC ANGEL: each committed unit advances on the nearest enemy
    for two ticks, as far as its move range reaches on open ground (it does
    not read terrain cost); after a run, each move SKYVAULT refused becomes
    a one-cell step towards the same cell.
    """

    system = "TAC_ANGEL (stand-in)"
    ticks = (1, 2)

    def actions(
        self, world: dict[str, Any], branch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        space = world["world_contract"]["space_model"]
        width, height = int(space["width"]), int(space["height"])
        faction = scenario_perspective(world) or ""
        enemies = [e for e in world["entities"] if e["faction"] != faction]
        units = {e["entity_id"]: e for e in world["entities"]}
        taken: set[tuple[int, int]] = {
            tuple(e["position"]) for e in world["entities"] if e["position"]
        }
        orders = []
        for unit_id in branch["committed"]:
            unit = units[unit_id]
            here = tuple(unit["position"])
            target = min(
                (tuple(e["position"]) for e in enemies),
                key=lambda p: (grid_distance(space, here, p), p),
            )
            reach = int(unit["capabilities"].get("move_range", 1))
            for tick in self.ticks:
                cells = [
                    (x, y)
                    for x in range(
                        max(0, here[0] - reach), min(width, here[0] + reach + 1)
                    )
                    for y in range(
                        max(0, here[1] - reach), min(height, here[1] + reach + 1)
                    )
                    if grid_distance(space, here, (x, y)) <= reach
                    and (x, y) not in taken
                ]
                if not cells:
                    break
                step = min(cells, key=lambda c: (grid_distance(space, c, target), c))
                taken.add(step)
                orders.append(
                    {
                        "tick": tick,
                        "actor_id": unit_id,
                        "action_type": "move",
                        "target": {"location": list(step)},
                        "intent": "tac_angel_advance",
                    }
                )
                here = step
        return orders

    def adjust(
        self,
        world: dict[str, Any],
        branch: dict[str, Any],
        orders: list[dict[str, Any]],
        package: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        A refused move becomes a one-cell step towards the same cell, from
        where the unit stood when the order came; a refused order of any
        other kind is dropped.
        """
        space = world["world_contract"]["space_model"]
        history = history_from_package(package)
        refused = {
            (e["time"], e["source"]["actor_id"])
            for e in package["event_memory"]
            if e["event_type"] == "ACTION_REJECTED"
            and e["source"].get("system_id") == "TAC_ANGEL"
        }
        adjusted = []
        for order in orders:
            key = (order["tick"], order["actor_id"])
            if key not in refused:
                adjusted.append(order)
                continue
            if order["action_type"] != "move":
                continue
            before = max(t for t in history if t < order["tick"])
            unit = history[before][order["actor_id"]]
            if not unit.get("position"):
                continue
            here = tuple(unit["position"])
            goal = tuple(order["target"]["location"])
            cells = [
                (here[0] + dx, here[1] + dy)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0)
            ]
            step = min(cells, key=lambda c: (grid_distance(space, c, goal), c))
            adjusted.append(
                {
                    **order,
                    "target": {"location": list(step)},
                    "intent": "tac_angel_step",
                }
            )
        return adjusted
