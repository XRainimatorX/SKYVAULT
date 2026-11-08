"""Versioning = which code, which rules and which scenario produced a result."""

from typing import Any

from .. import __version__
from ..contracts import SCHEMA_VERSION
from .hashing import content_hash, output_hash

RUNTIME_VERSION = __version__

# Formal Spec section 11 change categories, and the scenario parts each covers
CHANGE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "assumptions_changed": (
        "world_contract.assumption_registry",
        "assumption_registry",
    ),
    "data_changed": (
        "entities",
        "world_contract.space_model",
        "world_contract.entity_model",
        "world_contract.environment_state",
        "world_contract.resource_state",
        "world_contract.data_provenance",
        "data_provenance",
        "participants",
    ),
    "rules_changed": (
        "world_contract.rule_set",
        "world_contract.time_model",
        "runtime",
        "allowed_actions",
    ),
    "metrics_changed": (
        "evaluation",
        "world_contract.evaluation_targets",
    ),
    # failure_exploration is a request to stress the scenario, not part of
    # the world it describes, so it is not compared
    "failure_variables_changed": ("world_contract.failure_variables",),
}


def ruleset_version(scenario: dict[str, Any], action_types: list[str]) -> str:
    """
    A name for the rules a run was played under.

    Important:
    The world's rule_set, the action types the engine registered and the
    contract schema together decide what may happen and what it does. Change
    any of them and the ruleset version changes; nothing else moves it.
    """
    rules = {
        "rule_set": scenario["world_contract"].get("rule_set", {}),
        "action_types": sorted(action_types),
        "schema_version": SCHEMA_VERSION,
    }
    return "rules-" + content_hash(rules)[:12]


def seed_policy(runtime: dict[str, Any]) -> tuple[str, int | None, bool]:
    """
    (random_seed_policy, random_seed, deterministic_replay_available).

    Important:
    A declared random_seed_policy wins. Without one, an integer seed means
    "fixed". A stochastic run deliberately draws an unseeded generator, so it
    records no seed and cannot be replayed.
    """
    declared = runtime.get("random_seed_policy")
    seed = runtime.get("random_seed")
    policy = declared or ("fixed" if isinstance(seed, int) else "stochastic")
    if policy == "stochastic":
        return policy, None, False
    return policy, seed, seed is not None


def compare_scenarios(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    """
    What changed from one scenario version to the next, Formal Spec section 11.

    Each category lists "<path>: <old> -> <new>" for every leaf value that
    differs. Entities are matched by entity_id, so reordering them is not a
    change. Parts outside the five categories (ids, names, version fields)
    are not compared.
    """
    changes: dict[str, list[str]] = {category: [] for category in CHANGE_CATEGORIES}
    for category, paths in CHANGE_CATEGORIES.items():
        for path in paths:
            before, after = _lookup(old, path), _lookup(new, path)
            if path == "entities":
                before, after = _by_id(before), _by_id(after)
            _diff(path, before, after, changes[category])
    return changes


def compare_runs(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    How two result packages differ: inputs, outcome, verdict and every score.

    Important:
    same_output compares output hashes, so it is true only when the two runs
    produced the very same result package apart from when they ran.
    """
    repro_a, repro_b = a["reproducibility"], b["reproducibility"]
    verdict_a, verdict_b = a["evaluation_result"], b["evaluation_result"]
    axes = sorted(set(verdict_a["scores"]) | set(verdict_b["scores"]))
    return {
        "same_input": repro_a["input_hash"] == repro_b["input_hash"],
        "same_output": output_hash(a) == output_hash(b),
        "same_rules": repro_a["ruleset_version"] == repro_b["ruleset_version"],
        "scenario_version": _pair(
            repro_a["scenario_version"], repro_b["scenario_version"]
        ),
        "outcome": _pair(verdict_a["winner_or_result"], verdict_b["winner_or_result"]),
        "event_count": _pair(verdict_a["event_count"], verdict_b["event_count"]),
        "status": _pair(
            verdict_a["overall_judgement"]["status"],
            verdict_b["overall_judgement"]["status"],
        ),
        "overall_score": _pair(verdict_a["overall_score"], verdict_b["overall_score"]),
        "score_changes": {
            axis: _pair(verdict_a["scores"].get(axis), verdict_b["scores"].get(axis))
            for axis in axes
            if verdict_a["scores"].get(axis) != verdict_b["scores"].get(axis)
        },
    }


def _pair(before: Any, after: Any) -> dict[str, Any]:
    return {"before": before, "after": after}


def _lookup(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _by_id(entities: Any) -> Any:
    if not isinstance(entities, list):
        return entities
    return {entity["entity_id"]: entity for entity in entities}


def _diff(path: str, before: Any, after: Any, found: list[str]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            label = f"{path}[{key}]" if path == "entities" else f"{path}.{key}"
            _diff(label, before.get(key), after.get(key), found)
        return
    if before != after:
        found.append(f"{path}: {_show(before)} -> {_show(after)}")


def _show(value: Any) -> str:
    return "absent" if value is None else repr(value)
