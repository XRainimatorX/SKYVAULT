"""Snapshot store = keep the world every few ticks so a rebuild can start late."""

import copy
from typing import Any


class SnapshotStore:
    """
    In-memory world snapshots, one every interval ticks.

    Important:
    The development plan says in-memory first; a persistent store comes later.

    A snapshot is only a shortcut. Event memory stays the truth: rebuilding
    from a stored snapshot plus the events after it must give the same world
    as rebuilding from time zero, and the tests hold that.

    Snapshots are deep copies on the way in and on the way out, so nothing a
    caller does later can change what was kept.
    """

    def __init__(self, interval: int) -> None:
        if interval <= 0:
            raise ValueError("snapshot interval must be positive")
        self.interval = interval
        self._snapshots: dict[int, dict[str, Any]] = {}

    def __len__(self) -> int:
        return len(self._snapshots)

    def ticks(self) -> list[int]:
        return sorted(self._snapshots)

    def record(self, time: int, snapshot: dict[str, Any], force: bool = False) -> bool:
        """
        Keep the snapshot taken at time when time falls on the interval, or
        when forced. Returns whether it was kept. Time 0 always is.
        """
        if not force and time % self.interval != 0:
            return False

        self._snapshots[time] = copy.deepcopy(snapshot)
        return True

    def latest_at_or_before(self, time: int) -> dict[str, Any] | None:
        """The newest kept snapshot no later than time, or None if there is none."""
        candidates = [tick for tick in self._snapshots if tick <= time]
        if not candidates:
            return None
        return copy.deepcopy(self._snapshots[max(candidates)])
