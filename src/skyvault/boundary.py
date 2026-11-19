"""The Final Authority Boundary: what SKYVAULT may do, and what it never may.

Important:
Development plan Phase 20, Formal Spec section 17. SKYVAULT is a
world-environment engine: it simulates, recommends and warns; the final
decision belongs to a decision authority (NEXUS, the sovereign, a customer)
and never to SKYVAULT. This module only declares the boundary; it is
enforced where decisions are made — the contracts refuse SKYVAULT as a
decision authority, and interface.handoff.decide refuses it as the one who
decides, whatever a configuration says.

Pure data; is_skyvault comes from the contracts, the bottom layer, where
the boundary is enforced.
"""

from .contracts.base import is_skyvault

ROLE = "world_environment_engine"

MAY = (
    "simulate",
    "recommend",
    "warn",
    "return a failure map",
    "return a conflict package",
    "reject an invalid scenario",
)

MAY_NOT = (
    "make a sovereign decision",
    "override NEXUS",
    "override STARTX strategic intent",
    "replace human authority",
    "decide the final strategy on its own",
)


__all__ = ["MAY", "MAY_NOT", "ROLE", "declaration", "is_skyvault"]


def declaration() -> dict[str, object]:
    """{role, may, may_not}: the boundary as the service states it."""
    return {"role": ROLE, "may": list(MAY), "may_not": list(MAY_NOT)}
