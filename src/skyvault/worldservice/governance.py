"""Governance = the world service's limits, checked at the door and at every tick.

Important:
admit() checks a job before it is queued: too many runs, too costly, a full
queue — refused with the reason; a duration over the limit is cut down and
the cut recorded. The Governor rides along inside the engine and is asked
at the end of every tick whether the run should stop on its own (Formal
Spec section 15's auto-stop conditions). Neither imports the engine.
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..contracts import ResourceComputeGovernance, validate_governance

GOVERNANCE_DIR = Path(__file__).resolve().parents[3] / "data" / "service"

# Seconds per decision, measured at Phase 11 opening (reference 46 decisions in
# 34 ms, urban 208 in 138 ms): the basis of every estimate
SECONDS_PER_DECISION = 0.0007


class Rejected(ValueError):
    """A job the service refuses at the door, with the reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def load_governance(name_or_path: str | Path = "governance") -> dict[str, Any]:
    """A governance policy by name (data/service/<name>.json) or path, filled in."""
    path = Path(name_or_path)
    if path.suffix != ".json":
        path = GOVERNANCE_DIR / f"{name_or_path}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_governance(data)
    return ResourceComputeGovernance.model_validate(data).model_dump(mode="json")


def limits(policy: dict[str, Any]) -> dict[str, Any]:
    """The limits a run is held to, as its governance record shows them."""
    return {
        "compute_budget": dict(policy["compute_budget"]),
        "max_scenario_duration": policy["max_scenario_duration"],
        "max_runtime_seconds": policy["max_runtime_seconds"],
        "auto_stop": dict(policy["auto_stop"]),
    }


def estimate_run(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    What one run of scenario will cost: one decision per unit per tick at
    most, at the measured seconds per decision.
    """
    units = len(scenario["entities"])
    ticks = int(scenario["runtime"].get("max_ticks", 10))
    decisions = units * ticks
    return {
        "runs": 1,
        "decisions": decisions,
        "seconds": round(decisions * SECONDS_PER_DECISION, 3),
    }


def scale(estimate: dict[str, Any], runs: int) -> dict[str, Any]:
    """The estimate for runs runs of the same size."""
    return {
        "runs": runs,
        "decisions": estimate["decisions"] * runs,
        "seconds": round(estimate["seconds"] * runs, 3),
    }


def clamp_duration(scenario: dict[str, Any], policy: dict[str, Any]) -> int | None:
    """Cut runtime.max_ticks to max_scenario_duration; the asked value if cut."""
    ceiling = policy["max_scenario_duration"]
    asked = int(scenario["runtime"].get("max_ticks", 10))
    if ceiling is not None and asked > ceiling:
        scenario["runtime"]["max_ticks"] = ceiling
        return asked
    return None


def admit(
    estimate: dict[str, Any],
    policy: dict[str, Any],
    queue_length: int,
) -> None:
    """
    Refuse a job the policy does not allow, with the reason.

    Important:
    batch_too_large: more runs than max_batch_count. budget_exceeded: the
    estimated decisions of one run exceed the compute budget, or the
    estimate exceeds max_runtime_seconds per run. queue_full: the queue
    already holds max_queue_length jobs.
    """
    if (
        policy["max_batch_count"] is not None
        and estimate["runs"] > policy["max_batch_count"]
    ):
        raise Rejected(
            "batch_too_large",
            f"{estimate['runs']} runs; max_batch_count is {policy['max_batch_count']}",
        )
    per_run = estimate["decisions"] / max(estimate["runs"], 1)
    budget = policy["compute_budget"]["max_decisions"]
    if budget is not None and per_run > budget:
        raise Rejected(
            "budget_exceeded",
            f"about {per_run:.0f} decisions per run; the budget is {budget}",
        )
    seconds = policy["max_runtime_seconds"]
    if seconds is not None and estimate["seconds"] / max(estimate["runs"], 1) > seconds:
        raise Rejected(
            "budget_exceeded",
            f"about {estimate['seconds']:.1f} s per run; the limit is {seconds} s",
        )
    if (
        policy["max_queue_length"] is not None
        and queue_length >= policy["max_queue_length"]
    ):
        raise Rejected(
            "queue_full",
            f"{queue_length} jobs queued; the limit is {policy['max_queue_length']}",
        )


def fingerprint(snapshot: dict[str, Any]) -> str:
    """The units and resources of a world snapshot, as one hash (the tick left out)."""
    state = {
        "entities": snapshot["entities"],
        "resources": snapshot.get("resources", {}),
    }
    text = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Governor:
    """
    The policy, applied to one run as it goes.

    Important:
    after_tick() is called at the end of every tick with the world snapshot
    and the run's counts so far, and answers with a stop reason or None.
    Checks in order: cancelled, max_runtime_exceeded, budget_exceeded,
    resource_cap_reached (persistent worlds only), failure_threshold_reached,
    no_new_state_change, infinite_loop_detected.
    """

    def __init__(
        self,
        policy: dict[str, Any],
        perspective: str | None = None,
        cap: dict[str, Any] | None = None,
        estimated_cost: dict[str, Any] | None = None,
        duration_clamped_from: int | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.policy = policy
        self.perspective = perspective
        self.cap = cap
        self.estimated_cost = estimated_cost
        self.duration_clamped_from = duration_clamped_from
        self.cancel_requested = False
        self.cancel_check = cancel_check
        self.started = time.monotonic()
        self.last: str | None = None
        self.unchanged = 0
        self.seen: dict[str, int] = {}

    def start(self) -> None:
        self.started = time.monotonic()

    def cancel(self) -> None:
        """Ask the run to stop at the end of the current tick."""
        self.cancel_requested = True

    def after_tick(
        self, snapshot: dict[str, Any], decisions: int, events: int, ticks: int
    ) -> str | None:
        if self.cancel_requested or (self.cancel_check and self.cancel_check()):
            return "cancelled"
        seconds = self.policy["max_runtime_seconds"]
        if seconds is not None and time.monotonic() - self.started > seconds:
            return "max_runtime_exceeded"
        budget = self.policy["compute_budget"]
        if (
            budget["max_decisions"] is not None and decisions > budget["max_decisions"]
        ) or (budget["max_events"] is not None and events > budget["max_events"]):
            return "budget_exceeded"
        if self.cap is not None and (
            (self.cap["max_ticks"] is not None and ticks >= self.cap["max_ticks"])
            or (self.cap["max_events"] is not None and events >= self.cap["max_events"])
        ):
            return "resource_cap_reached"
        if self._lost_too_many(snapshot):
            return "failure_threshold_reached"
        return self._repeating(fingerprint(snapshot))

    def _lost_too_many(self, snapshot: dict[str, Any]) -> bool:
        ratio = self.policy["auto_stop"]["failure_loss_ratio"]
        if ratio is None or self.perspective is None:
            return False
        side = [
            u for u in snapshot["entities"].values() if u["faction"] == self.perspective
        ]
        lost = sum(1 for u in side if u["state"].get("status", "active") != "active")
        return bool(side) and lost / len(side) >= ratio

    def _repeating(self, state: str) -> str | None:
        rules = self.policy["auto_stop"]
        if state == self.last:
            self.unchanged += 1
            window = rules["no_new_state_change_ticks"]
            if window is not None and self.unchanged >= window:
                return "no_new_state_change"
            return None
        self.unchanged = 0
        self.last = state
        self.seen[state] = self.seen.get(state, 0) + 1
        repeats = rules["infinite_loop_repeats"]
        if repeats is not None and self.seen[state] >= repeats:
            return "infinite_loop_detected"
        return None

    def record(self, usage: dict[str, Any], stop_reason: str | None) -> dict[str, Any]:
        """This run's governance record."""
        return {
            "policy_id": self.policy["policy_id"],
            "run_priority": self.policy["run_priority"],
            "limits": limits(self.policy),
            "usage": usage,
            "estimated_cost": self.estimated_cost,
            "stopped": stop_reason is not None,
            "stop_reason": stop_reason,
            "partial": stop_reason is not None,
            "duration_clamped_from": self.duration_clamped_from,
        }
