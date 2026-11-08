"""
Runtime = the building blocks a world is made of.

Space, clock, entity registry, resources, rules, snapshots and event sourcing
live here, each usable on its own. They depend only on contracts and on the
plain data objects (Entity, Event); never on the engine, a policy or an
exporter.

Important:
create_world() lives in runtime.world and is not re-exported here. It builds a
WorldState, and world_state imports the primitives below, so exporting it from
this package would make the two import each other.
"""

from .clock import Clock, EventDrivenClock, PhaseClock, TickClock, build_clock
from .registry import EntityRegistry
from .resources import ResourceState
from .rules import RuleSet
from .snapshots import SnapshotStore
from .sourcing import rebuild_world
from .space import GraphSpace, GridSpace, NetworkSpace, Space, build_space

__all__ = [
    "Clock",
    "EntityRegistry",
    "EventDrivenClock",
    "GraphSpace",
    "GridSpace",
    "NetworkSpace",
    "PhaseClock",
    "ResourceState",
    "RuleSet",
    "SnapshotStore",
    "Space",
    "TickClock",
    "build_clock",
    "build_space",
    "rebuild_world",
]
