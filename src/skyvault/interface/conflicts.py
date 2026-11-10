"""Conflicts = actions from several systems for one moment: played out, never judged.

Important:
Outside systems submit actions for a tick of a running world into its
submission window. When the world reaches that tick, actions that do not
conflict are carried out (each recorded under the system that sent it).
Actions that conflict (Phase 10's detect_conflicts: the same unit twice,
the same cell, opposed targets, priorities, resources, timing) are not
carried out at all: SKYVAULT plays out every compatible set as a branch
and a branch with none — from the start, with the same seed and every
action already carried out, so each branch is the same history forked at
the conflict — and returns the conflict package. The world waits there
until a decision authority picks a branch (Formal Spec section 13).
"""

import copy
import itertools
from typing import Any

from ..batch.conflicts import branch_id, detect_conflicts
from ..batch.run import run_branches
from ..contracts.base import is_skyvault
from ..contracts.batch import Proposal
from .handoff import AUTHORITIES, authority_handoff, decide, handoff_triggers


class SubmissionWindow:
    """The actions submitted for a world's coming ticks, by tick."""

    def __init__(self) -> None:
        self.pending: dict[int, list[dict[str, Any]]] = {}
        self._numbers = itertools.count(1)

    def submit(
        self, tick: int, system: str, actor_id: str, order: dict[str, Any]
    ) -> dict[str, Any]:
        """Queue one action for tick; it becomes a proposal named <system>:<n>."""
        proposal = Proposal.model_validate(
            {
                **order,
                "proposal_id": f"{system}:{next(self._numbers)}",
                "tick": tick,
                "actor_id": actor_id,
                "system_id": system,
            }
        ).model_dump(mode="json", exclude_unset=True)
        self.pending.setdefault(tick, []).append(proposal)
        return proposal

    def withdraw(self, proposal: dict[str, Any]) -> None:
        """Take back a proposal submitted but not carried out yet."""
        waiting = self.pending.get(proposal["tick"], [])
        if proposal in waiting:
            waiting.remove(proposal)
        if not waiting:
            self.pending.pop(proposal["tick"], None)

    def take(self, tick: int) -> list[dict[str, Any]]:
        """Every action submitted for tick, in arrival order; the window empties."""
        return self.pending.pop(tick, [])


def scheduled(proposal: dict[str, Any]) -> dict[str, Any]:
    """A proposal as the scheduled order the engine carries out."""
    order = {k: v for k, v in proposal.items() if k != "proposal_id"}
    order["metadata"] = {
        **order.get("metadata", {}),
        "proposal_id": proposal["proposal_id"],
    }
    return order


def find_conflicts(
    base: dict[str, Any], proposals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The conflicts among one tick's proposals (empty: carry them all out)."""
    return detect_conflicts(base, proposals)


def play_out(
    base: dict[str, Any],
    applied: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
    profile: dict[str, Any],
    perspective: str,
    repeat_count: int,
    horizon: int,
) -> dict[str, Any]:
    """
    Every branch of a conflict, from the start of the world to horizon.

    Important:
    Seeds run from the world's own seed upwards: the first run of each
    branch is exactly this world's continuation; the others show how the
    branch fares when history goes slightly differently.
    """
    world = copy.deepcopy(base)
    world["runtime"]["scheduled_actions"] = [dict(order) for order in applied]
    world["runtime"]["max_ticks"] = horizon
    seed = int(world["runtime"]["random_seed"])
    return run_branches(
        world, proposals, profile, perspective, [seed + n for n in range(repeat_count)]
    )


def open_conflict(
    world_id: str,
    tick: int,
    proposals: list[dict[str, Any]],
    played: dict[str, Any],
    authorities: tuple[str, ...] = AUTHORITIES,
) -> dict[str, Any]:
    """The conflict record: package, branches and the handoff awaiting a decision."""
    package = played["conflict_package"]
    handoff = authority_handoff(
        handoff_triggers(conflict_package=package),
        branch_comparison=played["branch_comparison"],
        conflict_package=package,
        authorities=authorities,
    )
    branches = {branch_id(chosen): chosen for chosen in played["sets"]}
    branches["none"] = []
    return {
        "world_id": world_id,
        "tick": tick,
        "status": "awaiting_decision",
        "proposals": proposals,
        "branches": branches,
        "conflict_package": package,
        "branch_comparison": played["branch_comparison"],
        "handoff": handoff,
        "decided_by": None,
        "branch_id": None,
    }


def resolve(
    record: dict[str, Any], chosen: str, decided_by: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    An authority's decision on a conflict: the record as decided and the
    proposals of the chosen branch ("none" keeps none of them).

    Important:
    Anyone who is not a decision authority — SKYVAULT included — is refused
    first, with PermissionError; then a decided conflict with ValueError and
    an unknown branch with KeyError.
    """
    if is_skyvault(decided_by):
        raise PermissionError(
            f"{decided_by} never decides: SKYVAULT simulates, recommends and warns"
        )
    if decided_by not in record["handoff"]["decision_authority"]:
        raise PermissionError(
            f"{decided_by} is not a decision authority; "
            f"{', '.join(record['handoff']['decision_authority'])} decide"
        )
    if record["status"] != "awaiting_decision":
        raise ValueError(
            f"{record['conflict_id']} was already decided by {record['decided_by']}"
        )
    if chosen not in record["branches"]:
        raise KeyError(
            f"no branch {chosen!r}; the branches are {sorted(record['branches'])}"
        )
    handoff = decide(record["handoff"], decided_by, f"keep branch {chosen}")
    by_id = {p["proposal_id"]: p for p in record["proposals"]}
    kept = [by_id[p] for p in record["branches"][chosen]]
    return (
        {
            **record,
            "status": "decided",
            "decided_by": decided_by,
            "branch_id": chosen,
            "handoff": handoff,
        },
        kept,
    )
