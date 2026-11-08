"""Phase 2 acceptance 6: the world at any time, rebuilt from event memory."""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_scenario
from skyvault.engine import SNAPSHOT_INTERVAL, SkyVaultTacticalReferenceEngine
from skyvault.replay import build_replay_state_at_tick
from skyvault.runtime import SnapshotStore, rebuild_world
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"


@pytest.fixture(scope="module")
def run():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))
    package = engine.run()
    return engine, package


def ticks_of(package) -> list[int]:
    return sorted({event["time"] for event in package["event_memory"]})


# ── rebuilding the reference run ─────────────────────────────────────────────


def test_rebuilding_to_the_end_gives_the_final_world_state(run):
    _, package = run

    rebuilt = rebuild_world(package["initial_world_state"], package["event_memory"])

    assert rebuilt == package["final_world_state"]


def test_rebuilding_at_every_tick_matches_the_replay_exporter(run):
    _, package = run
    replay = build_replay_state_at_tick(
        package["initial_world_state"],
        package["event_memory"],
        package["final_world_state"],
    )

    for tick in [0, *ticks_of(package)]:
        rebuilt = rebuild_world(
            package["initial_world_state"], package["event_memory"], at_time=tick
        )
        assert rebuilt["tick"] == tick
        assert rebuilt["entities"] == replay["states"][str(tick)]["world_state"]


def test_rebuilding_at_time_zero_gives_the_initial_world_state(run):
    _, package = run

    rebuilt = rebuild_world(
        package["initial_world_state"], package["event_memory"], at_time=0
    )

    assert rebuilt == package["initial_world_state"]


def test_a_rebuild_shows_who_was_destroyed_by_then(run):
    _, package = run
    destroyed_at = {
        event["target_entity_id"]: event["time"]
        for event in package["event_memory"]
        if event["event_type"] == "ENTITY_DESTROYED"
    }
    entity_id, tick = min(destroyed_at.items(), key=lambda item: item[1])

    before = rebuild_world(
        package["initial_world_state"], package["event_memory"], at_time=tick - 1
    )
    after = rebuild_world(
        package["initial_world_state"], package["event_memory"], at_time=tick
    )

    assert before["entities"][entity_id]["state"]["status"] == "active"
    assert after["entities"][entity_id]["state"]["status"] == "destroyed"


def test_rebuild_never_mutates_its_inputs(run):
    _, package = run
    initial = copy.deepcopy(package["initial_world_state"])
    events = copy.deepcopy(package["event_memory"])

    rebuild_world(package["initial_world_state"], package["event_memory"])

    assert package["initial_world_state"] == initial
    assert package["event_memory"] == events


# ── snapshots ────────────────────────────────────────────────────────────────


def test_engine_keeps_a_snapshot_every_interval(run):
    engine, package = run

    assert SNAPSHOT_INTERVAL == 5
    assert engine.snapshots.ticks() == [0, 5, 10]
    assert engine.snapshots.latest_at_or_before(0) == package["initial_world_state"]


@pytest.mark.parametrize("at_time", [5, 6, 9, 10])
def test_a_rebuild_from_a_snapshot_equals_one_from_time_zero(run, at_time):
    engine, package = run
    start = engine.snapshots.latest_at_or_before(at_time)

    from_snapshot = rebuild_world(start, package["event_memory"], at_time=at_time)
    from_scratch = rebuild_world(
        package["initial_world_state"], package["event_memory"], at_time=at_time
    )

    assert start["tick"] > 0
    assert from_snapshot == from_scratch


def test_snapshot_store_keeps_only_ticks_on_the_interval():
    store = SnapshotStore(interval=3)

    kept = [store.record(tick, {"tick": tick}) for tick in range(7)]

    assert kept == [True, False, False, True, False, False, True]
    assert store.ticks() == [0, 3, 6]
    assert len(store) == 3
    assert store.record(4, {"tick": 4}, force=True)
    assert store.latest_at_or_before(5) == {"tick": 4}


def test_snapshot_store_hands_out_copies():
    store = SnapshotStore(interval=1)
    snapshot = {"tick": 0, "entities": {"a": {"hp": 1}}}
    store.record(0, snapshot)
    snapshot["entities"]["a"]["hp"] = 0

    kept = store.latest_at_or_before(0)
    kept["entities"]["a"]["hp"] = 99

    assert store.latest_at_or_before(0) == {"tick": 0, "entities": {"a": {"hp": 1}}}


def test_snapshot_store_has_nothing_before_its_first_snapshot():
    store = SnapshotStore(interval=5)
    store.record(5, {"tick": 5})

    assert store.latest_at_or_before(4) is None


def test_snapshot_interval_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        SnapshotStore(interval=0)


# ── resources and graph worlds ───────────────────────────────────────────────


def test_resource_changes_rebuild_on_a_graph_world():
    with (FIXTURES / "scenario_graph.json").open(encoding="utf-8") as file:
        world = create_world(validate_scenario(json.load(file)))
    initial = world.snapshot()

    world.clock.schedule(3, "load")  # type: ignore[attr-defined]
    world.clock.schedule(8, "unload")  # type: ignore[attr-defined]
    world.advance_time()
    world.change_resource("fuel", -40, actor_id="convoy_1")
    world.update_entity_state("convoy_1", {"status": "moving"})
    world.advance_time()
    world.change_resource("supply", 5)
    events = [event.to_dict() for event in world.event_memory]

    at_3 = rebuild_world(initial, events, at_time=3)
    at_end = rebuild_world(initial, events)

    assert at_3["resources"] == {"fuel": 60.0, "supply": 20.0}
    assert at_3["entities"]["convoy_1"]["state"]["status"] == "moving"
    assert at_3["entities"]["convoy_1"]["position"] == "A"
    assert at_end == world.snapshot()
    assert at_end["tick"] == 8


# ── layering ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("module", ["sourcing.py", "snapshots.py"])
def test_sourcing_and_snapshots_import_nothing_from_the_project(module):
    source = (SRC_PATH / "skyvault" / "runtime" / module).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.level, node.module))
        elif isinstance(node, ast.Import):
            imported.update((0, alias.name) for alias in node.names)

    assert all(level == 0 for level, _ in imported)
    assert not any(name and name.startswith("skyvault") for _, name in imported)


FORBIDDEN = {
    "engine",
    "tactical_reference_policy",
    "timeline",
    "replay",
    "entity_history",
    "causal_chain",
}


@pytest.mark.parametrize(
    "path",
    sorted((SRC_PATH / "skyvault" / "runtime").glob("*.py")),
    ids=lambda path: path.name,
)
def test_runtime_never_imports_the_engine_a_policy_or_an_exporter(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))

    assert not names & FORBIDDEN


def test_events_at_the_starting_tick_are_replayed():
    with (FIXTURES / "scenario_graph.json").open(encoding="utf-8") as file:
        world = create_world(validate_scenario(json.load(file)))
    initial = world.snapshot()

    world.update_entity_state("convoy_1", {"status": "loading"})
    world.change_resource("fuel", -10)
    events = [event.to_dict() for event in world.event_memory]

    assert {event["time"] for event in events} == {0}
    assert rebuild_world(initial, events) == world.snapshot()
