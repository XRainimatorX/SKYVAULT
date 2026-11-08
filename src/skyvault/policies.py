"""Policies = who decides what an actor attempts, and how to swap them.

Important:
A policy only proposes: decide_action returns an Action (or None to stand
still) and never changes the world. Policies are registered by name, so a
scenario can ask for one by name (runtime.policy.name) without being able
to load arbitrary code; a caller can also hand the engine a policy object.
"""

import importlib
import importlib.util
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .action import Action
from .entity import Entity
from .world_state import WorldState


class Policy(Protocol):
    """Anything that proposes one action for one actor at a time."""

    def decide_action(self, world: WorldState, actor: Entity) -> Action | None: ...


PolicyFactory = Callable[[random.Random, dict[str, Any]], Policy]

_REGISTRY: dict[str, PolicyFactory] = {}


def register_policy(name: str, factory: PolicyFactory) -> None:
    """
    Make factory(rng, params) available as name.

    Raises ValueError when name is taken by a different factory, so two
    policies can never silently shadow each other.
    """
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not factory:
        raise ValueError(f"a policy named {name!r} is already registered")
    _REGISTRY[name] = factory


def build_policy(
    name: str, rng: random.Random, params: dict[str, Any] | None = None
) -> Policy:
    """The policy registered as name, built with the run's rng."""
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise KeyError(f"no policy named {name!r} (registered: {known})")
    return _REGISTRY[name](rng, dict(params or {}))


def registered_policies() -> list[str]:
    """Every registered policy name, sorted."""
    return sorted(_REGISTRY)


def import_policy_module(spec: str) -> None:
    """
    Import a module or .py file that registers policies.

    Important:
    Only for a person running a script, who names the code to load
    explicitly (--policy-module). Scenario files cannot reach this: they can
    only pick names that are already registered.
    """
    if spec.endswith(".py"):
        path = Path(spec).resolve()
        loader_spec = importlib.util.spec_from_file_location(path.stem, path)
        if loader_spec is None or loader_spec.loader is None:
            raise ImportError(f"cannot load policies from {spec}")
        module = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(module)
    else:
        importlib.import_module(spec)
