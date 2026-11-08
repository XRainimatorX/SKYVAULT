"""Persistent worlds = a world kept running across requests, inside its cap.

Important:
A persistent world is a run that does not finish on its own schedule: each
advance() steps it a number of ticks and leaves a checkpoint in the store
(the world's snapshot, its tick and what it has used). The governor holds
it to persistent_world_resource_cap — ticks and events — and to its
auto-stop conditions; the number of checkpoints is capped here. Reaching a
cap stops the world and its partial result is exported. The engine stays
in this process's memory: a restarted service cannot resume a world (the
engine does not serialise); its checkpoints and result remain in the store.
"""

import copy
import threading
from typing import Any

from ..engine import SkyVaultTacticalReferenceEngine
from ..interface.conflicts import (
    SubmissionWindow,
    find_conflicts,
    open_conflict,
    play_out,
    resolve,
    scheduled,
)
from ..scenario_loader import scenario_perspective
from .governance import Governor, estimate_run
from .jobs import profile_for, scenario_for
from .store import JobStore

# A world with no tick cap still needs a runtime.max_ticks: this is it
UNCAPPED_TICKS = 10**9


# Runs per branch when a conflict is played out (Phase 12)
BRANCH_REPEATS = 5


class WorldClosed(RuntimeError):
    """The world has stopped or been deleted; it cannot advance."""


class WorldAwaiting(RuntimeError):
    """The world waits at a conflict for an authority's decision."""


class PersistentWorld:
    """One persistent world, its engine stepped on request."""

    def __init__(
        self,
        world_id: str,
        request: dict[str, Any],
        policy: dict[str, Any],
        store: JobStore,
    ) -> None:
        self.world_id = world_id
        self.store = store
        self.policy = policy
        self.cap = policy["persistent_world_resource_cap"]
        scenario = scenario_for(request)
        # The scenario as written: branches of a conflict play out to its end
        self.base = copy.deepcopy(scenario)
        self.horizon = int(scenario["runtime"].get("max_ticks", 10))
        self.window = SubmissionWindow()
        self.applied: list[dict[str, Any]] = []
        self.awaiting: str | None = None
        self.profile = profile_for(request, scenario)
        self.perspective = scenario_perspective(scenario) or ""
        # The cap, not the scenario's duration, decides how long the world lives
        scenario["runtime"]["max_ticks"] = (self.cap["max_ticks"] or UNCAPPED_TICKS) + 1
        self.scenario_id = scenario["scenario_id"]
        self.governor = Governor(
            policy,
            scenario_perspective(scenario),
            cap=self.cap,
            estimated_cost=self.estimate(scenario),
        )
        self.engine = SkyVaultTacticalReferenceEngine(
            scenario,
            evaluation_profile=self.profile,
            governor=self.governor,
        )
        self.engine.begin()
        self.lifecycle = "initialized"
        self.lock = threading.Lock()
        self.result: dict[str, Any] | None = None

    def estimate(self, scenario: dict[str, Any]) -> dict[str, Any] | None:
        """The cost of living to the tick cap (none without one)."""
        if self.cap["max_ticks"] is None:
            return None
        capped = {
            **scenario,
            "runtime": {**scenario["runtime"], "max_ticks": self.cap["max_ticks"]},
        }
        return estimate_run(capped)

    def instance(self) -> dict[str, Any]:
        """The world_instance block of Formal Spec section 10."""
        return {
            "world_id": self.world_id,
            "scenario_id": self.scenario_id,
            "lifecycle_state": self.lifecycle,
        }

    def state(self) -> dict[str, Any]:
        """Where the world stands."""
        return {
            "world_id": self.world_id,
            "scenario_id": self.scenario_id,
            "lifecycle_state": self.lifecycle,
            "tick": self.engine.world.tick,
            "over": self.engine.over,
            "stop_reason": self.engine.stop_reason,
            "checkpoints": len(self.store.checkpoints(self.world_id)),
            "awaiting_decision": self.awaiting,
            "pending_actions": sum(len(v) for v in self.window.pending.values()),
            "cap": dict(self.cap),
        }

    def advance(self, ticks: int) -> dict[str, Any]:
        """
        Step up to ticks ticks, checkpoint, and pause — or, when a cap or an
        auto-stop ends the world, finish it and export its result.
        """
        if ticks < 1:
            raise ValueError("advance at least one tick")
        with self.lock:
            if self.lifecycle in ("completed", "archived", "deleted"):
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            if self.awaiting is not None:
                raise WorldAwaiting(
                    f"world {self.world_id} waits for a decision on {self.awaiting}"
                )
            self.lifecycle = "running"
            for _ in range(ticks):
                if not self._before_tick(self.engine.world.tick + 1):
                    break
                if not self.engine.step():
                    break
            snapshot = self.engine.world.snapshot()
            n = self.store.add_checkpoint(
                self.world_id,
                {
                    "tick": snapshot["tick"],
                    "decisions": self.engine.decisions,
                    "events": len(self.engine.world.event_memory),
                    "world": snapshot,
                },
            )
            limit = self.cap["max_checkpoints"]
            if not self.engine.over and limit is not None and n >= limit:
                self.engine.stop("resource_cap_reached")
            if self.engine.over:
                self._finish()
            else:
                self.lifecycle = "paused"
                self.store.update_job(
                    self.world_id,
                    lifecycle_state="paused",
                    world_instance=self.instance(),
                )
            self.store.log(
                self.world_id, f"advanced to tick {snapshot['tick']} ({self.lifecycle})"
            )
            return self.state()

    def submit(
        self, system: str, tick: int, actor_id: str, order: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Queue an outside system's action for a coming tick of this world.

        Important:
        Only a tick still to come, a unit the world has, and not the tick a
        conflict is waiting on. The action is carried out when the world
        reaches the tick — unless it conflicts with another (play_out).
        """
        with self.lock:
            if self.lifecycle in ("completed", "archived", "deleted"):
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            if tick <= self.engine.world.tick:
                raise ValueError(
                    f"tick {tick} has been played; the world is at tick "
                    f"{self.engine.world.tick}"
                )
            if actor_id not in self.engine.world.entities:
                raise KeyError(f"world {self.world_id} has no unit {actor_id}")
            proposal = self.window.submit(tick, system, actor_id, order)
            self.store.log(
                self.world_id,
                f"{system} submitted {proposal['proposal_id']} "
                f"for {actor_id} at tick {tick}",
            )
            return proposal

    def _before_tick(self, tick: int) -> bool:
        """
        Carry out the actions submitted for tick, or — if they conflict —
        play out the branches, open the conflict and stop here (False).
        """
        proposals = self.window.take(tick)
        if not proposals:
            return True
        if not find_conflicts(self.base, proposals):
            self._apply(tick, proposals)
            return True
        played = play_out(
            self.base,
            self.applied,
            proposals,
            self.profile,
            self.perspective,
            BRANCH_REPEATS,
            max(self.horizon, tick),
        )
        record = self.store.save_conflict(
            open_conflict(self.world_id, tick, proposals, played)
        )
        self.awaiting = record["conflict_id"]
        self.store.log(
            self.world_id,
            f"conflict {record['conflict_id']} at tick {tick}: waiting for a decision",
        )
        return False

    def _apply(self, tick: int, proposals: list[dict[str, Any]]) -> None:
        for proposal in proposals:
            order = scheduled(proposal)
            self.engine.scheduled[(tick, proposal["actor_id"])] = order
            self.applied.append(order)
            self.store.log(
                self.world_id,
                f"carrying out {proposal['proposal_id']} at tick {tick}",
            )

    def decide(self, conflict_id: str, branch: str, decided_by: str) -> dict[str, Any]:
        """
        An authority picks a branch of the conflict this world waits on; its
        actions are carried out at that tick and the world may advance again.
        """
        with self.lock:
            if conflict_id != self.awaiting:
                raise KeyError(f"world {self.world_id} is not waiting on {conflict_id}")
            record, kept = resolve(
                self.store.get_conflict(conflict_id), branch, decided_by
            )
            self.store.update_conflict(
                conflict_id,
                **{k: v for k, v in record.items() if k != "conflict_id"},
            )
            self._apply(record["tick"], kept)
            self.awaiting = None
            self.store.log(
                self.world_id,
                f"{decided_by} decided {conflict_id}: branch {branch}",
            )
            return record

    def finish(self) -> dict[str, Any]:
        """Close the world now and export its result (partial if it was still going)."""
        with self.lock:
            if self.result is None:
                if not self.engine.over:
                    self.engine.stop("cancelled")
                self._finish()
            if self.result is None:  # pragma: no cover - _finish always sets it
                raise RuntimeError("the world finished without a result")
            return self.result

    def _finish(self) -> None:
        self.result = self.engine.finish()
        record = self.result["reproducibility"]["run_metadata"][
            "resource_compute_governance"
        ]
        if not record["partial"] or self.policy["partial_result_export"]:
            self.store.save_result(self.world_id, self.result)
        self.lifecycle = "completed"
        self.store.update_job(
            self.world_id,
            lifecycle_state="completed",
            governance=record,
            world_instance=self.instance(),
            summary={
                **self.store.get_job(self.world_id)["summary"],
                "tick": self.result["final_world_state"]["tick"],
                "termination_reason": self.result["evaluation_result"][
                    "termination_reason"
                ],
                "output_hash": self.result["reproducibility"]["output_hash"],
                "partial": record["partial"],
            },
        )

    def delete(self) -> None:
        """Close the world (its result is kept) and mark it deleted."""
        if self.result is None:
            self.finish()
        with self.lock:
            self.lifecycle = "deleted"
            self.store.update_job(
                self.world_id,
                lifecycle_state="deleted",
                world_instance=self.instance(),
            )
            self.store.log(self.world_id, "deleted")
