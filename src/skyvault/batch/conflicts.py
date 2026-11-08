"""Conflicting outside orders: detection, compatible branches, the package.

Important:
Pure functions over plain data; nothing here imports the engine. SKYVAULT
never picks between conflicting orders (Formal Spec section 13): it finds
which proposals cannot run together, runs every maximal set that can as its
own branch, and hands the results to NEXUS or the user in a conflict package.
"""

from itertools import combinations
from typing import Any

import networkx as nx

from .aggregate import METRICS

CONFLICT_TYPES = (
    "objective_conflict",
    "location_conflict",
    "timing_conflict",
    "resource_conflict",
    "priority_conflict",
    "risk_conflict",
)

# What an action does to its target entity. Actions not listed leave it alone.
TARGET_EFFECTS = {
    "attack": "harm",
    "repair": "support",
    "supply": "support",
    "deploy": "change",
    "withdraw": "change",
}
# Actions whose target entity defaults to the actor
SELF_TARGETED = ("repair", "withdraw")
# Actions that put a unit on target.location
OCCUPYING = ("move", "deploy")


def detect_conflicts(
    scenario: dict[str, Any], proposals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Every pair of same-tick proposals that cannot simply both run.

    Important:
    The rules (issue #24, section 6 point 9): one actor given two orders is
    an objective conflict; two actors sent to the same location a location
    conflict; harming and supporting the same entity an objective conflict;
    two other orders that both change the same entity a timing conflict; two
    orders each affordable from the world's stock but not together a
    resource conflict. Equal priority adds a priority conflict to the first
    two; a different risk level adds a risk conflict to any of them.
    """
    stock = scenario["world_contract"].get("resource_state", {})
    costs = scenario["world_contract"].get("rule_set", {}).get("action_costs", {})
    conflicts: list[dict[str, Any]] = []
    for first, second in combinations(proposals, 2):
        if first["tick"] != second["tick"]:
            continue
        found, reasons = _pair_conflicts(first, second, stock, costs)
        if not found:
            continue
        risk = (first.get("risk_profile") or {}).get("level")
        other_risk = (second.get("risk_profile") or {}).get("level")
        if risk is not None and other_risk is not None and risk != other_risk:
            found.add("risk_conflict")
            reasons.append(f"risk {risk} vs {other_risk}")
        conflicts.append(
            {
                "conflict_id": f"C{len(conflicts) + 1}",
                "proposals": [first["proposal_id"], second["proposal_id"]],
                "conflict_types": [t for t in CONFLICT_TYPES if t in found],
                "reason": f"{first['proposal_id']} vs {second['proposal_id']} "
                f"at tick {first['tick']}: " + "; ".join(reasons),
            }
        )
    return conflicts


def compatible_sets(
    proposals: list[dict[str, Any]], conflicts: list[dict[str, Any]]
) -> list[list[str]]:
    """
    Every maximal set of proposals with no conflict inside it.

    Each set lists proposals in request order, and the sets are ordered by
    those positions, so the branches come out the same every time. A
    proposal in no conflict is in every set.
    """
    order = [proposal["proposal_id"] for proposal in proposals]
    if not order:
        return []
    clashes: nx.Graph[str] = nx.Graph()
    clashes.add_nodes_from(order)
    clashes.add_edges_from(tuple(conflict["proposals"]) for conflict in conflicts)
    # A maximal independent set of the clash graph is a maximal clique of
    # its complement
    sets = [
        sorted(clique, key=order.index)
        for clique in nx.find_cliques(nx.complement(clashes))
    ]
    return sorted(sets, key=lambda chosen: [order.index(p) for p in chosen])


def build_conflict_package(
    scenario: dict[str, Any],
    proposals: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    branch_stats: list[dict[str, Any]],
    baseline_stats: dict[str, Any],
) -> dict[str, Any]:
    """
    The Formal Spec section 13 conflict package.

    Important:
    branch_stats holds one aggregate per compatible set, in compatible_sets
    order. Every branch is measured against the baseline run with no
    proposals. The recommendation states each branch's trade-offs and never
    names a choice; a decision is required whenever there is a conflict.
    """
    sets = compatible_sets(proposals, conflicts)
    if len(sets) != len(branch_stats):
        raise ValueError(
            f"{len(sets)} compatible sets but {len(branch_stats)} branch results"
        )
    partners: dict[str, list[str]] = {}
    for conflict in conflicts:
        first, second = conflict["proposals"]
        partners.setdefault(first, []).append(second)
        partners.setdefault(second, []).append(first)

    branches = [
        _branch_run(branch_id(chosen), chosen, stats, baseline_stats)
        for chosen, stats in zip(sets, branch_stats, strict=True)
    ]
    involved = [p for p in proposals if p["proposal_id"] in partners]
    return {
        "conflict_id": "conflict:{}:{}:{}".format(
            scenario["scenario_id"],
            scenario["scenario_version"],
            "+".join(p["proposal_id"] for p in involved) or "none",
        ),
        "scenario_id": scenario["scenario_id"],
        "conflicting_actions": [
            {
                "actor_id": proposal["actor_id"],
                "action_id": proposal["proposal_id"],
                "system_id": proposal["system_id"],
                "intent": proposal.get("intent", ""),
                "conflict_with": partners[proposal["proposal_id"]],
            }
            for proposal in involved
        ],
        "conflict_type": [
            t
            for t in CONFLICT_TYPES
            if any(t in c["conflict_types"] for c in conflicts)
        ],
        "conflicts": conflicts,
        "branch_runs": branches,
        "baseline": _branch_run("none", [], baseline_stats, baseline_stats),
        "recommendation_to_nexus": {
            "required_decision": bool(conflicts),
            "decision_reason": _decision_reason(conflicts, branches),
        },
    }


def branch_id(chosen: list[str]) -> str:
    """A branch's name: its proposals joined by '+', or 'none'."""
    return "+".join(chosen) or "none"


def summarise(stats: dict[str, Any]) -> str:
    """One line with what a variant led to over its runs."""
    low, high = stats["win_rate_ci"]
    return (
        f"{stats['runs']} runs: win {stats['win_rate']:.0%} "
        f"(95% CI {low:.0%}–{high:.0%}), loss {stats['loss_rate']:.0%}, "
        f"draw {stats['draw_rate']:.0%}; "
        f"fail verdict {stats['failure_frequency']:.0%}; "
        f"mean hp lost {stats['mean_hp_lost']:g}, risk events "
        f"{stats['mean_risk_events']:g}, score {stats['mean_score']:.3f}"
    )


def _pair_conflicts(
    first: dict[str, Any],
    second: dict[str, Any],
    stock: dict[str, float],
    costs: dict[str, dict[str, float]],
) -> tuple[set[str], list[str]]:
    found: set[str] = set()
    reasons: list[str] = []
    same_priority = first.get("priority", "normal") == second.get("priority", "normal")

    if first["actor_id"] == second["actor_id"]:
        found.add("objective_conflict")
        reasons.append(f"both order {first['actor_id']}")
        if same_priority:
            found.add("priority_conflict")
            reasons.append(f"both {first.get('priority', 'normal')} priority")
    else:
        place = _destination(first)
        if place is not None and place == _destination(second):
            found.add("location_conflict")
            reasons.append(f"both send a unit to {place}")
            if same_priority:
                found.add("priority_conflict")
                reasons.append(f"both {first.get('priority', 'normal')} priority")

    target = _target(first)
    if target is not None and target == _target(second):
        effects = {
            TARGET_EFFECTS[first["action_type"]],
            TARGET_EFFECTS[second["action_type"]],
        }
        if effects == {"harm", "support"}:
            found.add("objective_conflict")
            reasons.append(f"one harms and one supports {target}")
        else:
            found.add("timing_conflict")
            reasons.append(f"both change {target}; the order decides the result")

    for resource, available in stock.items():
        need = _cost(first, costs).get(resource, 0.0)
        other = _cost(second, costs).get(resource, 0.0)
        if need <= available and other <= available < need + other:
            found.add("resource_conflict")
            reasons.append(f"{resource} {need:g} + {other:g} exceeds {available:g}")
    return found, reasons


def _destination(proposal: dict[str, Any]) -> Any:
    if proposal["action_type"] not in OCCUPYING:
        return None
    return proposal["target"].get("location")


def _target(proposal: dict[str, Any]) -> str | None:
    """The entity the order changes, if it changes one."""
    action_type = proposal["action_type"]
    if action_type not in TARGET_EFFECTS:
        return None
    target: str | None = proposal["target"].get("entity_id")
    if target is None and action_type in SELF_TARGETED:
        return str(proposal["actor_id"])
    return target


def _cost(proposal: dict[str, Any], costs: dict[str, Any]) -> dict[str, float]:
    """What the world will charge (validation.action_cost): rule_set wins."""
    charged = costs.get(proposal["action_type"], proposal.get("required_resources"))
    return {key: float(value) for key, value in (charged or {}).items()}


def _branch_run(
    name: str,
    chosen: list[str],
    stats: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    return {
        "branch_id": name,
        "action_set": chosen,
        "result_summary": summarise(stats),
        "evaluation_delta": {
            metric: round(stats[metric] - baseline[metric], 4) for metric in METRICS
        },
        "metrics": {metric: stats[metric] for metric in METRICS},
    }


def _decision_reason(
    conflicts: list[dict[str, Any]], branches: list[dict[str, Any]]
) -> str:
    """The trade-offs between branches, without choosing one."""
    if not conflicts:
        return "The proposals do not conflict; they ran together as one branch."
    clashes = "; ".join(
        f"{c['proposals'][0]} vs {c['proposals'][1]} ("
        + ", ".join(t.removesuffix("_conflict") for t in c["conflict_types"])
        + ")"
        for c in conflicts
    )
    lines = [f"Conflicting orders: {clashes}."]
    for metric, larger_is_better in METRICS.items():
        sign = -1 if larger_is_better else 1
        leader = min(
            range(len(branches)),
            key=lambda i: (sign * branches[i]["metrics"][metric], i),
        )
        lines.append(
            f"{'Highest' if larger_is_better else 'Lowest'} {metric}: "
            f"branch {branches[leader]['branch_id']} "
            f"({branches[leader]['metrics'][metric]:g})."
        )
    lines.append(
        "SKYVAULT does not choose between the branches; "
        "NEXUS or the user decides which orders to keep."
    )
    return " ".join(lines)
