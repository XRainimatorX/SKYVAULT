"""Domain packs = what a field of application adds on top of the core.

Important:
A pack brings its own action handlers, a default policy and the upkeep the
world needs at the start of every tick. The core never imports a pack: a
scenario names its domain, and load_domain imports the pack by name only
when such a scenario runs. Packs are not SKYVAULT core (development plan
Phase 13).
"""

import importlib
import random
from typing import Any, Protocol

from ..action import Action
from ..actions import ActionHandler
from ..policies import Policy
from ..world_state import WorldState

# domain name -> "module:attribute" of its pack
KNOWN_DOMAINS = {
    "military": "skyvault.domains.military.pack:MILITARY",
    "city": "skyvault.domains.city.pack:CITY",
    "airspace": "skyvault.domains.airspace.pack:AIRSPACE",
}


class DomainPack(Protocol):
    """What the engine asks of a domain pack."""

    name: str
    action_types: tuple[str, ...]

    def handlers(self) -> dict[str, ActionHandler]:
        """Every handler this domain resolves actions with, by action type."""
        ...

    def default_policy(self, scenario: dict[str, Any], rng: random.Random) -> Policy:
        """The policy that decides when nobody supplies another."""
        ...

    def upkeep(self, world: WorldState) -> list[Action]:
        """Actions the world itself takes at the start of every tick."""
        ...


# What a pack may also say, read with getattr and these defaults (Phase 14):
#   spaces = ("grid",)              the space types its policy and handlers work on
#   ends_with_last_faction = True   False: one faction left does not end the run
#   acts(entity, world) -> bool     which entities decide this tick (all, by default)
#   finished(world) -> str | None   a reason ends the run early
#   end_reasons = ()                the reasons finished() can give
#   outcome_label(world) -> str | None   the result's name instead of <faction>_survived


def load_domain(name: str) -> DomainPack:
    """The pack for name. Raises ValueError for a domain nobody provides."""
    if name not in KNOWN_DOMAINS:
        known = ", ".join(sorted(KNOWN_DOMAINS))
        raise ValueError(f"unknown domain {name!r} (known: {known})")
    module_name, attribute = KNOWN_DOMAINS[name].split(":")
    pack: DomainPack = getattr(importlib.import_module(module_name), attribute)
    return pack
