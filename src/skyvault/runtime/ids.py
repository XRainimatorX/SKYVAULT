"""Run ids = event and action ids that repeat exactly when the run repeats."""


class IdSequence:
    """
    Ids of one kind for one run: prefix_0000000001, prefix_0000000002, ...

    Important:
    The counter belongs to a run, not to the process. Two worlds built side by
    side each start at 1, so running a scenario twice gives the same ids both
    times. Ten decimal digits keep the Phase 1 id shape (ten hex characters).
    """

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.issued = 0

    def next(self) -> str:
        self.issued += 1
        return f"{self.prefix}_{self.issued:010d}"


class RunIds:
    """The two id sequences a run needs."""

    def __init__(self) -> None:
        self._events = IdSequence("event")
        self._actions = IdSequence("action")

    def event(self) -> str:
        return self._events.next()

    def action(self) -> str:
        return self._actions.next()
