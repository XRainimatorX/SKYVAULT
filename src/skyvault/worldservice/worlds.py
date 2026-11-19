"""Persistent worlds = a world kept running across requests, inside its cap.

Important:
A persistent world is a run that does not finish on its own schedule: each
advance() steps it a number of ticks and leaves a checkpoint in the store
(the world's snapshot, its tick and what it has used). The governor holds
it to persistent_world_resource_cap — ticks and events — and to its
auto-stop conditions; the number of checkpoints is capped here. Reaching a
cap stops the world and its partial result is exported.

Formal Spec section 10.3: a world lives through created, initialized,
running, paused (pause_world, until resume_world), branched (a branch_world
copy that has not moved yet), completed (finished or terminate_world),
failed, archived (archive_world), replayed and deleted.

The engine does not serialise, so the world keeps what it was given
instead (world_inputs in its job: the orders carried out, the actions still
waiting and the conflict it waits on). A world is deterministic, so
restore() rebuilds it after a restart by playing those inputs again up to
the last checkpoint, and refuses — marking the world failed — if the
rebuilt world is not the one the checkpoint recorded.
"""

import copy
import threading
from typing import Any

from ..engine import SkyVaultEngine
from ..interface.conflicts import (
    SubmissionWindow,
    find_conflicts,
    open_conflict,
    play_out,
    resolve,
    scheduled,
)
from ..interface.handoff import AUTHORITIES
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


class WorldPaused(RuntimeError):
    """The world was paused (pause_world); resume it before it advances."""


LIVE = ("initialized", "running", "paused", "branched")
CLOSED = ("completed", "failed", "archived", "deleted")


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
        self.request = copy.deepcopy(request)
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
        self.engine = SkyVaultEngine(
            scenario,
            evaluation_profile=self.profile,
            governor=self.governor,
        )
        self.engine.begin()
        self.governor.pause()  # runtime counts only while advancing
        self.lifecycle = "initialized"
        self.lock = threading.Lock()
        self.result: dict[str, Any] | None = None

    @classmethod
    def restore(
        cls, job: dict[str, Any], policy: dict[str, Any], store: JobStore
    ) -> "PersistentWorld":
        """
        The world of job rebuilt after a restart: its scenario played again
        with the inputs it was given, up to its last checkpoint.

        Important:
        The rebuilt world must be the one the last checkpoint recorded,
        snapshot for snapshot; otherwise RuntimeError (and the caller marks
        the world failed). A world never checkpointed restarts at tick 0.
        """
        world = cls(job["job_id"], job["request"], policy, store)
        inputs = job["summary"].get("world_inputs") or {
            "tick": 0,
            "applied": [],
            "pending": [],
            "awaiting": None,
        }
        world.replay_inputs(inputs)
        checkpoints = store.checkpoints(world.world_id)
        if checkpoints:
            recorded = checkpoints[-1]["world"]
            rebuilt = world.engine.world.snapshot()
            if rebuilt != recorded:
                raise RuntimeError(
                    f"world {world.world_id} rebuilt to tick {rebuilt['tick']} "
                    "is not the world its last checkpoint recorded"
                )
        world.lifecycle = job["lifecycle_state"]
        store.log(world.world_id, f"restored at tick {world.engine.world.tick}")
        return world

    def branch(self, world_id: str) -> "PersistentWorld":
        """
        branch_world: a new world (world_id) that is this one as it stands —
        the same scenario played with the same inputs to the same tick — and
        then goes its own way. It is "branched" until it first advances.
        """
        with self.lock:
            if self.lifecycle in CLOSED:
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            inputs = self.inputs()
        twin = PersistentWorld(world_id, self.request, self.policy, self.store)
        twin.replay_inputs(inputs)
        twin.lifecycle = "branched"
        twin.store.update_job(
            world_id,
            lifecycle_state="branched",
            world_instance=twin.instance(),
            summary_fields={
                "branched_from": {"world_id": self.world_id, "tick": inputs["tick"]},
                "world_inputs": twin.inputs(),
            },
        )
        twin.store.log(
            world_id, f"branched from {self.world_id} at tick {inputs['tick']}"
        )
        return twin

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

    def events(self) -> list[dict[str, Any]]:
        """The world's event memory so far, as the result package will hold it."""
        with self.lock:
            return [event.to_dict() for event in self.engine.world.event_memory]

    def advance(self, ticks: int) -> dict[str, Any]:
        """
        Step up to ticks ticks and checkpoint — or, when a cap or an auto-stop
        ends the world, finish it and export its result. A world that breaks
        while stepping is marked failed.
        """
        if ticks < 1:
            raise ValueError("advance at least one tick")
        with self.lock:
            if self.lifecycle in CLOSED:
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            if self.lifecycle == "paused":
                raise WorldPaused(f"world {self.world_id} is paused; resume it first")
            if self.awaiting is not None:
                raise WorldAwaiting(
                    f"world {self.world_id} waits for a decision on {self.awaiting}"
                )
            self.lifecycle = "running"
            self.governor.resume()
            try:
                for _ in range(ticks):
                    if not self._before_tick(self.engine.world.tick + 1):
                        break
                    if not self.engine.step():
                        break
            except Exception as error:
                self._fail(str(error))
                raise
            finally:
                self.governor.pause()
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
                self.store.update_job(
                    self.world_id,
                    lifecycle_state="running",
                    world_instance=self.instance(),
                )
            self._keep_inputs()
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
        return self.submit_all(system, [(tick, actor_id, order)])[0]

    def submit_all(
        self, system: str, actions: list[tuple[int, str, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """
        Queue several actions of one submission: all of them, or — when any
        one is refused — none (the refusal is raised).
        """
        with self.lock:
            if self.lifecycle in CLOSED:
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            for tick, actor_id, _ in actions:
                if tick <= self.engine.world.tick:
                    raise ValueError(
                        f"tick {tick} has been played; the world is at tick "
                        f"{self.engine.world.tick}"
                    )
                if actor_id not in self.engine.world.entities:
                    raise KeyError(f"world {self.world_id} has no unit {actor_id}")
            proposals: list[dict[str, Any]] = []
            try:
                for tick, actor_id, order in actions:
                    proposals.append(self.window.submit(tick, system, actor_id, order))
            except Exception:
                for proposal in proposals:
                    self.window.withdraw(proposal)
                raise
            for proposal in proposals:
                self.store.log(
                    self.world_id,
                    f"{system} submitted {proposal['proposal_id']} "
                    f"for {proposal['actor_id']} at tick {proposal['tick']}",
                )
            self._keep_inputs()
            return proposals

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
            open_conflict(
                self.world_id,
                tick,
                proposals,
                played,
                authorities=tuple(
                    self.policy.get("decision_authorities") or AUTHORITIES
                ),
            )
        )
        self.awaiting = record["conflict_id"]
        self.store.log(
            self.world_id,
            f"conflict {record['conflict_id']} at tick {tick}: waiting for a decision",
        )
        self._keep_inputs()
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
            # who decides is checked first: a non-authority is refused even
            # on a conflict that is already decided
            record, kept = resolve(
                self.store.get_conflict(conflict_id), branch, decided_by
            )
            if conflict_id != self.awaiting:
                raise KeyError(f"world {self.world_id} is not waiting on {conflict_id}")
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
            self._keep_inputs()
            return record

    # ── Formal Spec 10.4 service actions ────────────────────────────────────

    def pause(self) -> dict[str, Any]:
        """pause_world: refuse to advance until resumed."""
        with self.lock:
            if self.lifecycle in CLOSED:
                raise WorldClosed(f"world {self.world_id} is {self.lifecycle}")
            self.lifecycle = "paused"
            self._record_lifecycle("paused")
            return self.state()

    def resume(self) -> dict[str, Any]:
        """resume_world: a paused world may advance again."""
        with self.lock:
            if self.lifecycle != "paused":
                raise ValueError(
                    f"world {self.world_id} is {self.lifecycle}, not paused"
                )
            self.lifecycle = "running"
            self._record_lifecycle("running")
            return self.state()

    def terminate(self) -> dict[str, Any]:
        """terminate_world: stop now and export the (partial) result."""
        return self.finish(reason="terminated")

    def archive(self) -> dict[str, Any]:
        """archive_world: put a finished world away; its result is kept."""
        with self.lock:
            if self.lifecycle not in ("completed", "failed"):
                raise ValueError(
                    f"only a completed or failed world is archived; "
                    f"{self.world_id} is {self.lifecycle}"
                )
            self.lifecycle = "archived"
            self._record_lifecycle("archived")
            return self.instance()

    def inputs(self) -> dict[str, Any]:
        """What the world was given so far: enough to rebuild it (restore())."""
        return {
            "tick": self.engine.world.tick,
            "applied": copy.deepcopy(self.applied),
            "pending": [
                copy.deepcopy(p)
                for tick in sorted(self.window.pending)
                for p in self.window.pending[tick]
            ],
            "awaiting": self.awaiting,
        }

    def replay_inputs(self, inputs: dict[str, Any]) -> None:
        """Play inputs into this fresh world: the same orders, up to the same tick."""
        for order in inputs["applied"]:
            self.engine.scheduled[(order["tick"], order["actor_id"])] = order
            self.applied.append(copy.deepcopy(order))
        self.governor.resume()
        try:
            while self.engine.world.tick < inputs["tick"] and not self.engine.over:
                self.engine.step()
        finally:
            self.governor.pause()
        for proposal in inputs["pending"]:
            self.window.restore(proposal)
        self.awaiting = inputs["awaiting"]

    def _keep_inputs(self) -> None:
        self.store.update_job(
            self.world_id, summary_fields={"world_inputs": self.inputs()}
        )

    def _record_lifecycle(self, state: str) -> None:
        self.store.update_job(
            self.world_id, lifecycle_state=state, world_instance=self.instance()
        )
        self.store.log(self.world_id, state)

    def _fail(self, error: str) -> None:
        self.lifecycle = "failed"
        self.store.update_job(
            self.world_id,
            lifecycle_state="failed",
            error=error,
            world_instance=self.instance(),
        )
        self.store.log(self.world_id, f"failed: {error}")

    def finish(self, reason: str = "cancelled") -> dict[str, Any]:
        """Close the world now and export its result (partial if it was still going)."""
        with self.lock:
            if self.result is None:
                if not self.engine.over:
                    self.engine.stop(reason)
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
            summary_fields={
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
