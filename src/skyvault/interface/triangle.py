"""Triangle = the Definition's core loop, carried through SKYVAULT's interface.

Important:
SKYVAULT Definition IV: in a mature task NEXUS calls the whole triangle —

    1. STARTX     proposes strategic branches and their limits
    2. SKYVAULT   builds the runnable world (the mission compiled)
    3. TAC ANGEL  writes the local actions of each branch
    4. SKYVAULT   runs them
    5. STARTX     reads the results and re-evaluates its branches
    6. TAC ANGEL  adjusts its tactics from what happened
    7. NEXUS      integrates the report

STARTX and TAC ANGEL are outside systems: run_triangle takes them as
objects (propose / reevaluate, actions / adjust) and only carries what
they decide through SKYVAULT's own interface (NEXUS missions), so every
step is a submission any real system could make. SKYVAULT never chooses
a branch: STARTX ranks them, and which plan goes ahead is handed to
NEXUS / 陛下 (the mission's authority handoff).
"""

from collections.abc import Callable
from typing import Any, Protocol

from ..scenario_loader import scenario_perspective
from .missions import compile_mission
from .systems import load_scenario_named

Submit = Callable[[dict[str, Any]], dict[str, Any]]


class StrategySystem(Protocol):
    """What the loop asks of STARTX."""

    def propose(self, order: str, world: dict[str, Any]) -> list[dict[str, Any]]:
        """Strategic branches: {plan_id, description, committed, ...changes}."""

    def reevaluate(self, plans: list[dict[str, Any]]) -> dict[str, Any]:
        """{ranking, preferred, reason} from SKYVAULT's comparison of the plans."""


class TacticalSystem(Protocol):
    """What the loop asks of TAC ANGEL."""

    def actions(
        self, world: dict[str, Any], branch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """The local orders that carry out branch in world."""

    def adjust(
        self,
        world: dict[str, Any],
        branch: dict[str, Any],
        orders: list[dict[str, Any]],
        package: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """New orders, from what happened to these (package: the run's result)."""


def _plan(branch: dict[str, Any], orders: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {
        "plan_id": branch["plan_id"],
        "description": branch.get("description", ""),
        "system_id": "TAC_ANGEL",
        "actions": [{**o, "system_id": "TAC_ANGEL"} for o in orders],
    }
    for field in ("entity_changes", "rule_changes"):
        if branch.get(field):
            plan[field] = branch[field]
    return plan


def _nexus(scenario: str, mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": "NEXUS",
        "kind": "task",
        "scenario": scenario,
        "content": {"task_type": "mission", "mission": mission},
    }


def _jobs(done: dict[str, Any]) -> list[str]:
    return [entry["job"]["job_id"] for entry in done["results"]]


def _refused(package: dict[str, Any]) -> int:
    return sum(
        1
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
        and e["source"].get("system_id") == "TAC_ANGEL"
    )


def run_triangle(
    order: str,
    scenario: str,
    startx: StrategySystem,
    tac_angel: TacticalSystem,
    submit: Submit,
    mission_id: str = "triangle",
    repeat_count: int = 2,
) -> dict[str, Any]:
    """
    One pass of the triangle for order in the world scenario names.

    Important:
    submit carries a submission through SKYVAULT and returns what
    run_submission returns ({request, results, returned}). The report
    keeps every step: who did what, with the job ids, so the loop can be
    reread and each run replayed.
    """
    world = load_scenario_named(scenario)
    steps: list[dict[str, Any]] = []

    branches = startx.propose(order, world)
    steps.append(
        {
            "step": 1,
            "system": "STARTX",
            "did": "proposed strategic branches",
            "branches": [b["plan_id"] for b in branches],
        }
    )

    mission: dict[str, Any] = {
        "mission_id": mission_id,
        "order": order,
        "objective": "compare_plans",
        "scenario": scenario,
        "plans": [_plan(b, []) for b in branches],
        "repeat_count": repeat_count,
    }
    built = compile_mission(mission)
    steps.append(
        {
            "step": 2,
            "system": "SKYVAULT",
            "did": "built the runnable world",
            "assessment": built["assessment"],
            "scenarios": {
                plan_id: doc["identity"]["scenario_version"]
                for plan_id, doc in built["scenarios"].items()
            },
        }
    )

    orders = {b["plan_id"]: tac_angel.actions(world, b) for b in branches}
    mission["plans"] = [_plan(b, orders[b["plan_id"]]) for b in branches]
    steps.append(
        {
            "step": 3,
            "system": "TAC_ANGEL",
            "did": "wrote local actions",
            "orders": {k: len(v) for k, v in orders.items()},
        }
    )

    compared = submit(_nexus(scenario, mission))
    plans = compared["returned"]["plans"]
    steps.append(
        {
            "step": 4,
            "system": "SKYVAULT",
            "did": "ran every branch",
            "job_ids": _jobs(compared),
            "runs": sum(p["runs"] for p in plans),
        }
    )

    verdict = startx.reevaluate(plans)
    steps.append(
        {"step": 5, "system": "STARTX", "did": "re-evaluated its branches", **verdict}
    )

    preferred = next(b for b in branches if b["plan_id"] == verdict["preferred"])

    def tested(plan_orders: list[dict[str, Any]]) -> dict[str, Any]:
        test = {
            "mission_id": f"{mission_id}-{preferred['plan_id']}",
            "order": order,
            "objective": "test_plan",
            "scenario": scenario,
            "plans": [_plan(preferred, plan_orders)],
        }
        return submit(_nexus(scenario, test))

    before = tested(orders[preferred["plan_id"]])
    first = before["returned"]["result_package"]
    adjusted = tac_angel.adjust(world, preferred, orders[preferred["plan_id"]], first)
    after = tested(adjusted)
    second = after["returned"]["result_package"]
    tactics = {
        "plan_id": preferred["plan_id"],
        "before": {
            "job_ids": _jobs(before),
            "orders": len(orders[preferred["plan_id"]]),
            "orders_rejected": _refused(first),
            "overall_score": first["evaluation_result"]["overall_score"],
            "result": first["evaluation_result"]["winner_or_result"],
        },
        "after": {
            "job_ids": _jobs(after),
            "orders": len(adjusted),
            "orders_rejected": _refused(second),
            "overall_score": second["evaluation_result"]["overall_score"],
            "result": second["evaluation_result"]["winner_or_result"],
        },
    }
    steps.append(
        {"step": 6, "system": "TAC_ANGEL", "did": "adjusted its tactics", **tactics}
    )

    handoff = compared["returned"]["authority_handoff"]
    report = render_triangle(order, scenario_perspective(world), steps, plans, handoff)
    steps.append({"step": 7, "system": "NEXUS", "did": "integrated the report"})
    return {
        "order": order,
        "scenario": scenario,
        "steps": steps,
        "comparison": plans,
        "startx": verdict,
        "tactics": tactics,
        "authority_handoff": handoff,
        "report": report,
    }


def render_triangle(
    order: str,
    perspective: str | None,
    steps: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    handoff: dict[str, Any] | None,
) -> str:
    """The report NEXUS presents: the order, every step, the plans, who decides."""
    lines = [
        f"# {order}",
        "",
        f"Judged from {perspective or 'the scenario'}'s side.",
        "",
    ]
    lines += ["## Steps", ""]
    for step in steps:
        lines.append(f"{step['step']}. {step['system']}: {step['did']}")
    lines += ["", "## Plans", "", "| plan | win rate | failure | mean score |"]
    lines.append("|---|---|---|---|")
    for p in plans:
        c = p["consequences"]
        lines.append(
            f"| {p['plan_id']} | {c['win_rate']:.2f} | "
            f"{p['risk']['failure_frequency']:.2f} | {p['score']['mean']:.3f} |"
        )
    lines += ["", "## Decision", ""]
    if handoff:
        lines.append(handoff["package_to_nexus"]["required_decision"])
        lines.append(
            f"Decided by: {', '.join(handoff['decision_authority'])}. "
            "SKYVAULT recommends; it does not decide."
        )
    return "\n".join(lines) + "\n"
