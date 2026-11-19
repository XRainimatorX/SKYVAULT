"""Action queue = orders submitted from outside the run, waiting for their turn.

Important:
An outside system or a person submits an order for one unit at one tick,
from any thread or from asyncio code; the run takes it when that unit's
turn comes, waiting at most a timeout. Nothing else crosses: the queue
holds orders, never the world.
"""

import threading
from typing import Any


class ActionQueue:
    """Orders keyed by (tick, entity id); each key takes one order."""

    def __init__(self) -> None:
        self._orders: dict[tuple[int, str], dict[str, Any]] = {}
        self._ready = threading.Condition()

    def submit_nowait(self, tick: int, entity_id: str, order: dict[str, Any]) -> None:
        """Queue an order; a second order for the same unit and tick raises."""
        key = (int(tick), str(entity_id))
        with self._ready:
            if key in self._orders:
                raise ValueError(f"an order for {entity_id} at tick {tick} is queued")
            self._orders[key] = dict(order)
            self._ready.notify_all()

    async def submit(self, tick: int, entity_id: str, order: dict[str, Any]) -> None:
        """submit_nowait for asyncio code (async action submission)."""
        self.submit_nowait(tick, entity_id, order)

    def take(self, tick: int, entity_id: str, timeout: float) -> dict[str, Any] | None:
        """This unit's order for tick, waiting up to timeout seconds; else None."""
        key = (int(tick), str(entity_id))
        with self._ready:
            if not self._ready.wait_for(lambda: key in self._orders, timeout):
                return None
            return self._orders.pop(key)

    def pending(self) -> list[tuple[int, str]]:
        """Every (tick, entity id) with an order still waiting, in order."""
        with self._ready:
            return sorted(self._orders)
