"""Resource state = the world's stock of supply, fuel, power and the like."""

from collections.abc import Mapping


class ResourceState:
    """
    How much of each world-level resource exists right now.

    Important:
    A stock never goes below zero. A change that would make it negative is
    refused rather than clamped: silently clamping would let an action consume
    supply that was never there. Checking that enough exists before acting is
    the action layer's job (Phase 3); this is the last line of defence.

    Changing a resource only adjusts the number. Recording the change in event
    memory is WorldState.change_resource(), which every mutation should go
    through so the change can be replayed.
    """

    def __init__(self, initial: Mapping[str, float] | None = None) -> None:
        self._amounts: dict[str, float] = {}
        for resource_id, amount in (initial or {}).items():
            if amount < 0:
                raise ValueError(f"resource {resource_id!r} cannot start negative")
            self._amounts[resource_id] = float(amount)

    def __contains__(self, resource_id: object) -> bool:
        return resource_id in self._amounts

    def amount(self, resource_id: str) -> float:
        if resource_id not in self._amounts:
            raise KeyError(f"Unknown resource: {resource_id}")
        return self._amounts[resource_id]

    def change(self, resource_id: str, delta: float) -> tuple[float, float]:
        """Apply delta and return (before, after). Refuses to go below zero."""
        before = self.amount(resource_id)
        after = before + delta

        if after < 0:
            raise ValueError(
                f"resource {resource_id!r} has {before}, cannot apply {delta}"
            )

        self._amounts[resource_id] = after
        return before, after

    def snapshot(self) -> dict[str, float]:
        """A copy of every stock. Later changes never reach it."""
        return dict(self._amounts)
