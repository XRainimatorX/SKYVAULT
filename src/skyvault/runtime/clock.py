"""Clock = how time advances in a world."""

import heapq
from itertools import count
from typing import Any, Protocol


class Clock(Protocol):
    """
    What every clock offers the runtime.

    Important:
    now is a plain integer in the world's own unit. Event memory records it as
    an event's time, so every clock produces the same kind of value no matter
    how it advances.
    """

    now: int

    def advance(self) -> int: ...

    def describe(self) -> dict[str, Any]: ...


class TickClock:
    """One step per advance. The tactical reference runs on this."""

    def __init__(self) -> None:
        self.now = 0

    def advance(self) -> int:
        self.now += 1
        return self.now

    def describe(self) -> dict[str, Any]:
        return {"type": "tick"}


class PhaseClock:
    """
    Fixed-length phases: each advance moves time forward by phase_length units.

    Important:
    A six-hour phase with time_unit "hours" advances now from 0 to 6 to 12.
    phase counts how many phases have passed; now stays in base units so events
    from different phases still order correctly.
    """

    def __init__(self, phase_length: int, time_unit: str | None = None) -> None:
        if phase_length <= 0:
            raise ValueError("phase_length must be positive")
        self.phase_length = phase_length
        self.time_unit = time_unit
        self.now = 0

    @property
    def phase(self) -> int:
        return self.now // self.phase_length

    def advance(self) -> int:
        self.now += self.phase_length
        return self.now

    def describe(self) -> dict[str, Any]:
        description: dict[str, Any] = {
            "type": "phase",
            "phase_length": self.phase_length,
        }
        if self.time_unit is not None:
            description["time_unit"] = self.time_unit
        return description


class EventDrivenClock:
    """
    Time jumps straight to the next scheduled happening.

    Important:
    Nothing happens between scheduled moments, so the clock skips them. Two
    happenings scheduled for the same moment come out in the order they were
    scheduled — a stable order is what keeps a run reproducible.

    Scheduling into the past is refused: a world cannot change what already
    happened.
    """

    def __init__(self) -> None:
        self.now = 0
        self._queue: list[tuple[int, int, Any]] = []
        self._sequence = count()
        self._due: list[Any] = []

    @property
    def pending(self) -> int:
        return len(self._queue)

    def schedule(self, at: int, payload: Any) -> None:
        if at < self.now:
            raise ValueError(
                f"cannot schedule at {at}: the clock is already at {self.now}"
            )
        heapq.heappush(self._queue, (at, next(self._sequence), payload))

    def advance(self) -> int:
        """
        Jump to the earliest scheduled moment and collect everything due then.

        Raises LookupError when nothing is scheduled, because there is no next
        moment to jump to.
        """
        if not self._queue:
            raise LookupError("nothing is scheduled")

        self.now = self._queue[0][0]
        self._due = []

        while self._queue and self._queue[0][0] == self.now:
            _, _, payload = heapq.heappop(self._queue)
            self._due.append(payload)

        return self.now

    def due(self) -> list[Any]:
        """What the last advance() reached, in the order it was scheduled."""
        return list(self._due)

    def describe(self) -> dict[str, Any]:
        return {"type": "event_driven"}


def build_clock(time_model: dict[str, Any]) -> Clock:
    """The clock a world contract's time_model describes."""
    kind = time_model["type"]

    if kind == "tick":
        return TickClock()

    if kind == "phase":
        return PhaseClock(int(time_model["phase_length"]), time_model.get("time_unit"))

    if kind == "event_driven":
        return EventDrivenClock()

    raise ValueError(f"unknown time_model type {kind!r}")
