"""The three core extension points: policy registry, domain loading, environment."""

import ast
import copy
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skyvault.action import Action, ActionTarget
from skyvault.actions import MILITARY_ACTION_TYPES
from skyvault.domains import load_domain
from skyvault.domains.military import MILITARY
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.policies import build_policy, register_policy, registered_policies
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_scenario

REFERENCE = SRC.parent / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"


class Holder:
    """An outside policy: every unit only looks at itself. Names itself TAC_ANGEL."""

    system_id = "TAC_ANGEL"

    def decide_action(self, world, actor):
        return Action(
            world.ids.action(),
            actor.entity_id,
            "observe",
            target=ActionTarget(entity_id=actor.entity_id),
            intent="hold",
        )


def test_the_reference_policy_is_registered_and_others_can_join():
    assert "tactical_reference" in registered_policies()
    factory = lambda rng, params: Holder()  # noqa: E731
    register_policy("test_holder", factory)
    register_policy("test_holder", factory)  # the same factory again is fine

    assert isinstance(build_policy("test_holder", random.Random(1)), Holder)
    with pytest.raises(ValueError, match="already registered"):
        register_policy("test_holder", lambda rng, params: Holder())
    with pytest.raises(KeyError, match="no policy named 'nobody'"):
        build_policy("nobody", random.Random(1))


def test_an_outside_policy_replaces_the_baseline_and_signs_its_events():
    package = SkyVaultTacticalReferenceEngine(
        load_scenario(REFERENCE), policy=Holder()
    ).run()

    selected = [
        e for e in package["event_memory"] if e["event_type"] == "ACTION_SELECTED"
    ]
    assert {e["source"]["system_id"] for e in selected} == {"TAC_ANGEL"}
    assert {e["event_type"] for e in package["event_memory"]} == {
        "ACTION_SELECTED",
        "OBSERVE",
        "SCENARIO_END",
    }
    assert package["evaluation_result"]["destroyed_entities"] == 0


def test_a_scenario_can_name_a_registered_policy():
    register_policy("test_holder_named", lambda rng, params: Holder())
    scenario = load_scenario(REFERENCE)
    scenario["runtime"]["policy"] = {"name": "test_holder_named"}

    package = SkyVaultTacticalReferenceEngine(scenario).run()

    assert package["evaluation_result"]["destroyed_entities"] == 0


def test_without_a_domain_the_engine_is_the_tactical_reference():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE))

    assert engine.domain is None
    assert sorted(engine.resolver.handlers) == sorted(MILITARY_ACTION_TYPES)
    assert type(engine.policy).__name__ == "TacticalReferencePolicy"
    assert engine.actor_system_id == "temporary_tactical_reference_policy"


def test_domains_are_loaded_by_name():
    assert load_domain("military") is MILITARY
    # "city" became a real pack in Phase 14
    with pytest.raises(ValueError, match="unknown domain 'airspace'"):
        load_domain("airspace")


def test_the_world_reads_the_environment_but_never_snapshots_it():
    scenario = load_scenario(REFERENCE)
    scenario = copy.deepcopy(scenario)
    scenario["world_contract"]["environment_state"] = {"terrain": {"rows": ["..."]}}

    world = create_world(scenario)

    assert world.environment == {"terrain": {"rows": ["..."]}}
    assert "environment" not in world.snapshot()
    assert create_world(load_scenario(REFERENCE)).environment == {}


def test_no_core_module_imports_the_military_pack():
    for path in (SRC / "skyvault").rglob("*.py"):
        if "domains" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "military" not in (node.module or ""), path
