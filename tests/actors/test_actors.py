"""Phase 6: actors only submit intent — views, actor types, adapters, participants."""

import ast
import asyncio
import copy
import io
import json
import operator
import random
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

import skyvault.policies as policies
from skyvault.actors.adapters import (
    AEROGRIDAdapter,
    HADESAdapter,
    SKYFOXAdapter,
    STARTXBranchAdapter,
    TACAngelAdapter,
    hades_stand_in,
    startx_stand_in,
)
from skyvault.actors.basic import (
    ConsoleInput,
    ExternalSystemActor,
    HumanInputActor,
    LLMAssistedActor,
    QueueInput,
    RuleBasedActor,
    ScriptedActor,
    parse_suggestion,
    register_client,
)
from skyvault.actors.participants import Participants
from skyvault.actors.queue import ActionQueue
from skyvault.actors.view import (
    EntityView,
    ReadOnlySequence,
    ReadOnlyWorldError,
    WorldView,
    deep_frozen,
    frozen,
)
from skyvault.contracts import ContractError, validate_order, validate_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.observation import load_observer_profile, observe
from skyvault.policies import KNOWN_POLICIES, build_policy, register_policy
from skyvault.scenario_loader import load_scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "skyvault"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "actors"
SCENARIOS = REPO_ROOT / "data" / "scenarios"
REFERENCE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "reference"
    / "scenarios"
    / "tactical_reference_001"
    / "v0.1.json"
)
SQUAD = SCENARIOS / "military_squad_001" / "v0.1.json"
GRID = {"type": "grid", "width": 10, "height": 10, "distance_model": "chebyshev"}


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def unit(entity_id, faction, position, hp=30, status="active", state=None, **caps):
    return {
        "entity_id": entity_id,
        "faction": faction,
        "position": position,
        "state": {"hp": hp, "status": status, **(state or {})},
        "capabilities": caps,
    }


def units(*items):
    return {item["entity_id"]: item for item in items}


def context(actions=("attack", "move", "observe"), space=GRID):
    return {
        "max_ticks": 10,
        "resources": {},
        "available_actions": list(actions),
        "mission": "hold",
        "constraints": [],
        "concealment": None,
        "space": space,
    }


def view(history, observer="TAC_ANGEL", tick=None, actor="r1", **ctx):
    tick = max(history) if tick is None else tick
    profile = load_observer_profile(observer)
    return observe(
        history, tick, profile, {"faction": "RED", "actor_id": actor}, context(**ctx)
    )


def run(path, participants=None, policy=None):
    scenario = load_scenario(path)
    if participants is not None:
        scenario["runtime"]["participants"] = participants
    if policy is not None:
        scenario["runtime"]["policy"] = policy
    return SkyVaultEngine(validate_scenario(scenario)).run()


def selected(package):
    return [e for e in package["event_memory"] if e["event_type"] == "ACTION_SELECTED"]


@pytest.fixture
def world():
    return SkyVaultEngine(load_scenario(SQUAD)).world


# ── acceptance 3: a world policy reads through glass ─────────────────────────


class Cheat:
    """The opening measurement: destroy every enemy without an Action."""

    def decide_action(self, world, actor):
        for other in world.active_entities():
            if other.faction != actor.faction:
                other.state["status"] = "destroyed"
        return None


def test_the_cheating_policy_is_stopped_at_its_first_write():
    engine = SkyVaultEngine(load_scenario(REFERENCE), policy=Cheat())

    with pytest.raises(ReadOnlyWorldError, match="read-only"):
        engine.run()

    assert all(e.is_active() for e in engine.world.entities.values())
    assert not any(
        e.event_type == "ENTITY_DESTROYED" for e in engine.world.event_memory
    )


@pytest.mark.parametrize(
    "write",
    [
        lambda w, u: operator.setitem(u.state, "hp", 0),
        lambda w, u: operator.delitem(u.state, "hp"),
        lambda w, u: setattr(u, "position", (5, 5)),
        lambda w, u: delattr(u, "faction"),
        lambda w, u: operator.setitem(u.capabilities, "attack_range", 99),
        lambda w, u: setattr(w, "tick", 99),
        lambda w, u: delattr(w, "tick"),
        lambda w, u: w.record_event,
        lambda w, u: w.mutate_entity,
        lambda w, u: w.update_entity_state,
        lambda w, u: w.change_resource,
        lambda w, u: w.advance_time,
        lambda w, u: w.event_memory,
        lambda w, u: w.resources.change,
        lambda w, u: setattr(w.space, "width", 1),
        lambda w, u: w.ids.event,
        lambda w, u: operator.setitem(w.rules.require("military")["terrain"], "x", {}),
        lambda w, u: setattr(w.rules, "x", 1),
        lambda w, u: operator.setitem(w.environment["terrain"]["rows"], 0, "...."),
        lambda w, u: u._target_free,
    ],
)
def test_every_write_through_the_view_raises(world, write):
    before = world.snapshot()
    view_ = WorldView(world)

    with pytest.raises((ReadOnlyWorldError, TypeError)):
        write(view_, view_.active_entities()[0])

    assert world.snapshot() == before


def test_every_read_the_policies_use_reaches_the_live_world(world):
    view_ = WorldView(world)
    red = view_.get_entity("red_01")

    assert (view_.tick, view_.world_id, view_.scenario_id) == (
        world.tick,
        world.world_id,
        world.scenario_id,
    )
    assert view_.space.distance((0, 0), (3, 1)) == 3
    assert view_.space.neighbors((0, 0)) == world.space.neighbors((0, 0))
    assert view_.space.is_inside((9, 9)) and not view_.space.is_inside((10, 0))
    assert view_.space.describe() == world.space.describe()
    assert (view_.space.width, view_.space.height) == (10, 10)
    assert view_.resources.snapshot() == world.resources.snapshot()
    assert all(
        view_.resources.amount(r) == world.resources.amount(r)
        for r in world.resources.snapshot()
    )
    assert ("ammo" in view_.resources) == ("ammo" in world.resources)
    # rule and environment lists are seen as tuples, frozen once per run
    assert view_.rules.require("military") == deep_frozen(
        world.rules.require("military")
    )
    assert view_.rules["military"] == deep_frozen(world.rules.as_dict()["military"])
    assert "military" in view_.rules and dict(view_.rules.as_dict())
    with pytest.raises(KeyError, match="Missing rule"):
        view_.rules.require("weather")
    assert view_.environment == deep_frozen(world.environment)
    assert view_.assumptions == world.assumptions
    assert [u.entity_id for u in view_.active_entities()] == [
        u.entity_id for u in world.active_entities()
    ]
    assert set(view_.entities) == set(world.entities)
    assert view_.is_occupied((1, 0)) and not view_.is_occupied((5, 5))
    assert view_.active_factions() == {"RED", "BLUE"}
    assert view_.snapshot() == world.snapshot()
    assert (red.name, red.entity_type, red.faction, red.position) == (
        world.get_entity("red_01").name,
        world.get_entity("red_01").entity_type,
        "RED",
        (1, 0),
    )
    assert red.state["hp"] == world.get_entity("red_01").state["hp"]
    assert red.tags == tuple(world.get_entity("red_01").tags)
    assert red.is_active() and red.snapshot() == world.get_entity("red_01").snapshot()

    issued = view_.ids.action()
    assert issued == "action_0000000001" and world.ids.action() == "action_0000000002"

    world.get_entity("red_01").state["hp"] = 1
    world.get_entity("red_01").state = {"hp": 2, "status": "active"}
    assert red.state["hp"] == 2


def test_each_unit_has_one_view_equal_to_the_unit(world):
    view_ = WorldView(world)
    entity = world.get_entity("red_01")

    first = view_.get_entity("red_01")
    assert first is view_.active_entities()[0] is view_.view_of(entity)
    assert first == entity and first == EntityView(entity)
    assert first != world.get_entity("red_02")
    assert hash(first) == hash(EntityView(entity))
    assert repr(first) == "EntityView('red_01')"


def test_frozen_values_compare_like_the_originals():
    rows = frozen([[1, 2], [3, 4]])
    table = frozen({"a": {"b": [1]}})

    assert isinstance(rows, ReadOnlySequence) and rows == [[1, 2], [3, 4]]
    assert rows == ((1, 2), (3, 4)) and rows == frozen([[1, 2], [3, 4]])
    assert rows[1:] == ((3, 4),) and len(rows) == 2
    assert rows.__eq__(5) is NotImplemented
    assert table["a"]["b"] == [1] and len(table) == 1 and list(table) == ["a"]
    assert frozen((1, 2)) == (1, 2) and frozen({1, 2}) == frozenset({1, 2})
    assert "ReadOnlySequence" in repr(rows) and "ReadOnlyMapping" in repr(table)
    with pytest.raises(ReadOnlyWorldError):
        rows[0] = 1
    with pytest.raises(ReadOnlyWorldError):
        rows.extra = 1
    with pytest.raises(ReadOnlyWorldError):
        table.extra = 1


def test_world_policies_play_exactly_as_before():
    # output hashes of the Phase 5 system (before the read-only view), as
    # renamed by Phase 21: the engine's system id is part of every event
    expected = {
        "tactical_reference_001/v0.1": "7debca2af33238c2",
        "military_squad_001/v0.1": "f49c7eb730cef464",
        "military_urban_001/v0.1": "203bd68cf56c1e80",
        "military_mountain_001/v0.1": "33b6e3aad8fdcbcc",
        "military_junction_001/v0.1": "d79218652b949905",
        "military_urban_001/v0.1+overwatch": "721eea5f8477bdd6",
    }
    for name, prefix in expected.items():
        folder = (
            SCENARIOS
            if name.startswith("military")
            else (REPO_ROOT / "tests" / "fixtures" / "reference" / "scenarios")
        )
        package = run(folder / f"{name}.json")
        assert package["reproducibility"]["output_hash"].startswith(prefix), name


# ── acceptance 1: the tactical reference policy can be unplugged ─────────────


def imports_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
    return found


def test_the_engine_does_not_import_the_tactical_reference_policy():
    assert not any(
        "tactical_reference_policy" in m for m in imports_of(SRC / "engine.py")
    )


def test_with_the_tactical_reference_unplugged_another_policy_still_runs(
    monkeypatch,
):
    # the reference policy is a test fixture now (Phase 21): unregister it
    monkeypatch.delitem(policies._REGISTRY, "tactical_reference", raising=False)

    package = run(REFERENCE, policy={"name": "rule_based"})

    assert {
        e["source"]["system_id"]
        for e in package["event_memory"]
        if e["event_type"] in ("ACTION_SELECTED", "NO_ACTION")
    } == {"rule_based"}
    with pytest.raises(KeyError, match="registered: "):
        run(REFERENCE)


def test_a_scenario_that_names_no_policy_and_no_domain_is_refused():
    """The engine used to fall back to the Phase 0 policy (Phase 21)."""
    from skyvault.contracts import ContractError
    from skyvault.engine import SkyVaultEngine, require_decider

    nobody = load_scenario(REFERENCE)
    del nobody["runtime"]["policy"]

    with pytest.raises(ContractError, match="no runtime.policy and no domain"):
        SkyVaultEngine(nobody)
    with pytest.raises(ContractError, match="no policy to fall back on"):
        require_decider(nobody)
    # handed a policy, it runs: only choosing one needs the scenario to say
    assert SkyVaultEngine(nobody, policy=build_policy("rule_based", random.Random(1)))
    require_decider({**nobody, "domain": "military"})


def test_every_known_policy_name_builds():
    register_client("echo", lambda observation: None)
    params = {"external_system": {"client": "echo"}}

    for name in KNOWN_POLICIES:
        built = build_policy(name, random.Random(1), params.get(name))
        assert built is not None, name


# ── acceptance 2: another actor, no change to the core ───────────────────────


class Waiter:
    """An actor written outside SKYVAULT: watch, never move."""

    observer_profile = "TAC_ANGEL"
    system_id = "OUTSIDER"

    def decide_from_observation(self, observation):
        return {
            "action_type": "observe",
            "target": {"entity_id": observation["viewpoint"]["actor_id"]},
        }


def test_an_actor_registered_outside_the_core_joins_through_participants():
    if "outsider" not in policies.registered_policies():
        register_policy("outsider", lambda rng, params: Waiter())
    participants = [
        {
            "participant_id": "outsider",
            "policy": {"name": "outsider"},
            "controls": {"factions": ["BLUE"]},
        }
    ]

    package = run(REFERENCE, participants)

    by = Counter(
        (
            e["source"]["actor_id"][:3],
            e["source"]["system_id"],
            e["data"]["action_type"],
        )
        for e in selected(package)
    )
    assert {k[1] for k in by if k[0] == "blu"} == {"OUTSIDER"}
    assert {k[2] for k in by if k[0] == "blu"} == {"observe"}
    assert {k[1] for k in by if k[0] == "red"} == {
        "temporary_tactical_reference_policy"
    }


# ── acceptance 4: world_state does not import policy ─────────────────────────


def test_world_state_imports_no_policy_actor_or_engine():
    found = imports_of(SRC / "world_state.py")

    assert not any(
        word in module
        for module in found
        for word in ("polic", "actors", "engine", "tactical_reference")
    ), found


def test_actors_never_import_the_engine():
    for path in (SRC / "actors").glob("*.py"):
        assert not any("engine" in m for m in imports_of(path)), path.name


# ── order contract ───────────────────────────────────────────────────────────


def test_an_order_names_only_what_it_targets():
    order = validate_order({"action_type": "move", "target": {"location": [1, 1]}})

    assert order == {"action_type": "move", "target": {"location": [1, 1]}}


@pytest.mark.parametrize(
    "broken",
    [
        {"target": {"entity_id": "x"}},
        {"action_type": "", "target": {}},
        {"action_type": "move", "target": {"location": [1]}},
        {"action_type": "move", "target": {}, "confidence": 2},
        {"action_type": "move", "target": {}, "action_id": "a1"},
    ],
)
def test_a_broken_order_is_rejected(broken):
    with pytest.raises(ContractError):
        validate_order(broken)


def test_an_observing_actor_that_submits_a_broken_order_is_a_broken_actor():
    class Broken:
        observer_profile = "TAC_ANGEL"

        def decide_from_observation(self, observation):
            return {"action_type": "move", "target": {"location": "nowhere", "x": 1}}

    with pytest.raises(ContractError, match="order"):
        SkyVaultEngine(load_scenario(REFERENCE), policy=Broken()).run()


# ── rule-based ───────────────────────────────────────────────────────────────


def skirmish():
    """r1 at [0,0]; b1 visible at [2,0]; b2 seen at [4,4] on tick 0, gone by tick 1."""
    return {
        0: units(
            unit("r1", "RED", [0, 0], attack_range=1),
            unit("b1", "BLUE", [2, 0]),
            unit("b2", "BLUE", [4, 4]),
        ),
        1: units(
            unit("r1", "RED", [0, 0], attack_range=1),
            unit("b1", "BLUE", [9, 0]),
            unit("b2", "BLUE", [9, 9]),
        ),
    }


def test_rules_are_tried_in_order():
    near = {
        0: units(unit("r1", "RED", [0, 0], attack_range=2), unit("b1", "BLUE", [2, 0]))
    }

    assert RuleBasedActor().decide_from_observation(view(near)) == {
        "action_type": "attack",
        "target": {"entity_id": "b1"},
        "intent": "rule_attack_in_range",
    }
    assert RuleBasedActor(["close_on_visible"]).decide_from_observation(view(near)) == {
        "action_type": "move",
        "target": {"location": [1, 0]},
        "intent": "rule_close_in",
    }
    assert (
        RuleBasedActor(["hold", "attack_in_range"]).decide_from_observation(view(near))
        is None
    )


def test_only_remembered_enemies_are_closed_on_by_close_on_known():
    history = skirmish()
    # tick 1: both moved out of sight (b1 at distance 9, b2 at 9); both remembered
    tick1 = view(history, tick=1)

    assert RuleBasedActor(["attack_in_range"]).decide_from_observation(tick1) is None
    assert RuleBasedActor(["close_on_visible"]).decide_from_observation(tick1) is None
    # nearest remembered: b1 last seen at [2,0] (distance 2) before b2 at [4,4]
    assert RuleBasedActor(["close_on_known"]).decide_from_observation(tick1)[
        "target"
    ] == {"location": [1, 0]}


def test_range_follows_the_grid_distance_model():
    diagonal = {
        0: units(unit("r1", "RED", [0, 0], attack_range=1), unit("b1", "BLUE", [1, 1]))
    }
    manhattan = dict(GRID, distance_model="manhattan")

    assert RuleBasedActor(["attack_in_range"]).decide_from_observation(view(diagonal))
    assert (
        RuleBasedActor(["attack_in_range"]).decide_from_observation(
            view(diagonal, space=manhattan)
        )
        is None
    )


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError, match="unknown rules"):
        RuleBasedActor(["charge"])


def test_a_rule_actor_needs_a_local_view():
    world = {0: units(unit("r1", "RED", [0, 0]))}

    with pytest.raises(ValueError, match="local view"):
        RuleBasedActor().decide_from_observation(view(world, observer="HADES"))


# ── scripted ─────────────────────────────────────────────────────────────────


def test_the_script_runs_and_skyvault_still_judges_each_order():
    orders = fixture("scripted_reference")["orders"]
    participants = [
        {
            "participant_id": "script",
            "policy": {"name": "scripted", "params": {"orders": orders}},
            "controls": {"entity_ids": ["red_001"]},
        }
    ]

    package = run(REFERENCE, participants)
    mine = [
        e for e in package["event_memory"] if e["source"].get("actor_id") == "red_001"
    ]

    assert [
        (e["time"], e["event_type"])
        for e in mine
        if e["time"] <= 4 and e["event_type"] in ("MOVE", "ACTION_REJECTED")
    ] == [(1, "MOVE"), (2, "MOVE"), (3, "MOVE"), (4, "ACTION_REJECTED")]
    assert {
        e["source"]["system_id"] for e in mine if e["event_type"] == "ACTION_SELECTED"
    } == {"scripted"}
    assert [e["event_type"] for e in mine if e["time"] == 5] == ["NO_ACTION"]


def test_a_bad_script_fails_before_the_run():
    with pytest.raises(ValueError, match="two scripted orders"):
        ScriptedActor(
            [{"tick": 1, "entity_id": "r1", "action_type": "move", "target": {}}] * 2
        )
    with pytest.raises(ContractError):
        ScriptedActor([{"tick": 1, "entity_id": "r1", "target": {}}])


# ── human input and the action queue ─────────────────────────────────────────


def test_an_order_submitted_from_another_thread_is_taken_on_its_turn():
    queue = ActionQueue()
    actor = HumanInputActor(QueueInput(queue, timeout=2.0))
    world = {1: units(unit("r1", "RED", [0, 0]))}
    order = {"action_type": "move", "target": {"location": [1, 1]}}

    threading.Timer(0.05, queue.submit_nowait, (1, "r1", order)).start()

    assert actor.decide_from_observation(view(world)) == order
    assert queue.pending() == []


def test_a_person_who_does_not_answer_in_time_holds():
    actor = HumanInputActor(QueueInput(ActionQueue(), timeout=0.05))
    world = {1: units(unit("r1", "RED", [0, 0]))}

    started = time.monotonic()
    assert actor.decide_from_observation(view(world)) is None
    assert time.monotonic() - started < 1.0


def test_the_queue_takes_one_order_per_unit_and_tick_and_accepts_async_submission():
    queue = ActionQueue()
    order = {"action_type": "move", "target": {}}

    asyncio.run(queue.submit(2, "r1", order))
    queue.submit_nowait(1, "r2", order)

    assert queue.pending() == [(1, "r2"), (2, "r1")]
    with pytest.raises(ValueError, match="queued"):
        queue.submit_nowait(2, "r1", order)
    assert queue.take(2, "r1", 0.0) == order
    assert queue.take(2, "r1", 0.0) is None


def test_the_console_shows_the_observation_and_reads_one_order_per_line():
    world = {1: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [9, 9]))}
    out = io.StringIO()
    console = ConsoleInput(
        io.StringIO('{"action_type": "move", "target": {"location": [1, 0]}}\n\n'), out
    )
    actor = HumanInputActor(console)

    assert actor.decide_from_observation(view(world))["target"] == {"location": [1, 0]}
    assert actor.decide_from_observation(view(world)) is None
    assert "tick 1 r1" in out.getvalue() and "b1" not in out.getvalue()


def test_by_name_a_human_actor_reads_the_console_only():
    assert isinstance(
        build_policy("human_input", random.Random(1)).source, ConsoleInput
    )
    with pytest.raises(ValueError, match="console"):
        build_policy("human_input", random.Random(1), {"source": "queue"})


# ── external system ──────────────────────────────────────────────────────────

ORDER = {"action_type": "observe", "target": {"entity_id": "r1"}}
ONE = {1: units(unit("r1", "RED", [0, 0]))}


def test_an_external_system_answers_synchronously_or_as_a_coroutine():
    async def answer(observation):
        return ORDER

    assert (
        ExternalSystemActor(lambda o: ORDER).decide_from_observation(view(ONE)) == ORDER
    )
    assert ExternalSystemActor(answer).decide_from_observation(view(ONE)) == ORDER
    assert (
        ExternalSystemActor(lambda o: None).decide_from_observation(view(ONE)) is None
    )


def test_a_late_external_system_means_standing_still_without_waiting_for_it():
    def slow(observation):
        time.sleep(0.5)
        return ORDER

    async def slow_async(observation):
        await asyncio.sleep(0.5)
        return ORDER

    for client in (slow, slow_async):
        actor = ExternalSystemActor(client, timeout=0.05)
        started = time.monotonic()
        assert actor.decide_from_observation(view(ONE)) is None
        assert time.monotonic() - started < 0.4
        assert (actor.timeouts, actor.errors) == (1, 0)


def test_a_failing_external_system_is_counted_and_the_unit_holds():
    def broken(observation):
        raise ConnectionError("down")

    actor = ExternalSystemActor(broken)

    assert actor.decide_from_observation(view(ONE)) is None
    assert (actor.timeouts, actor.errors) == (0, 1)


def test_external_clients_are_registered_by_name_only():
    register_client("constant", lambda o: ORDER)

    built = build_policy("external_system", random.Random(1), {"client": "constant"})

    assert built.system_id == "constant"
    assert built.decide_from_observation(view(ONE)) == ORDER
    with pytest.raises(ValueError, match="already registered"):
        register_client("constant", lambda o: None)
    with pytest.raises(KeyError, match="no client"):
        build_policy("external_system", random.Random(1), {"client": "missing"})


# ── LLM-assisted ─────────────────────────────────────────────────────────────

REPLIES = fixture("llm_replies")["replies"]
CONTACT = {
    1: units(
        unit("r1", "RED", [3, 3], attack_range=1),
        unit("b3", "BLUE", [3, 4]),
    )
}


def contact_view():
    world = copy.deepcopy(CONTACT)
    world[1]["blue_003"] = dict(world[1].pop("b3"), entity_id="blue_003")
    return view(world)


def test_a_usable_suggestion_is_followed():
    seen = []
    actor = LLMAssistedActor(
        lambda prompt: seen.append(prompt) or REPLIES["valid_attack"]
    )

    order = actor.decide_from_observation(contact_view())

    assert order == {
        "action_type": "attack",
        "target": {"entity_id": "blue_003"},
        "intent": "llm_engage",
    }
    assert (actor.suggestions, actor.fallbacks) == (1, 0)
    assert "unit r1 at tick 1" in seen[0] and "attack, move, observe" in seen[0]


@pytest.mark.parametrize("reply", ["malformed", "illegal_action", "unknown_target"])
def test_a_bad_suggestion_falls_back_to_the_rules(reply):
    actor = LLMAssistedActor(lambda prompt: REPLIES[reply])

    order = actor.decide_from_observation(contact_view())

    assert order == {
        "action_type": "attack",
        "target": {"entity_id": "blue_003"},
        "intent": "rule_attack_in_range",
    }
    assert (actor.suggestions, actor.fallbacks) == (0, 1)


def test_a_suggestion_to_hold_is_followed_and_no_client_means_rules():
    assert (
        LLMAssistedActor(lambda p: REPLIES["hold"]).decide_from_observation(
            contact_view()
        )
        is None
    )
    assert (
        LLMAssistedActor().decide_from_observation(contact_view())["intent"]
        == "rule_attack_in_range"
    )


def test_the_first_json_object_in_a_reply_is_the_suggestion():
    assert parse_suggestion('noise {bad} then {"a": 1} {"b": 2}') == {"a": 1}
    assert parse_suggestion("[1, 2] no object") is None


def test_by_name_an_llm_actor_uses_a_registered_client():
    register_client("canned", lambda prompt: REPLIES["valid_attack"])

    built = build_policy("llm_assisted", random.Random(1), {"client": "canned"})

    assert built.decide_from_observation(contact_view())["intent"] == "llm_engage"
    assert build_policy("llm_assisted", random.Random(1)).client is None


# ── adapters ─────────────────────────────────────────────────────────────────


def test_tac_angel_answers_translate_into_orders():
    near = view({0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [1, 0]))})

    def says(answer):
        return TACAngelAdapter(lambda o: answer).decide_from_observation(near)

    assert says({"maneuver": "engage", "target": "b1"})["target"] == {"entity_id": "b1"}
    assert says({"maneuver": "advance", "waypoint": [2, 2]})["target"] == {
        "location": [2, 2]
    }
    assert says({"maneuver": "hold"}) is None
    with pytest.raises(ValueError, match="maneuver"):
        says({"maneuver": "flank"})


def test_the_tac_angel_stand_in_engages_advances_or_holds():
    adapter = TACAngelAdapter()

    assert (
        adapter.decide_from_observation(
            view({0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [1, 0]))})
        )["action_type"]
        == "attack"
    )
    assert adapter.decide_from_observation(
        view({0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [3, 0]))})
    )["target"] == {"location": [1, 0]}
    assert (
        adapter.decide_from_observation(
            view({0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [9, 9]))})
        )
        is None
    )


def both(history, other, tick=None, **ctx):
    return {
        other: view(history, observer=other, tick=tick, **ctx),
        "TAC_ANGEL": view(history, tick=tick, **ctx),
    }


def test_startx_sees_only_its_trends_and_each_unit_carries_out_its_stance():
    world = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [2, 0]))}
    handed = []

    def stance(value):
        def system(observation):
            handed.append(observation)
            return {"stance": value}

        return STARTXBranchAdapter(system).decide_from_observations(
            both(world, "STARTX")
        )

    assert stance("press")["target"] == {"location": [1, 0]}
    assert stance("hold") is None
    assert stance("withdraw")["target"] == {"location": [-1, 0]}
    assert all(o["observer_id"] == "STARTX" for o in handed)
    assert all("position" not in json.dumps(o) for o in handed)
    with pytest.raises(ValueError, match="stance"):
        stance("surrender")


def test_withdrawing_with_no_enemy_known_stands_still():
    world = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [9, 9]))}

    adapter = STARTXBranchAdapter(lambda o: {"stance": "withdraw"})

    assert adapter.decide_from_observations(both(world, "STARTX")) is None


@pytest.mark.parametrize(
    ("own", "change", "stance"),
    [
        (0.3, 0.0, "withdraw"),
        (0.34, -0.3, "hold"),
        (0.8, -0.2, "hold"),
        (0.8, -0.19, "press"),
    ],
)
def test_the_startx_stand_in_thresholds(own, change, stance):
    observation = {
        "visible_world_state": {
            "summary": {
                "own": {"hp_ratio": own},
                "trend": {"own_hp_ratio_change": change},
            }
        }
    }

    assert startx_stand_in(observation) == {"stance": stance}


def test_hades_intercepts_in_range_or_closes_and_otherwise_keeps_watch():
    near = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [1, 0]))}
    far = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [4, 0]))}

    def answer(history, reply, **ctx):
        return HADESAdapter(lambda o: reply).decide_from_observations(
            both(history, "HADES", **ctx)
        )

    assert (
        answer(near, {"response": "intercept", "threat": "b1"})["action_type"]
        == "attack"
    )
    assert answer(far, {"response": "intercept", "threat": "b1"})["target"] == {
        "location": [1, 0]
    }
    assert answer(far, {"response": "monitor"})["action_type"] == "observe"
    assert (
        answer(far, {"response": "monitor"}, actions=("move", "wait"))["action_type"]
        == "wait"
    )
    assert answer(far, {"response": "monitor"}, actions=("move",)) is None
    assert (
        answer(far, {"response": "intercept", "threat": "b9"})["action_type"]
        == "observe"
    )
    with pytest.raises(ValueError, match="response"):
        answer(far, {"response": "panic"})


def test_the_hades_stand_in_prefers_threats_to_this_unit_then_to_the_side():
    def risks(*pairs):
        return {
            "viewpoint": {"actor_id": "r1"},
            "visible_world_state": {
                "known_risks": [{"entity_id": e, "nearest_own": o} for e, o in pairs]
            },
        }

    assert hades_stand_in(risks(("b1", "r2"), ("b2", "r1"))) == {
        "response": "intercept",
        "threat": "b2",
    }
    assert hades_stand_in(risks(("b1", "r2"), ("b2", "r3"))) == {
        "response": "intercept",
        "threat": "b1",
    }
    assert hades_stand_in(risks()) == {"response": "monitor"}


def test_aerogrid_spreads_units_out_while_coverage_is_thin():
    small = {"type": "grid", "width": 20, "height": 20, "distance_model": "chebyshev"}
    crowded = {
        0: units(
            unit("r1", "RED", [5, 5], sensor_range=1),
            unit("r2", "RED", [6, 5], sensor_range=1),
            unit("b1", "BLUE", [5, 6]),
        )
    }

    thin = AEROGRIDAdapter().decide_from_observations(
        both(crowded, "AEROGRID", space=small)
    )
    covered = AEROGRIDAdapter(threshold=0.0).decide_from_observations(
        both(crowded, "AEROGRID", space=small)
    )

    assert thin == {
        "action_type": "move",
        "target": {"location": [4, 5]},
        "intent": "aerogrid_reposition",
    }
    assert covered["action_type"] == "attack"
    with pytest.raises(ValueError, match="reposition"):
        AEROGRIDAdapter(lambda o: {"reposition": "maybe"}).decide_from_observations(
            both(crowded, "AEROGRID", space=small)
        )


def test_skyfox_flies_its_route_and_lands_when_energy_runs_low():
    adapter = SKYFOXAdapter(route=[[2, 0], [2, 2]], energy_floor=10)

    def at(position, energy=50):
        world = {1: units(unit("r1", "RED", position, state={"energy": energy}))}
        order = adapter.decide_from_observation(view(world, observer="SKYFOX"))
        return None if order is None else order["target"]["location"]

    assert at([0, 0]) == [1, 0]
    assert at([2, 0]) == [2, 1]  # first waypoint reached: on to the second
    assert at([2, 2]) == [2, 1]  # second reached: the route starts again
    assert at([2, 1], energy=5) is None
    assert (
        SKYFOXAdapter().decide_from_observation(
            view({1: units(unit("r1", "RED", [0, 0]))}, observer="SKYFOX")
        )
        is None
    )
    with pytest.raises(ValueError, match="waypoint"):
        SKYFOXAdapter(system=lambda o: {}).decide_from_observation(
            view(ONE, observer="SKYFOX")
        )


def test_a_drone_standing_on_its_only_waypoint_holds():
    adapter = SKYFOXAdapter(route=[[0, 0]])

    assert adapter.decide_from_observation(view(ONE, observer="SKYFOX")) is None


# ── participants ─────────────────────────────────────────────────────────────


class Unit:
    def __init__(self, entity_id, faction):
        self.entity_id, self.faction = entity_id, faction


SIDES = [Unit("r1", "RED"), Unit("r2", "RED"), Unit("b1", "BLUE")]


def slot(pid, factions=(), ids=(), name="rule_based"):
    return {
        "participant_id": pid,
        "policy": {"name": name},
        "controls": {"factions": list(factions), "entity_ids": list(ids)},
    }


def built(choice):
    return build_policy(choice["name"], random.Random(1), choice.get("params"))


def test_each_unit_is_decided_by_the_participant_controlling_it():
    table = Participants([slot("reds", factions=["RED"])], SIDES, built)

    assert table.for_entity("r1").participant_id == "reds"
    assert table.for_entity("r2").system_id == "rule_based"
    assert table.for_entity("b1") is None
    assert [s.participant_id for s in table.slots()] == ["reds"]


def test_a_policy_without_a_system_id_is_recorded_under_the_participant():
    class Anonymous:
        def decide_action(self, world, actor):
            return None

    table = Participants([slot("anon", ids=["b1"])], SIDES, lambda c: Anonymous())

    assert table.for_entity("b1").system_id == "anon"


@pytest.mark.parametrize(
    ("chosen", "message"),
    [
        (
            [slot("a", factions=["RED"]), slot("b", ids=["r2"])],
            "controlled by both a and b",
        ),
        ([slot("a", ids=["x9"])], "unknown units"),
    ],
)
def test_a_unit_claimed_twice_or_a_unit_that_does_not_exist_is_refused(chosen, message):
    with pytest.raises(ValueError, match=message):
        Participants(chosen, SIDES, built)


def test_the_scenario_contract_checks_participants():
    scenario = load_scenario(REFERENCE)
    scenario["runtime"]["participants"] = [
        slot("a", factions=["RED"]),
        slot("a", factions=["BLUE"]),
    ]
    with pytest.raises(ContractError, match="participant_id must be unique"):
        validate_scenario(scenario)
    scenario["runtime"]["participants"] = [slot("a")]
    with pytest.raises(ContractError, match="at least one faction or unit"):
        validate_scenario(scenario)


def test_the_squad_fixture_mixes_three_deciders_each_on_its_own_units():
    package = run(SQUAD, fixture("participants_squad")["participants"])

    deciders = {}
    for event in package["event_memory"]:
        if event["event_type"] in ("ACTION_SELECTED", "NO_ACTION"):
            deciders.setdefault(event["source"]["actor_id"], set()).add(
                event["source"]["system_id"]
            )

    assert (
        deciders["red_01"] == deciders["red_02"] == deciders["red_03"] == {"TAC_ANGEL"}
    )
    assert deciders["red_04"] == {"HADES"}
    assert all(
        deciders[b] == {"military_baseline"}
        for b in ("blue_01", "blue_02", "blue_03", "blue_04")
    )


def test_the_reference_fixture_puts_fog_on_one_side_only():
    package = run(REFERENCE, fixture("participants_reference")["participants"])
    first_moves = {
        e["source"]["system_id"]: e["time"] for e in reversed(selected(package))
    }

    # RED decides from its observation and sees nothing until BLUE comes near;
    # BLUE's tactical reference reads the world and moves at once
    assert first_moves["blue_reference"] == 1
    assert first_moves["rule_based"] > 1
    no_action = [
        e
        for e in package["event_memory"]
        if e["event_type"] == "NO_ACTION" and e["time"] == 1
    ]
    assert {e["source"]["system_id"] for e in no_action} == {"rule_based"}


def test_a_multi_view_actor_gets_every_view_of_the_same_moment():
    seen = []

    class TwoEyes:
        observer_profiles = ("STARTX", "TAC_ANGEL")

        def decide_from_observations(self, observations):
            seen.append(observations)
            return None

    SkyVaultEngine(load_scenario(REFERENCE), policy=TwoEyes()).run()

    assert seen and all(set(o) == {"STARTX", "TAC_ANGEL"} for o in seen)
    assert all(o["STARTX"]["time"] == o["TAC_ANGEL"]["time"] for o in seen)
    assert all(
        o["STARTX"]["uncertainty"]["observed_at"] == max(0, o["STARTX"]["time"] - 1)
        for o in seen
    )


@pytest.mark.parametrize(
    "name",
    [
        "rule_based",
        "tac_angel_adapter",
        "startx_branch_adapter",
        "hades_adapter",
        "aerogrid_adapter",
        "llm_assisted",
    ],
)
def test_every_actor_type_completes_a_military_run(name):
    package = run(SCENARIOS / "military_urban_001" / "v0.1.json", policy={"name": name})

    assert package["evaluation_result"]["event_count"] == len(package["event_memory"])
    assert selected(package)
