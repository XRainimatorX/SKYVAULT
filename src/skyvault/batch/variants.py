"""Variants = the scenarios a batch compares, each a version of one base.

Important:
A variant is always a whole scenario: another version from the scenario
folder, the base with one parameter swept to a value, or the base with a set
of outside orders scheduled. Swept and branched variants are recorded as
child versions of the base, so every run in a batch says exactly what it ran.
"""

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..library import scenario_folder
from ..reproducibility import child_version
from ..scenario_loader import load_scenario

VariantKind = Literal["version", "sweep", "branch"]

PART = re.compile(r"^(\w+)(?:\[([^\]]+)\])?$")


@dataclass(frozen=True)
class Variant:
    """One scenario a batch runs repeat_count times."""

    variant_id: str
    kind: VariantKind
    scenario: dict[str, Any]


def set_parameter(scenario: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """
    A copy of scenario with the value at path replaced.

    Important:
    path uses the notation compare_scenarios prints: dotted keys, with
    entities[<entity_id>] picking an entity by id, for example
    entities[blue_002].capabilities.accuracy. Every part must already exist,
    so a misspelt path raises KeyError instead of quietly adding a key.
    """
    changed = copy.deepcopy(scenario)
    parts = path.split(".")
    node: Any = changed
    for depth, part in enumerate(parts):
        match = PART.match(part)
        if match is None:
            raise KeyError(f"bad path segment {part!r} in {path!r}")
        key, index = match.groups()
        last = depth == len(parts) - 1
        if index is not None:
            items = node[key]
            found = [item for item in items if item.get("entity_id") == index]
            if not found:
                raise KeyError(f"no entity {index!r} for path {path!r}")
            if last:
                raise KeyError(f"path {path!r} must end at a value, not an entity")
            node = found[0]
            continue
        if key not in node:
            raise KeyError(f"{key!r} not found for path {path!r}")
        if last:
            node[key] = value
        else:
            node = node[key]
    return changed


def build_variants(batch: dict[str, Any], scenarios_dir: Path) -> list[Variant]:
    """
    The version and sweep variants a batch request names, in request order.

    Versions come from scenarios_dir/<scenario_id>/<version>.json. Each sweep
    value becomes a child version of the base labelled sweep:<path>=<value>.
    Branch variants are added by the conflict step, which knows the branches.
    """
    folder = scenario_folder(scenarios_dir, batch["scenario_id"])
    base = load_scenario(folder / f"{batch['base_version']}.json")
    variants = [
        Variant(
            item["variant_id"],
            "version",
            load_scenario(folder / f"{item['scenario_version']}.json"),
        )
        for item in batch.get("variants", [])
    ]
    for sweep in batch.get("sweeps", []):
        for value in sweep["values"]:
            label = f"sweep:{sweep['parameter']}={value}"
            swept = set_parameter(base, sweep["parameter"], value)
            variants.append(
                Variant(
                    label,
                    "sweep",
                    child_version(base, swept, label, f"Batch sweep: {label}"),
                )
            )
    return variants


def branch_variant(
    base: dict[str, Any], branch_id: str, proposals: list[dict[str, Any]]
) -> Variant:
    """
    The base with these outside orders scheduled, as a child version.

    Important:
    Orders the base already schedules are kept and the proposals added after
    them (Phase 12: a conflict in a running world branches from everything
    already done).
    Each proposal becomes a runtime.scheduled_actions entry; its proposal_id
    is kept in metadata so a branch's events can be traced back to the order.
    An empty proposal list is the baseline branch: the base run unchanged
    apart from its version label.
    """
    branched = copy.deepcopy(base)
    # orders the base already carries (actions applied before the conflict) stay
    scheduled = list(branched["runtime"].get("scheduled_actions", []))
    for proposal in proposals:
        order = {key: value for key, value in proposal.items() if key != "proposal_id"}
        order["metadata"] = {
            **order.get("metadata", {}),
            "proposal_id": proposal["proposal_id"],
        }
        scheduled.append(order)
    if scheduled:
        branched["runtime"]["scheduled_actions"] = scheduled
    label = f"branch:{branch_id}"
    reason = "Batch branch: " + (
        ", ".join(p["proposal_id"] for p in proposals)
        if proposals
        else "no outside orders"
    )
    return Variant(label, "branch", child_version(base, branched, label, reason))
