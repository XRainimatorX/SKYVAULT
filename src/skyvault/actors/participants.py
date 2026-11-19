"""Participants = which actor decides for which unit (Formal Spec section 4, step 4)."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Slot:
    """One participant: its policy and the system id its decisions carry."""

    participant_id: str
    policy: Any
    system_id: str


class Participants:
    """
    The run's actor slots, looked up by unit.

    Important:
    A participant controls whole factions, single units, or both. A unit
    claimed by two participants, or a named unit the world does not have,
    is refused when the run is built — never discovered halfway through.
    A participant's system id is its policy's system_id, else its own id.
    """

    def __init__(
        self,
        participants: list[dict[str, Any]],
        entities: Iterable[Any],
        build: Callable[[dict[str, Any]], Any],
    ) -> None:
        units = list(entities)
        known = {unit.entity_id for unit in units}
        self._slots: list[Slot] = []
        self._by_entity: dict[str, Slot] = {}
        for participant in participants:
            policy = build(participant["policy"])
            slot = Slot(
                participant["participant_id"],
                policy,
                getattr(policy, "system_id", None) or participant["participant_id"],
            )
            controls = participant["controls"]
            named = set(controls.get("entity_ids", []))
            if named - known:
                raise ValueError(
                    f"participant {slot.participant_id} controls unknown units "
                    f"{sorted(named - known)}"
                )
            factions = set(controls.get("factions", []))
            claimed = named | {u.entity_id for u in units if u.faction in factions}
            for entity_id in sorted(claimed):
                if entity_id in self._by_entity:
                    raise ValueError(
                        f"{entity_id} is controlled by both "
                        f"{self._by_entity[entity_id].participant_id} and "
                        f"{slot.participant_id}"
                    )
                self._by_entity[entity_id] = slot
            self._slots.append(slot)

    def for_entity(self, entity_id: str) -> Slot | None:
        """The slot deciding for entity_id, or None for the run's default policy."""
        return self._by_entity.get(entity_id)

    def slots(self) -> list[Slot]:
        """Every participant, in scenario order."""
        return list(self._slots)
