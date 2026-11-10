"""Policies = who decides what an actor attempts, and how to swap them.

Important:
A policy only proposes: decide_action returns an Action (or None to stand
still) and never changes the world. An observing policy names an observer
profile and is never handed the world: decide_from_observation gets what
that observer sees and answers with an order (development plan Phase 5).
Policies are registered by name, so a scenario can ask for one by name
(runtime.policy.name) without being able to load arbitrary code; a caller
can also hand the engine a policy object.
"""

import contextlib
import importlib
import importlib.util
import os
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


class ObservingPolicy(Protocol):
    """Anything that decides for one actor from its observation alone."""

    observer_profile: str

    def decide_from_observation(
        self, observation: dict[str, Any]
    ) -> dict[str, Any] | None: ...


class MultiViewPolicy(Protocol):
    """Anything that decides from several observers' views of the same moment."""

    observer_profiles: tuple[str, ...]

    def decide_from_observations(
        self, observations: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None: ...


AnyPolicy = Policy | ObservingPolicy | MultiViewPolicy

PolicyFactory = Callable[[random.Random, dict[str, Any]], AnyPolicy]

_REGISTRY: dict[str, PolicyFactory] = {}
# a deployment's own policy modules, imported on first need (see build_policy)
POLICY_MODULES = "SKYVAULT_POLICY_MODULES"
_IMPORTED: set[str] = set()

# Policies the core knows by name only: the module registering each one is
# imported the first time the name is asked for, so nothing in the core
# imports a policy (development plan Phase 6). Any other policy is
# registered by whoever brings it (register_policy, import_policy_module).
KNOWN_POLICIES = {
    "rule_based": "skyvault.actors.basic",
    "scripted": "skyvault.actors.basic",
    "human_input": "skyvault.actors.basic",
    "external_system": "skyvault.actors.basic",
    "llm_assisted": "skyvault.actors.basic",
    "tac_angel_adapter": "skyvault.actors.adapters",
    "startx_branch_adapter": "skyvault.actors.adapters",
    "hades_adapter": "skyvault.actors.adapters",
    "aerogrid_adapter": "skyvault.actors.adapters",
    "skyfox_adapter": "skyvault.actors.adapters",
    "hades_rules": "skyvault.domains.airspace.policy",
}


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
) -> AnyPolicy:
    """
    The policy registered as name, built with the run's rng.

    Important:
    A name in KNOWN_POLICIES that is not registered yet has its module
    imported first. A module that cannot be imported counts as unplugged:
    the name is then simply not available. A name SKYVAULT does not know
    may come from a deployment's own modules (SKYVAULT_POLICY_MODULES),
    imported the first time an unknown name is asked for.
    """
    if name not in _REGISTRY and name in KNOWN_POLICIES:
        with contextlib.suppress(ImportError):
            importlib.import_module(KNOWN_POLICIES[name])
    if name not in _REGISTRY:
        import_deployment_policies()
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise KeyError(f"no policy named {name!r} (registered: {known})")
    return _REGISTRY[name](rng, dict(params or {}))


def import_deployment_policies() -> None:
    """
    Import every module or .py file named in SKYVAULT_POLICY_MODULES
    (os.pathsep-separated), once each: how a deployment brings policies of
    its own to the service and its workers without changing SKYVAULT.
    """
    for spec in os.environ.get(POLICY_MODULES, "").split(os.pathsep):
        if spec and spec not in _IMPORTED:
            import_policy_module(spec)
            _IMPORTED.add(spec)


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
