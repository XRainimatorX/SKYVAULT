"""World view = the world as a policy may see it: readable, never writable.

Important:
A policy that reads the world gets these views instead of the world itself
(development plan Phase 6: an actor only submits intent, as an Action). The
views copy nothing: every read goes to the live world, and anything handed
back — a unit, its state, a rule table — is wrapped in turn. Only the reads
the policies measured at Phase 6 opening use are open; any write, and any
other attribute, raises ReadOnlyWorldError.
"""

from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Any

from ..entity import Entity


class ReadOnlyWorldError(AttributeError):
    """A policy tried to change the world, or to reach past what it may read."""


_SCALARS = (str, int, float, bool, type(None))


def frozen(value: Any) -> Any:
    """
    value as something that cannot be changed through it.

    Important:
    Lazy: a dict or list is wrapped, not converted, so reading one cell of
    a large table costs one wrapper, not a copy of the table.
    """
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, Entity):
        return EntityView(value)
    if isinstance(value, dict):
        return ReadOnlyMapping(value)
    if isinstance(value, list):
        return ReadOnlySequence(value)
    if isinstance(value, tuple):
        if all(isinstance(item, _SCALARS) for item in value):
            return value
        return ReadOnlySequence(value)
    if isinstance(value, set):
        return frozenset(value)
    return value


class ReadOnlyMapping(Mapping[Any, Any]):
    """A dict seen through glass: nested dicts and lists come back read-only too."""

    __slots__ = ("_data",)
    _data: Mapping[Any, Any]

    def __init__(self, data: Mapping[Any, Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __getitem__(self, key: Any) -> Any:
        return frozen(self._data[key])

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ReadOnlyMapping({self._data!r})"

    def __setitem__(self, key: Any, value: Any) -> None:
        raise ReadOnlyWorldError(f"cannot set {key!r}: the world is read-only here")

    def __delitem__(self, key: Any) -> None:
        raise ReadOnlyWorldError(f"cannot delete {key!r}: the world is read-only here")

    def __setattr__(self, name: str, value: Any) -> None:
        raise ReadOnlyWorldError("the world is read-only here")


def deep_frozen(value: Any) -> Any:
    """
    A fully read-only copy of static data: dicts become mapping proxies and
    lists tuples, all the way down. Made once, read at C speed.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: deep_frozen(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_frozen(item) for item in value)
    return value


class _StaticRules:
    """The world's rule set, frozen once: require and indexing only."""

    __slots__ = ("_rules",)
    _rules: Mapping[str, Any]

    def __init__(self, rules: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_rules", rules)

    def require(self, name: str) -> Any:
        if name not in self._rules:
            raise KeyError(f"Missing rule: {name}")
        return self._rules[name]

    def as_dict(self) -> Mapping[str, Any]:
        return self._rules

    def __getitem__(self, name: str) -> Any:
        return self._rules[name]

    def __contains__(self, name: object) -> bool:
        return name in self._rules

    def __setattr__(self, name: str, value: Any) -> None:
        raise ReadOnlyWorldError(
            "cannot change world.rules: the world is read-only here"
        )


def _same(a: Any, b: Any) -> bool:
    """Equal item by item, a list, a tuple and a read-only sequence alike."""
    kinds = (list, tuple, Sequence)
    if isinstance(a, kinds) and isinstance(b, kinds) and not isinstance(a, str):
        if isinstance(b, str) or len(a) != len(b):
            return False
        return all(_same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


class ReadOnlySequence(Sequence[Any]):
    """A list seen through glass; equal to any sequence with the same items."""

    __slots__ = ("_data",)
    _data: Sequence[Any]

    def __init__(self, data: Sequence[Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return tuple(frozen(item) for item in self._data[index])
        return frozen(self._data[index])

    def __len__(self) -> int:
        return len(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple, ReadOnlySequence)):
            return _same(self, other)
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"ReadOnlySequence({self._data!r})"

    def __setitem__(self, index: Any, value: Any) -> None:
        raise ReadOnlyWorldError("the world is read-only here")

    def __setattr__(self, name: str, value: Any) -> None:
        raise ReadOnlyWorldError("the world is read-only here")


class _Guarded:
    """
    Base of every view: only what the class itself defines can be read.

    Important:
    Reads are explicit properties and methods, found by ordinary attribute
    lookup; __getattr__ runs only for a name the view does not offer, and
    refuses it. Writing or deleting any attribute raises.
    """

    __slots__ = ()
    _label = "world"

    def __getattr__(self, name: str) -> Any:
        raise ReadOnlyWorldError(
            f"a policy may not use {self._label}.{name}: "
            "it may only read the world and submit an Action"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise ReadOnlyWorldError(
            f"cannot set {self._label}.{name}: the world is read-only here"
        )

    def __delattr__(self, name: str) -> None:
        raise ReadOnlyWorldError(
            f"cannot delete {self._label}.{name}: the world is read-only here"
        )


class SpaceView(_Guarded):
    """The world's space: distances and neighbours. Every answer is a fresh value."""

    __slots__ = ("_space",)
    _label = "world.space"
    _space: Any

    def __init__(self, space: Any) -> None:
        object.__setattr__(self, "_space", space)

    def is_inside(self, position: Any) -> bool:
        return bool(self._space.is_inside(position))

    def distance(self, a: Any, b: Any) -> Any:
        return self._space.distance(a, b)

    def neighbors(self, position: Any) -> list[Any]:
        return list(self._space.neighbors(position))

    def describe(self) -> dict[str, Any]:
        return dict(self._space.describe())

    @property
    def width(self) -> Any:
        return self._space.width

    @property
    def height(self) -> Any:
        return self._space.height


class ResourcesView(_Guarded):
    """The world's resource ledger, for reading: amounts and a copy of the ledger."""

    __slots__ = ("_resources",)
    _label = "world.resources"
    _resources: Any

    def __init__(self, resources: Any) -> None:
        object.__setattr__(self, "_resources", resources)

    def amount(self, resource_id: str) -> float:
        return float(self._resources.amount(resource_id))

    def snapshot(self) -> dict[str, float]:
        return dict(self._resources.snapshot())

    def __contains__(self, resource_id: object) -> bool:
        return resource_id in self._resources


class IdsView(_Guarded):
    """
    Action ids only: issuing one is how a policy names its Action, not a
    change to the world. Event ids stay with the world.
    """

    __slots__ = ("_ids",)
    _label = "world.ids"
    _ids: Any

    def __init__(self, ids: Any) -> None:
        object.__setattr__(self, "_ids", ids)

    def action(self) -> str:
        return str(self._ids.action())


class EntityView(_Guarded):
    """
    One unit, readable: state, capabilities and tags cannot be changed through it.

    Important:
    Every read goes to the live unit. The read-only wrapper around its state
    (and capabilities) is kept while the unit keeps the same dict, so
    reading a unit repeatedly costs no new wrappers.
    """

    __slots__ = ("_target", "_wrapped")
    _target: Entity
    _wrapped: dict[str, tuple[Any, Any]]

    def __init__(self, entity: Entity) -> None:
        object.__setattr__(self, "_target", entity)
        object.__setattr__(self, "_wrapped", {})

    @property
    def _label(self) -> str:  # type: ignore[override]
        return f"entity {self._target.entity_id}"

    def _mapping(self, name: str) -> Any:
        current = getattr(self._target, name)
        held = self._wrapped.get(name)
        if held is None or held[0] is not current:
            held = (current, ReadOnlyMapping(current))
            self._wrapped[name] = held
        return held[1]

    @property
    def entity_id(self) -> str:
        return self._target.entity_id

    @property
    def name(self) -> str:
        return self._target.name

    @property
    def entity_type(self) -> str:
        return self._target.entity_type

    @property
    def faction(self) -> str | None:
        return self._target.faction

    @property
    def position(self) -> Any:
        return frozen(self._target.position)

    @property
    def state(self) -> Any:
        return self._mapping("state")

    @property
    def capabilities(self) -> Any:
        return self._mapping("capabilities")

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(self._target.tags)

    def is_active(self) -> bool:
        return self._target.is_active()

    def snapshot(self) -> dict[str, Any]:
        """A copy: changing it changes nothing in the world."""
        return self._target.snapshot()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EntityView):
            return bool(self._target is other._target)
        return bool(self._target is other)

    def __hash__(self) -> int:
        return id(self._target)

    def __repr__(self) -> str:
        return f"EntityView({self._target.entity_id!r})"


class WorldView(_Guarded):
    """
    The world as a policy reads it.

    Important:
    Build one per run: it reads the live world on every access, except the
    rule set and the environment, which never change during a run and are
    frozen once when the view is made. Each unit has one view, kept for the
    run. The reads offered are the ones the tactical reference and military
    baseline policies use (measured at Phase 6 opening).
    """

    __slots__ = (
        "_world",
        "_rules",
        "_environment",
        "_space",
        "_resources",
        "_ids",
        "_units",
    )
    _world: Any
    _rules: _StaticRules
    _environment: Any
    _space: SpaceView
    _resources: ResourcesView
    _ids: IdsView
    _units: dict[int, EntityView]

    def __init__(self, world: Any) -> None:
        put = object.__setattr__
        put(self, "_world", world)
        put(self, "_rules", _StaticRules(deep_frozen(world.rules.as_dict())))
        put(self, "_environment", deep_frozen(world.environment))
        put(self, "_space", SpaceView(world.space))
        put(self, "_resources", ResourcesView(world.resources))
        put(self, "_ids", IdsView(world.ids))
        put(self, "_units", {})

    def view_of(self, entity: Entity) -> EntityView:
        """The one view of entity this world view hands out."""
        view = self._units.get(id(entity))
        if view is None or view._target is not entity:
            view = EntityView(entity)
            self._units[id(entity)] = view
        return view

    @property
    def world_id(self) -> str:
        return str(self._world.world_id)

    @property
    def scenario_id(self) -> str:
        return str(self._world.scenario_id)

    @property
    def tick(self) -> int:
        return int(self._world.tick)

    @property
    def space(self) -> SpaceView:
        return self._space

    @property
    def resources(self) -> ResourcesView:
        return self._resources

    @property
    def ids(self) -> IdsView:
        return self._ids

    @property
    def rules(self) -> _StaticRules:
        return self._rules

    @property
    def environment(self) -> Any:
        return self._environment

    @property
    def assumptions(self) -> Any:
        return frozen(self._world.assumptions)

    @property
    def entities(self) -> Mapping[str, EntityView]:
        return MappingProxyType(
            {k: self.view_of(e) for k, e in self._world.entities.items()}
        )

    def active_entities(self) -> list[EntityView]:
        return [self.view_of(e) for e in self._world.active_entities()]

    def get_entity(self, entity_id: str) -> EntityView:
        return self.view_of(self._world.get_entity(entity_id))

    def is_occupied(self, position: Any) -> bool:
        return bool(self._world.is_occupied(position))

    def active_factions(self) -> set[str]:
        return set(self._world.active_factions())

    def snapshot(self) -> dict[str, Any]:
        """A copy: changing it changes nothing in the world."""
        return dict(self._world.snapshot())
