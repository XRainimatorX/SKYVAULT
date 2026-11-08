"""Phase 3 acceptance: an action changes the world only through its Consequence."""

import ast
import copy
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

for path in (SRC_PATH, REPO_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from reference_trace import digest, reference_package, trace  # noqa: E402

from skyvault.action import Action, ActionAttempt, ActionTarget
from skyvault.actions import (
    CORE_HANDLERS,
    MILITARY_ACTION_TYPES,
    ActionContext,
    ActionResolver,
    ActionValidation,
    action_cost,
    apply_consequence,
    check_resources,
    handlers_for,
)
from skyvault.consequence import Consequence, DirectEffect
from skyvault.contracts import validate_action, validate_consequence, validate_scenario
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.runtime import rebuild_world
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def reference_world():
    return create_world(load_scenario(REFERENCE_SCENARIO))


def resolver(world=None, seed: int = 0, types=MILITARY_ACTION_TYPES) -> ActionResolver:
    return ActionResolver(
        handlers_for(types), ActionContext(random.Random(seed), "test")
    )


def move(actor_id: str, location) -> Action:
    return Action("action_move", actor_id, "move", ActionTarget(location=location))


def attack(actor_id: str, target_id: str) -> Action:
    return Action(
        "action_attack", actor_id, "attack", ActionTarget(entity_id=target_id)
    )


class AlwaysHits(random.Random):
    def random(self) -> float:
        return 0.0


class AlwaysMisses(random.Random):
    def random(self) -> float:
        return 1.0


def place_adjacent(world, actor_id: str, target_id: str) -> None:
    world.get_entity(actor_id).position = (4, 4)
    world.get_entity(target_id).position = (4, 5)


# ── the reference run is unchanged, event by event ──────────────────────────


def test_reference_run_matches_the_committed_trace():
    committed = fixture("reference_trace")
    package = reference_package()

    assert trace(package) == committed["trace"]
    assert digest(package) == committed["digest"]


# ── acceptance 1: an action no longer changes the world directly ────────────


@pytest.mark.parametrize("rng", [AlwaysHits(), AlwaysMisses()], ids=["hit", "miss"])
def test_resolving_an_attack_reads_the_world_and_changes_nothing(rng):
    world = reference_world()
    place_adjacent(world, "red_001", "blue_001")
    before = copy.deepcopy(world.snapshot())
    handler = CORE_HANDLERS["attack"]

    consequence = handler.resolve(
        world, attack("red_001", "blue_001"), ActionContext(rng)
    )

    assert consequence.accepted
    assert world.snapshot() == before
    assert world.event_memory == []


def test_resolving_a_move_reads_the_world_and_changes_nothing():
    world = reference_world()
    before = copy.deepcopy(world.snapshot())

    consequence = CORE_HANDLERS["move"].resolve(
        world, move("red_001", (1, 1)), ActionContext(random.Random(0))
    )

    assert consequence.effects[0].changes["position"] == (1, 1)
    assert world.snapshot() == before
    assert world.event_memory == []


MUTATING_CALLS = {
    "record_event",
    "record_transition",
    "mutate_entity",
    "change_resource",
    "update_entity_state",
    "advance_time",
}


def handler_mutations(source: str) -> list[str]:
    """Every place in source that would change the world or record an event."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MUTATING_CALLS:
                found.append(node.func.attr)
            if node.func.attr in {"update", "pop", "clear", "setdefault"}:
                owner = node.func.value
                if isinstance(owner, ast.Attribute) and owner.attr == "state":
                    found.append(f"state.{node.func.attr}")
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in {
                    "position",
                    "state",
                    "tick",
                }:
                    found.append(f"assign .{target.attr}")
                if isinstance(target, ast.Subscript):
                    owner = target.value
                    if isinstance(owner, ast.Attribute) and owner.attr == "state":
                        found.append("assign .state[...]")
    return found


def test_handlers_never_change_the_world_or_record_events():
    source = (SRC_PATH / "skyvault" / "actions" / "handlers.py").read_text(
        encoding="utf-8"
    )

    assert handler_mutations(source) == []


@pytest.mark.parametrize(
    "line",
    [
        "target.state['hp'] = 0",
        "actor.position = (0, 0)",
        "target.state.update({'hp': 0})",
        "world.record_event(event_type='MOVE')",
        "world.change_resource('fuel', -1)",
        "world.mutate_entity('a', {}, 'MOVE')",
    ],
)
def test_the_handler_check_catches_each_kind_of_mutation(line):
    assert handler_mutations(f"def resolve(world, actor, target):\n    {line}\n")


# ── acceptance 2: an action must be validated first ─────────────────────────


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (move("red_001", None), "Move action missing target_position"),
        (move("red_001", (10, 0)), "Move target outside world boundary"),
        (move("red_001", (1, 0)), "Move target occupied"),
        (move("red_001", (2, 2)), "Move target out of range: distance=2, range=1"),
        (
            Action("action_x", "red_001", "attack"),
            "Attack action missing target_entity_id",
        ),
        (attack("red_001", "blue_001"), "Target out of range: distance=9, range=1"),
        (Action("action_x", "red_001", "dance"), "Unsupported action type: dance"),
    ],
)
def test_a_refused_action_changes_nothing_and_records_nothing(action, reason):
    world = reference_world()
    before = copy.deepcopy(world.snapshot())

    consequence = resolver().execute(world, action)

    assert not consequence.accepted
    assert consequence.reason == reason
    assert consequence.effects == []
    assert world.snapshot() == before
    assert world.event_memory == []
    validate_consequence(consequence.to_dict())


def test_an_inactive_actor_is_refused():
    world = reference_world()
    world.get_entity("red_001").state["status"] = "destroyed"

    consequence = resolver().execute(world, move("red_001", (1, 0)))

    assert consequence.reason == "Actor is not active"
    assert world.event_memory == []


def test_an_unknown_actor_is_a_programming_error_not_a_refusal():
    with pytest.raises(KeyError, match="ghost"):
        resolver().execute(reference_world(), move("ghost", (1, 0)))


# ── acceptance 3: only a consequence mutates the world ──────────────────────


def test_applying_a_rejected_consequence_raises():
    world = reference_world()
    action = move("red_001", (1, 0))

    with pytest.raises(ValueError, match="rejected"):
        apply_consequence(world, Consequence.rejected(action.action_id, "no"), action)

    assert world.event_memory == []


def test_applying_another_actions_consequence_raises():
    world = reference_world()
    consequence = Consequence("action_other", True, "ok")

    with pytest.raises(ValueError, match="does not belong"):
        apply_consequence(world, consequence, move("red_001", (1, 0)))


def test_a_state_effect_is_refused_until_the_environment_is_modelled():
    world = reference_world()
    action = Action("action_s", "red_001", "wait")
    consequence = Consequence(
        action.action_id, True, "ok", effects=[DirectEffect("state", "WAIT")]
    )

    with pytest.raises(NotImplementedError, match="environment"):
        apply_consequence(world, consequence, action)


def test_applying_a_move_changes_the_actor_and_records_its_snapshots():
    world = reference_world()
    action = move("red_001", (1, 1))

    consequence = resolver().execute(world, action)

    actor = world.get_entity("red_001")
    assert consequence.accepted
    assert actor.position == (1, 1)
    assert actor.state["last_action"] == "move"
    [event] = [event.to_dict() for event in world.event_memory]
    assert event["event_type"] == "MOVE"
    assert event["before_state"]["position"] == [0, 0]
    assert event["after_state"]["position"] == [1, 1]
    assert event["data"] == {"from": [0, 0], "to": [1, 1]}
    assert event["affected"]["locations"] == [[0, 0], [1, 1]]


# ── acceptance 4: every mutation generates an event ─────────────────────────


def test_a_fatal_hit_records_the_hit_then_the_destruction_as_a_chain_reaction():
    world = reference_world()
    place_adjacent(world, "red_001", "blue_001")
    world.get_entity("blue_001").state["hp"] = 4
    hits = ActionResolver(handlers_for(("attack",)), ActionContext(AlwaysHits(), "t"))

    consequence = hits.execute(world, attack("red_001", "blue_001"))

    hit, destroyed = [event.to_dict() for event in world.event_memory]
    assert [hit["event_type"], destroyed["event_type"]] == [
        "ATTACK",
        "ENTITY_DESTROYED",
    ]
    assert hit["data"] == {"damage": 10, "hp_before": 4, "hp_after": -6, "distance": 1}
    assert destroyed["before_state"] == hit["before_state"]
    assert destroyed["after_state"] == hit["after_state"]
    assert destroyed["after_state"]["state"]["status"] == "destroyed"
    assert destroyed["causal_links"]["caused_by"] == [hit["event_id"]]
    [reaction] = consequence.to_dict()["chain_reactions"]
    assert reaction == {
        "event_id": destroyed["event_id"],
        "cause": "ATTACK:blue_001",
        "effect": "ENTITY_DESTROYED",
    }


def test_a_miss_records_one_event_and_changes_nothing():
    world = reference_world()
    place_adjacent(world, "red_001", "blue_001")
    target_before = world.get_entity("blue_001").snapshot()
    misses = ActionResolver(handlers_for(("attack",)), ActionContext(AlwaysMisses()))

    consequence = misses.execute(world, attack("red_001", "blue_001"))

    [event] = [event.to_dict() for event in world.event_memory]
    assert consequence.reason == "Attack missed"
    assert event["event_type"] == "MISS"
    assert event["before_state"] == event["after_state"] == target_before


def test_every_effect_and_chain_reaction_is_one_event_in_the_reference_run():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))
    applied = []
    original = engine.resolver.execute

    def counting(world, action):
        start = len(world.event_memory)
        consequence = original(world, action)
        applied.append((consequence, len(world.event_memory) - start))
        return consequence

    engine.resolver.execute = counting
    engine.run()

    assert applied
    for consequence, recorded in applied:
        expected = len(consequence.effects) + len(consequence.chain_reactions)
        assert recorded == (expected if consequence.accepted else 0)


# ── acceptance 5: every event traces back to its action ─────────────────────


def test_every_event_an_action_caused_carries_its_action_id():
    package = reference_package()
    selected = {
        event["source"]["action_id"]: event["source"]["actor_id"]
        for event in package["event_memory"]
        if event["event_type"] == "ACTION_SELECTED"
    }

    for event in package["event_memory"]:
        if event["event_type"] in {"NO_ACTION", "SCENARIO_END"}:
            assert event["source"]["action_id"] is None
            continue
        action_id = event["source"]["action_id"]
        assert action_id in selected
        assert event["source"]["actor_id"] == selected[action_id]


def test_event_sourcing_still_rebuilds_the_final_world():
    package = reference_package()

    rebuilt = rebuild_world(package["initial_world_state"], package["event_memory"])

    assert rebuilt == package["final_world_state"]


# ── resources and costs ──────────────────────────────────────────────────────


def logistics_world():
    return create_world(validate_scenario(fixture("scenario_logistics")))


def test_the_rule_set_cost_wins_over_the_declared_resources():
    world = logistics_world()
    declared = Action("a", "truck_1", "repair", required_resources={"fuel": 9})
    plain = Action("b", "truck_1", "observe", required_resources={"fuel": 2})

    assert action_cost(world, declared) == {"spare_parts": 1.0}
    assert action_cost(world, plain) == {"fuel": 2.0}


def test_a_shortfall_is_refused_with_both_amounts():
    world = logistics_world()

    assert check_resources(world, {"fuel": 51}) == ActionValidation.reject(
        "Insufficient fuel: have 50.0, need 51"
    )
    assert check_resources(world, {"water": 1}).reason == (
        "Insufficient water: have 0.0, need 1"
    )
    assert check_resources(world, {"fuel": 50}).valid


def test_a_charged_move_spends_the_resource_before_moving():
    world = logistics_world()
    action = Action(
        "action_drive",
        "truck_1",
        "move",
        ActionTarget(location="junction"),
        required_resources={"fuel": 5},
    )
    world.get_entity("squad_1").position = "front"

    consequence = resolver().execute(world, action)

    events = [event.to_dict() for event in world.event_memory]
    assert [event["event_type"] for event in events] == ["RESOURCE_CHANGED", "MOVE"]
    assert events[0]["after_state"] == {"resource_id": "fuel", "amount": 45.0}
    assert events[0]["source"]["action_id"] == "action_drive"
    assert events[1]["data"] == {"from": "depot", "to": "junction"}
    assert consequence.to_dict()["direct_effects"]["resource_changes"] == [
        {"resource_id": "fuel", "delta": -5.0, "event_type": "RESOURCE_CHANGED"}
    ]


def test_an_unaffordable_action_is_refused_and_records_nothing():
    world = logistics_world()
    action = Action(
        "action_drive",
        "truck_1",
        "move",
        ActionTarget(location="junction"),
        required_resources={"fuel": 500},
    )
    world.get_entity("squad_1").position = "front"

    consequence = resolver().execute(world, action)

    assert consequence.reason == "Insufficient fuel: have 50.0, need 500.0"
    assert world.event_memory == []
    assert world.resources.amount("fuel") == 50.0


# ── data shapes ──────────────────────────────────────────────────────────────


def test_action_attempt_is_the_action_and_serialises_to_its_contract():
    action = ActionAttempt("a1", "truck_1", "move", ActionTarget(location=(1, 2)))

    recorded = validate_action(action.to_dict())

    assert ActionAttempt is Action
    assert recorded["target"] == {
        "entity_id": None,
        "location": [1, 2],
        "system_id": None,
    }
    assert recorded["required_resources"] == {}
    assert recorded["confidence"] == 1.0


def test_the_tactical_policy_fills_every_section_6_field():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))
    place_adjacent(engine.world, "red_001", "blue_001")
    for other in ("blue_002", "blue_003"):
        engine.world.get_entity(other).state["status"] = "destroyed"

    action = engine.policy.decide_action(
        engine.world, engine.world.get_entity("red_001")
    )

    recorded = validate_action(action.to_dict())
    assert recorded["action_type"] == "attack"
    assert recorded["confidence"] == 0.8
    assert recorded["expected_effect"] == "hp_change"


def test_mutate_entity_refuses_an_unknown_change_key():
    world = reference_world()

    with pytest.raises(ValueError, match="unknown entity change keys"):
        world.mutate_entity("red_001", {"hp": 1}, "MOVE")

    assert world.event_memory == []


def test_the_military_line_registers_five_types_and_the_engine_uses_it():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))

    assert MILITARY_ACTION_TYPES == ("move", "attack", "observe", "supply", "repair")
    assert set(engine.resolver.handlers) <= set(MILITARY_ACTION_TYPES)
    assert not hasattr(engine, "resolve_move")
    assert not hasattr(engine, "resolve_attack")


@pytest.mark.parametrize(
    "module", sorted((SRC_PATH / "skyvault" / "actions").glob("*.py"))
)
def test_actions_never_import_the_engine_a_policy_or_an_exporter(module):
    forbidden = {
        "engine",
        "tactical_reference_policy",
        "timeline",
        "replay",
        "entity_history",
        "causal_chain",
    }
    names = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))

    assert not names & forbidden
