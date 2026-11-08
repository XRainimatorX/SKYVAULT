"""Entity registry = every entity a world holds, addressable by id."""

from collections.abc import Iterable, Iterator, Mapping

from ..entity import Entity


class EntityRegistry(Mapping[str, Entity]):
    """
    The entities of one world.

    Important:
    It reads like a dict (iteration, len, values, items), so code that used to
    hold a plain dict keeps working. It differs in two ways:

    add() refuses a duplicate id — two entities sharing an id would make event
    memory ambiguous about who did what.

    require() raises KeyError for an unknown id instead of returning None, so a
    bad id fails where it is used instead of turning into a silent no-op.

    A destroyed entity is never removed, only marked: event memory keeps
    referring to it.
    """

    def __init__(self, entities: Iterable[Entity] = ()) -> None:
        self._entities: dict[str, Entity] = {}
        for entity in entities:
            self.add(entity)

    def add(self, entity: Entity) -> None:
        if entity.entity_id in self._entities:
            raise ValueError(f"duplicate entity_id {entity.entity_id!r}")
        self._entities[entity.entity_id] = entity

    def require(self, entity_id: str) -> Entity:
        if entity_id not in self._entities:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        return self._entities[entity_id]

    def active(self) -> list[Entity]:
        """Every entity still alive, in registration order."""
        return [entity for entity in self._entities.values() if entity.is_active()]

    def __getitem__(self, entity_id: str) -> Entity:
        return self._entities[entity_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entities)

    def __len__(self) -> int:
        return len(self._entities)
