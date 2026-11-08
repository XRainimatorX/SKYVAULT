"""Phase 5: observer profiles, fog of war, delay, stale data and the five views."""

import ast
import copy
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from skyvault.contracts import (
    ContractError,
    validate_observation,
    validate_observer_profile,
)
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.observation import (
    OBSERVERS,
    available_actions,
    concealment_for,
    context_for,
    history_from_package,
    load_observer_profile,
    observations_for_run,
    observe,
    visible_contacts,
)
from skyvault.observation.observe import hp_band
from skyvault.policies import import_policy_module
from skyvault.scenario_loader import load_scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = REPO_ROOT / "data" / "scenarios"
REFERENCE = SCENARIOS / "tactical_reference_001" / "v0.1.json"
MILITARY = {
    name: SCENARIOS / f"military_{name}_001" / "v0.1.json"
    for name in ("squad", "urban", "mountain", "junction")
}
GRID = {"type": "grid", "width": 10, "height": 10, "distance_model": "chebyshev"}


def unit(entity_id, faction, position, hp=30, status="active", **capabilities):
    return {
        "entity_id": entity_id,
        "faction": faction,
        "position": position,
        "state": {"hp": hp, "status": status},
        "capabilities": capabilities,
    }


def units(*items):
    return {item["entity_id"]: item for item in items}


def profile(**overrides):
    base = load_observer_profile("TAC_ANGEL")
    base.update(overrides)
    return base


def context(**overrides):
    base = {
        "max_ticks": 10,
        "resources": {},
        "available_actions": ["attack", "move"],
        "mission": "hold",
        "constraints": [],
        "concealment": None,
        "space": GRID,
    }
    base.update(overrides)
    return base


RED = {"faction": "RED", "actor_id": "r1"}


@pytest.fixture(scope="module")
def reference():
    scenario = load_scenario(REFERENCE)
    return scenario, SkyVaultTacticalReferenceEngine(scenario).run()


@pytest.fixture(scope="module")
def urban():
    scenario = load_scenario(MILITARY["urban"])
    return scenario, SkyVaultTacticalReferenceEngine(scenario).run()


def strings(value: Any) -> set[str]:
    """Every string and key anywhere in value."""
    if isinstance(value, dict):
        return set(value) | set().union(*(strings(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(strings(v) for v in value)) if value else set()
    return {value} if isinstance(value, str) else set()


# ── profiles ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", OBSERVERS)
def test_every_observer_profile_passes_its_contract(name):
    loaded = load_observer_profile(name)

    assert loaded["observer_id"] == name
    assert set(loaded) == {
        "observer_id",
        "description",
        "view",
        "delay_ticks",
        "stale_after_ticks",
        "default_sensor_range",
        "local_radius",
        "enemy_detail",
        "source_quality",
    }


def test_the_five_observers_have_the_five_views():
    views = {name: load_observer_profile(name)["view"] for name in OBSERVERS}

    assert views == {
        "TAC_ANGEL": "local",
        "STARTX": "aggregate",
        "NEXUS": "mission",
        "HADES": "threat",
        "AEROGRID": "coverage",
    }


def test_a_profile_loads_by_path_and_fills_defaults(tmp_path):
    path = tmp_path / "minimal.json"
    path.write_text(json.dumps({"observer_id": "X", "view": "threat"}))

    loaded = load_observer_profile(path)

    assert loaded["delay_ticks"] == 0
    assert loaded["enemy_detail"] == "exact"
    assert loaded["default_sensor_range"] == 5.0


@pytest.mark.parametrize(
    "broken",
    [
        {"observer_id": "X", "view": "god"},
        {"observer_id": "X", "view": "local", "delay_ticks": -1},
        {"observer_id": "X", "view": "local", "sees_everything": True},
        {"view": "local"},
    ],
)
def test_a_broken_profile_is_rejected(broken):
    with pytest.raises(ContractError):
        validate_observer_profile(broken)


def test_an_unknown_observer_is_not_found():
    with pytest.raises(FileNotFoundError):
        load_observer_profile("SKYNET")


# ── sensing ──────────────────────────────────────────────────────────────────


def test_an_enemy_is_seen_within_sensor_range_only():
    world = units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [5, 0]))
    far = units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [6, 0]))

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.5}
    assert visible_contacts(far, "RED", profile(), None, GRID) == {}


def test_a_units_own_sensor_range_beats_the_profile_default():
    world = units(unit("r1", "RED", [0, 0], sensor_range=7), unit("b1", "BLUE", [7, 0]))

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.5}


def test_concealment_shortens_the_range_an_enemy_is_seen_at():
    world = units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [3, 0]))

    def forest(cell):
        return 0.5 if list(cell) == [3, 0] else 0.0

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.7}
    assert visible_contacts(world, "RED", profile(), forest, GRID) == {}
    world["b1"]["position"] = [2, 0]
    assert visible_contacts(world, "RED", profile(), forest, GRID) == {"b1": 0.8}


def test_confidence_is_the_best_among_the_units_that_see():
    world = units(
        unit("r1", "RED", [0, 0]),
        unit("r2", "RED", [4, 0]),
        unit("b1", "BLUE", [5, 0]),
    )

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.9}


def test_a_destroyed_unit_senses_nothing_but_a_wreck_is_seen():
    world = units(
        unit("r1", "RED", [0, 0], status="destroyed"),
        unit("r2", "RED", [9, 9]),
        unit("b1", "BLUE", [1, 0]),
        unit("b2", "BLUE", [9, 8], status="destroyed"),
    )

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b2": 0.9}


def test_distance_follows_the_spaces_distance_model():
    world = units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [3, 3]))
    manhattan = dict(GRID, distance_model="manhattan")

    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.7}
    assert visible_contacts(world, "RED", profile(), None, manhattan) == {}


def test_euclidean_distance_rounds_down():
    world = units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [4, 4]))
    euclid = dict(GRID, distance_model="euclidean_floor")

    # sqrt(32) = 5.66 → 5: just in range, where chebyshev says 4
    assert visible_contacts(world, "RED", profile(), None, euclid) == {"b1": 0.5}
    assert visible_contacts(world, "RED", profile(), None, GRID) == {"b1": 0.6}


# ── acceptance 1–2: the same world, two different observations ───────────────


def test_tac_angel_and_startx_see_the_same_world_differently(reference):
    scenario, package = reference
    history = history_from_package(package)
    ctx = context_for(scenario, "RED")
    viewpoint = {"faction": "RED", "actor_id": "red_001"}

    tac = observe(history, 4, load_observer_profile("TAC_ANGEL"), viewpoint, ctx)
    startx = observe(history, 4, load_observer_profile("STARTX"), viewpoint, ctx)

    assert tac["visible_world_state"] != startx["visible_world_state"]
    assert tac["uncertainty"]["observed_at"] == 4
    assert startx["uncertainty"]["observed_at"] == 3
    assert any(
        e["relation"] == "enemy" for e in tac["visible_world_state"]["known_entities"]
    )
    assert startx["visible_world_state"]["known_entities"] == []


def test_startx_never_gets_a_position_or_an_enemy_id(urban):
    scenario, package = urban
    enemies = {e["entity_id"] for e in scenario["entities"] if e["faction"] != "RED"}
    observations = observations_for_run(
        package,
        scenario,
        load_observer_profile("STARTX"),
        {"faction": "RED", "actor_id": "red_01"},
    )

    for observation in observations:
        found = strings(observation["visible_world_state"])
        assert not found & {"position", "center", "positions"}
        assert not found & enemies


# ── acceptance 3: what cannot be seen is not exposed ─────────────────────────


@pytest.mark.parametrize("observer", ["TAC_ANGEL", "STARTX", "HADES", "AEROGRID"])
def test_an_enemy_out_of_sight_never_appears(observer, urban):
    scenario, package = urban
    history = history_from_package(package)
    ctx = context_for(scenario, "RED")
    loaded = load_observer_profile(observer)
    seen_anything_hidden = False

    for tick in history:
        observation = observe(
            history, tick, loaded, {"faction": "RED", "actor_id": "red_01"}, ctx
        )
        shown = observation["uncertainty"]["observed_at"]
        known = set()
        for back in range(loaded["stale_after_ticks"] + 1):
            if shown - back >= 0:
                known |= set(
                    visible_contacts(
                        history[shown - back], "RED", loaded, ctx["concealment"], GRID
                    )
                )
        enemies = {e for e, u in history[shown].items() if u["faction"] != "RED"}
        unknown = enemies - known
        seen_anything_hidden |= bool(unknown)
        assert not strings(observation) & unknown, (tick, unknown)
        assert set(observation["hidden_state"]) == {"exists", "reason"}

    assert seen_anything_hidden


def test_hidden_state_admits_only_that_something_is_hidden():
    world = {
        0: units(
            unit("r1", "RED", [0, 0]),
            unit("b1", "BLUE", [9, 9]),
            unit("b2", "BLUE", [8, 9]),
        )
    }

    hidden = observe(world, 0, profile(), RED, context())

    assert hidden["hidden_state"] == {"exists": True, "reason": "fog_of_war"}
    assert hidden["uncertainty"]["confidence_level"] == 0.0
    assert not strings(hidden) & {"b1", "b2"}


def test_nothing_is_hidden_when_every_enemy_is_in_sight_or_gone():
    world = {
        0: units(
            unit("r1", "RED", [0, 0]),
            unit("b1", "BLUE", [1, 1]),
            unit("b2", "BLUE", [9, 9], status="destroyed"),
        )
    }

    seen = observe(world, 0, profile(), RED, context())

    assert seen["hidden_state"] == {"exists": False, "reason": None}


def test_the_mission_view_has_no_fog_and_full_confidence():
    world = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [9, 9]))}

    nexus = observe(world, 0, load_observer_profile("NEXUS"), RED, context())

    assert nexus["hidden_state"] == {"exists": False, "reason": None}
    assert nexus["uncertainty"]["confidence_level"] == 1.0


# ── acceptance 4: confidence, delay and uncertainty on every observation ─────


@pytest.mark.parametrize("name", ["reference", "squad", "mountain", "junction"])
def test_every_observation_carries_its_uncertainty(name):
    path = REFERENCE if name == "reference" else MILITARY[name]
    scenario = load_scenario(path)
    package = SkyVaultTacticalReferenceEngine(scenario).run()
    first = scenario["entities"][0]
    viewpoint = {"faction": first["faction"], "actor_id": first["entity_id"]}

    for observer in OBSERVERS:
        loaded = load_observer_profile(observer)
        observations = observations_for_run(package, scenario, loaded, viewpoint)
        assert len(observations) == package["final_world_state"]["tick"] + 1
        for observation in observations:
            uncertainty = observation["uncertainty"]
            assert 0.0 <= uncertainty["confidence_level"] <= 1.0
            assert uncertainty["delay_ticks"] == loaded["delay_ticks"]
            assert uncertainty["stale_after"] == loaded["stale_after_ticks"]
            assert uncertainty["source_quality"] == loaded["source_quality"]
            assert validate_observation(observation) == observation


def test_confidence_level_is_the_mean_of_the_known_contacts():
    world = {
        0: units(
            unit("r1", "RED", [0, 0]),
            unit("b1", "BLUE", [1, 0]),
            unit("b2", "BLUE", [5, 0]),
        )
    }

    observation = observe(world, 0, profile(), RED, context())

    assert observation["uncertainty"]["confidence_level"] == 0.7


# ── information delay ────────────────────────────────────────────────────────


def moving_history():
    """BLUE walks toward RED one cell per tick from [9, 0]."""
    return {
        tick: units(
            unit("r1", "RED", [0, 0]),
            unit("b1", "BLUE", [9 - tick, 0], hp=30 - tick),
        )
        for tick in range(6)
    }


def test_a_delayed_observer_sees_an_earlier_tick():
    history = moving_history()
    delayed = observe(history, 5, profile(delay_ticks=2), RED, context())
    then = observe(history, 3, profile(), RED, context())

    assert delayed["time"] == 5
    assert delayed["uncertainty"]["observed_at"] == 3
    assert delayed["visible_world_state"] == then["visible_world_state"]
    assert (
        observe(history, 5, profile(), RED, context())["uncertainty"]["observed_at"]
        == 5
    )


def test_a_delay_never_reaches_before_the_start():
    observation = observe(moving_history(), 1, profile(delay_ticks=3), RED, context())

    assert observation["uncertainty"]["observed_at"] == 0


def test_the_latest_recorded_tick_stands_in_for_a_missing_one():
    history = {0: moving_history()[0], 3: moving_history()[3]}

    observation = observe(history, 2, profile(), RED, context())

    assert observation["uncertainty"]["observed_at"] == 2
    assert observation["hidden_state"]["exists"] is True


def test_an_observation_before_any_history_fails():
    with pytest.raises(ValueError, match="no history"):
        observe({3: moving_history()[3]}, 1, profile(), RED, context())


# ── stale data ───────────────────────────────────────────────────────────────


def retreat_history():
    """BLUE is seen at [4, 0] on tick 0, then steps out of range."""
    return {
        0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [4, 0])),
        1: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [7, 0])),
        2: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [8, 0])),
        3: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [9, 0])),
    }


def enemy(observation):
    return [
        e
        for e in observation["visible_world_state"]["known_entities"]
        if e["relation"] == "enemy"
    ]


def test_a_lost_contact_stays_where_it_was_last_seen():
    stale = enemy(observe(retreat_history(), 1, profile(), RED, context()))

    # seen at confidence 0.6, faded by one tick of four: 0.6 × 0.75
    assert stale == [
        {
            "entity_id": "b1",
            "faction": "BLUE",
            "relation": "enemy",
            "status": "stale",
            "position": [4, 0],
            "hp": None,
            "hp_band": "intact",
            "confidence": 0.45,
            "last_seen": 0,
            "age": 1,
            "capabilities": None,
        }
    ]


def test_a_stale_contact_fades_and_is_then_forgotten():
    history = retreat_history()

    ages = [
        [
            (e["age"], e["confidence"])
            for e in enemy(
                observe(history, t, profile(stale_after_ticks=2), RED, context())
            )
        ]
        for t in (1, 2, 3)
    ]

    assert ages == [[(1, 0.4)], [(2, 0.2)], []]


def test_without_memory_a_lost_contact_is_gone_at_once():
    assert (
        enemy(
            observe(retreat_history(), 1, profile(stale_after_ticks=0), RED, context())
        )
        == []
    )


def test_a_contact_last_seen_as_a_wreck_is_not_remembered():
    history = {
        0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [4, 0])),
        1: units(
            unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [4, 0], status="destroyed")
        ),
        2: units(
            unit("r1", "RED", [9, 9]), unit("b1", "BLUE", [4, 0], status="destroyed")
        ),
    }

    wreck = enemy(observe(history, 1, profile(), RED, context()))
    later = enemy(observe(history, 2, profile(), RED, context()))

    assert [e["status"] for e in wreck] == ["destroyed"]
    assert wreck[0]["hp"] is None and wreck[0]["hp_band"] is None
    assert later == []


# ── partial observation ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hp", "band"),
    [(30, "intact"), (21, "intact"), (20, "damaged"), (10, "damaged"), (9, "critical")],
)
def test_health_bands_split_the_starting_hp_in_thirds(hp, band):
    assert hp_band(hp, 30) == band


def test_enemy_detail_decides_how_much_health_is_shown():
    history = {
        0: units(unit("r1", "RED", [0, 0], hp=30), unit("b1", "BLUE", [1, 0], hp=30)),
        1: units(unit("r1", "RED", [0, 0], hp=12), unit("b1", "BLUE", [1, 0], hp=12)),
    }

    shown = {
        detail: enemy(
            observe(history, 1, profile(enemy_detail=detail), RED, context())
        )[0]
        for detail in ("exact", "banded", "hidden")
    }
    me = observe(history, 1, profile(enemy_detail="hidden"), RED, context())

    assert (shown["exact"]["hp"], shown["exact"]["hp_band"]) == (12.0, None)
    assert (shown["banded"]["hp"], shown["banded"]["hp_band"]) == (None, "damaged")
    assert (shown["hidden"]["hp"], shown["hidden"]["hp_band"]) == (None, None)
    assert me["visible_world_state"]["known_entities"][0]["hp"] == 12.0


def test_own_units_carry_capabilities_and_enemies_never_do():
    world = {
        0: units(
            unit("r1", "RED", [0, 0], attack_range=2),
            unit("b1", "BLUE", [1, 0], attack_range=3),
        )
    }

    known = observe(world, 0, profile(), RED, context())["visible_world_state"][
        "known_entities"
    ]

    assert known[0]["capabilities"] == {"attack_range": 2}
    assert known[1]["capabilities"] is None


# ── the five views ───────────────────────────────────────────────────────────


def test_the_local_view_centres_on_the_deciding_unit():
    world = {
        0: units(
            unit("r1", "RED", [0, 0]),
            unit("r2", "RED", [3, 0]),
            unit("r3", "RED", [9, 9], status="destroyed"),
            unit("b1", "BLUE", [1, 0], attack_range=1),
            unit("b2", "BLUE", [2, 2], attack_range=1, move_range=1),
            unit("b3", "BLUE", [5, 0], attack_range=1),
        )
    }

    state = observe(world, 0, profile(local_radius=2), RED, context())[
        "visible_world_state"
    ]

    assert [
        (e["entity_id"], e["relation"], e["status"]) for e in state["known_entities"]
    ] == [
        ("r1", "self", "active"),
        ("r2", "ally", "active"),
        ("r3", "ally", "destroyed"),
        ("b1", "enemy", "visible"),
        ("b2", "enemy", "visible"),
        ("b3", "enemy", "visible"),
    ]
    assert state["local_area"] == {
        "center": [0, 0],
        "radius": 2,
        "entity_ids": ["b1", "b2", "r1"],
    }
    assert [(r["entity_id"], r["kind"]) for r in state["known_risks"]] == [
        ("b1", "in_range"),
        ("b2", "can_close"),
    ]
    assert state["summary"] == {
        "own_active": 2,
        "visible_enemies": 3,
        "stale_enemies": 0,
        "destroyed_enemies_in_sight": 0,
    }


def test_the_local_view_needs_a_deciding_unit():
    world = {0: units(unit("r1", "RED", [0, 0]))}

    with pytest.raises(ValueError, match="actor_id"):
        observe(world, 0, profile(), {"faction": "RED"}, context())


def test_the_aggregate_view_reports_shares_and_trends():
    history = {
        0: units(
            unit("r1", "RED", [0, 0], hp=20),
            unit("r2", "RED", [1, 0], hp=20),
            unit("b1", "BLUE", [9, 9]),
        ),
        1: units(
            unit("r1", "RED", [0, 0], hp=20),
            unit("r2", "RED", [1, 0], hp=10),
            unit("b1", "BLUE", [4, 4]),
        ),
        2: units(
            unit("r1", "RED", [0, 0], hp=15),
            unit("r2", "RED", [1, 0], hp=-3, status="destroyed"),
            unit("b1", "BLUE", [4, 4]),
        ),
    }
    startx = profile(
        view="aggregate", delay_ticks=0, stale_after_ticks=1, enemy_detail="hidden"
    )

    summary = observe(history, 2, startx, RED, context())["visible_world_state"][
        "summary"
    ]

    assert summary == {
        "own": {"active": 1, "destroyed": 1, "hp_ratio": 0.375},
        "enemy": {"visible": 1, "stale": 0, "destroyed_in_sight": 0},
        "trend": {
            "window": 1,
            "own_hp_ratio_change": -0.375,
            "own_losses": 1,
            "enemy_contacts_change": 0,
        },
    }


def test_the_mission_view_reports_progress_for_every_side():
    world = {
        0: units(unit("r1", "RED", [0, 0], hp=10), unit("b1", "BLUE", [9, 9], hp=10)),
        4: units(
            unit("r1", "RED", [0, 0], hp=5),
            unit("b1", "BLUE", [9, 9], hp=0, status="destroyed"),
        ),
    }

    summary = observe(world, 4, load_observer_profile("NEXUS"), RED, context())[
        "visible_world_state"
    ]["summary"]

    assert summary == {
        "tick": 4,
        "max_ticks": 10,
        "progress": 0.4,
        "factions": {
            "BLUE": {"active": 0, "destroyed": 1, "hp_ratio": 0.0},
            "RED": {"active": 1, "destroyed": 0, "hp_ratio": 0.5},
        },
    }


def test_the_threat_view_counts_ticks_until_each_enemy_can_strike():
    world = {
        0: units(
            unit("r1", "RED", [0, 0]),
            unit("r2", "RED", [4, 4]),
            unit("b1", "BLUE", [5, 5], attack_range=1),
            unit("b2", "BLUE", [0, 4], attack_range=1, move_range=1),
            unit("b3", "BLUE", [0, 5], attack_range=2, move_range=2),
        )
    }

    state = observe(world, 0, load_observer_profile("HADES"), RED, context())[
        "visible_world_state"
    ]

    assert [
        (r["entity_id"], r["nearest_own"], r["ticks_to_strike"])
        for r in state["known_risks"]
    ] == [
        ("b1", "r2", 0),
        ("b3", "r2", 1),
        ("b2", "r1", 3),  # as near to r1 as to r2: the first id wins
    ]
    assert state["summary"] == {"threats": 3, "in_range_now": 1, "defense_window": 0}
    assert [e["hp"] for e in state["known_entities"]] == [30.0, 30.0, 30.0]


def test_the_threat_view_without_threats_has_no_window():
    world = {0: units(unit("r1", "RED", [0, 0]))}

    summary = observe(world, 0, load_observer_profile("HADES"), RED, context())[
        "visible_world_state"
    ]["summary"]

    assert summary == {"threats": 0, "in_range_now": 0, "defense_window": None}


def test_the_coverage_view_counts_covered_cells_and_gaps():
    small = {"type": "grid", "width": 5, "height": 5, "distance_model": "chebyshev"}
    world = {
        0: units(
            unit("r1", "RED", [0, 2], sensor_range=0),
            unit("r2", "RED", [4, 2], sensor_range=0),
            unit("r3", "RED", [2, 2], sensor_range=1, status="destroyed"),
            unit("b1", "BLUE", [2, 2]),
        )
    }

    summary = observe(
        world, 0, load_observer_profile("AEROGRID"), RED, context(space=small)
    )["visible_world_state"]["summary"]

    # two lone covered cells leave one connected gap around them
    assert summary == {
        "covered_cells": 2,
        "total_cells": 25,
        "coverage_ratio": 0.08,
        "gaps": 1,
        "contacts": 0,
    }
    world[0]["r1"]["capabilities"]["sensor_range"] = 2
    world[0]["r1"]["position"] = [2, 2]
    world[0]["r2"]["capabilities"]["sensor_range"] = 0
    split = observe(
        world, 0, load_observer_profile("AEROGRID"), RED, context(space=small)
    )["visible_world_state"]["summary"]
    assert (split["covered_cells"], split["gaps"], split["contacts"]) == (25, 0, 1)


def test_the_coverage_view_finds_separate_gaps():
    small = {"type": "grid", "width": 5, "height": 3, "distance_model": "chebyshev"}
    world = {0: units(unit("r1", "RED", [2, 1], sensor_range=1))}

    summary = observe(
        world, 0, load_observer_profile("AEROGRID"), RED, context(space=small)
    )["visible_world_state"]["summary"]

    assert (summary["covered_cells"], summary["gaps"]) == (9, 2)


def test_observation_needs_a_grid():
    world = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [1, 0]))}

    with pytest.raises(ValueError, match="grid"):
        observe(world, 0, profile(), RED, context(space={"type": "graph"}))
    with pytest.raises(ValueError, match="grid"):
        observe(world, 0, load_observer_profile("AEROGRID"), RED, context(space={}))


# ── contracts ────────────────────────────────────────────────────────────────


def valid_observation():
    world = {0: units(unit("r1", "RED", [0, 0]), unit("b1", "BLUE", [1, 0]))}
    return observe(world, 0, profile(), RED, context())


@pytest.mark.parametrize(
    "break_it",
    [
        lambda o: o["visible_world_state"]["known_entities"][1].update(status="stale"),
        lambda o: o["visible_world_state"]["known_entities"][1].update(capabilities={}),
        lambda o: o["visible_world_state"]["known_entities"][0].update(
            status="visible"
        ),
        lambda o: o["hidden_state"].update(reason="fog_of_war"),
        lambda o: o["uncertainty"].update(observed_at=3),
        lambda o: o["uncertainty"].update(confidence_level=1.5),
        lambda o: o.update(world={}),
    ],
)
def test_a_broken_observation_is_rejected(break_it):
    observation = copy.deepcopy(valid_observation())
    break_it(observation)

    with pytest.raises(ContractError):
        validate_observation(observation)


# ── history and context ──────────────────────────────────────────────────────


def test_history_from_a_package_fills_quiet_ticks():
    initial = {"tick": 0, "entities": {"r1": unit("r1", "RED", [0, 0])}}
    moved = dict(unit("r1", "RED", [1, 0]))
    final = {"tick": 3, "entities": {"r1": dict(unit("r1", "RED", [2, 0]))}}
    package = {
        "initial_world_state": dict(initial, scenario_id="s"),
        "event_memory": [{"time": 1, "after_state": moved}],
        "final_world_state": final,
    }

    history = history_from_package(package)

    assert sorted(history) == [0, 1, 2, 3]
    assert history[2] == history[1] == {"r1": moved}
    assert history[3] == final["entities"]


def test_context_comes_from_the_scenario_and_its_domain():
    reference = load_scenario(REFERENCE)
    squad = load_scenario(MILITARY["squad"])

    plain = context_for(reference, "RED")
    military = context_for(squad, "RED")

    assert concealment_for(reference) is None
    assert plain["mission"] == reference["world_contract"]["purpose"]
    assert plain["available_actions"] == available_actions(reference)
    assert plain["constraints"] == ["max_ticks=10"]
    assert military["mission"] == {"type": "destroy", "objective": []}
    assert "rally" in military["available_actions"]
    assert military["concealment"]([2, 1]) == 0.4
    assert military["concealment"]([0, 0]) == 0.0


def test_a_domain_without_observation_hooks_gives_none(monkeypatch):
    import skyvault.observation.history as history_module

    class Bare:
        action_types = ("move",)

    squad = load_scenario(MILITARY["squad"])
    monkeypatch.setattr(history_module, "load_domain", lambda name: Bare())

    assert concealment_for(squad) is None
    assert context_for(squad, "RED")["mission"] == squad["world_contract"]["purpose"]


# ── the engine: a policy that decides from its observation only ──────────────


class Recorder:
    """An observing policy that records everything it is handed."""

    system_id = "RECORDER"
    observer_profile = "TAC_ANGEL"

    def __init__(self):
        self.seen: list[Any] = []

    def decide_from_observation(self, observation):
        self.seen.append(observation)
        known = observation["visible_world_state"]["known_entities"]
        me = known[0]
        targets = [e for e in known if e["status"] == "visible"]
        if not targets:
            return None
        x, y = me["position"]
        tx, ty = targets[0]["position"]
        if max(abs(tx - x), abs(ty - y)) <= me["capabilities"].get("attack_range", 1):
            return {
                "action_type": "attack",
                "target": {"entity_id": targets[0]["entity_id"]},
            }
        return {
            "action_type": "move",
            "target": {"location": [x + (tx > x) - (tx < x), y + (ty > y) - (ty < y)]},
            "intent": "close",
        }


def test_an_observing_policy_never_gets_the_world_or_a_hidden_enemy(monkeypatch):
    import skyvault.engine as engine_module

    calls = []

    def recording_observe(history, tick, loaded, viewpoint, ctx):
        result = observe(history, tick, loaded, viewpoint, ctx)
        calls.append((copy.deepcopy(history), tick, loaded, viewpoint, ctx, result))
        return result

    monkeypatch.setattr(engine_module, "observe", recording_observe)
    recorder = Recorder()
    SkyVaultTacticalReferenceEngine(
        load_scenario(MILITARY["urban"]), policy=recorder
    ).run()

    assert recorder.seen == [call[-1] for call in calls]
    assert any(o["hidden_state"]["exists"] for o in recorder.seen)
    for history, tick, loaded, viewpoint, ctx, result in calls:
        faction = viewpoint["faction"]
        known = set()
        for back in range(loaded["stale_after_ticks"] + 1):
            if tick - back in history:
                known |= set(
                    visible_contacts(
                        history[tick - back], faction, loaded, ctx["concealment"], GRID
                    )
                )
        enemies = {e for e, u in history[tick].items() if u["faction"] != faction}
        assert not strings(result) & (enemies - known), tick
        assert "world" not in result


def test_the_engine_issues_the_action_ids_of_an_observing_policy():
    scenario = load_scenario(MILITARY["squad"])
    package = SkyVaultTacticalReferenceEngine(scenario, policy=Recorder()).run()

    selected = [
        e for e in package["event_memory"] if e["event_type"] == "ACTION_SELECTED"
    ]
    ids = [e["source"]["action_id"] for e in selected]

    assert selected
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("action_") for i in ids)
    assert {e["source"]["system_id"] for e in selected} == {"RECORDER"}


def test_an_observing_policy_that_holds_records_no_action():
    class Holder:
        observer_profile = "TAC_ANGEL"

        def decide_from_observation(self, observation):
            return None

    scenario = load_scenario(REFERENCE)
    package = SkyVaultTacticalReferenceEngine(scenario, policy=Holder()).run()
    kinds = {e["event_type"] for e in package["event_memory"]}

    assert "ACTION_SELECTED" not in kinds
    assert "NO_ACTION" in kinds


def test_the_engines_history_is_the_packages_history():
    scenario = load_scenario(MILITARY["squad"])
    engine = SkyVaultTacticalReferenceEngine(scenario, policy=Recorder())

    package = engine.run()

    rebuilt = history_from_package(package)
    assert {t: rebuilt[t] for t in engine.observed} == engine.observed


def test_a_world_policy_keeps_no_observation_history(reference):
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE))
    engine.run()

    assert engine.observer is None
    assert engine.observed == {}
    with pytest.raises(RuntimeError, match="decides from the world"):
        engine.observed_decision(next(iter(engine.world.entities.values())))


def test_the_tac_angel_example_decides_from_observations_only():
    from skyvault.policies import build_policy, registered_policies

    # the military tests may have loaded it already; a file loads only once
    if "tac_angel_example" not in registered_policies():
        import_policy_module(str(REPO_ROOT / "examples" / "tac_angel_policy.py"))

    policy = build_policy("tac_angel_example", random.Random(1))
    squad = load_scenario(MILITARY["squad"])
    squad["runtime"]["policy"] = {"name": "tac_angel_example"}

    package = SkyVaultTacticalReferenceEngine(squad).run()

    assert policy.observer_profile == "TAC_ANGEL"
    assert not hasattr(policy, "decide_action")
    selected = [
        e for e in package["event_memory"] if e["event_type"] == "ACTION_SELECTED"
    ]
    assert {e["source"]["system_id"] for e in selected} == {"TAC_ANGEL"}
    assert {e["data"]["action_type"] for e in selected} == {"attack", "move"}


# ── layering, script and reproducibility ─────────────────────────────────────


def test_observation_never_imports_the_engine():
    package = REPO_ROOT / "src" / "skyvault" / "observation"
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "engine" not in (node.module or ""), path.name
            if isinstance(node, ast.Import):
                assert not any("engine" in a.name for a in node.names), path.name


def run_script(output: Path, seed: str, *extra: str) -> None:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    subprocess.run(  # nosec B603 - fixed interpreter and repo script
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "observe_run.py"),
            "--output",
            str(output),
            *extra,
        ],
        check=True,
        env=env,
        capture_output=True,
    )


def test_the_script_writes_every_observer_byte_for_byte_across_hash_seeds(tmp_path):
    run_script(tmp_path / "a", "0", "--scenario", str(MILITARY["squad"]))
    run_script(tmp_path / "b", "4242", "--scenario", str(MILITARY["squad"]))

    for observer in OBSERVERS:
        first = (tmp_path / "a" / f"{observer}.json").read_bytes()
        assert first == (tmp_path / "b" / f"{observer}.json").read_bytes()
        document = json.loads(first)
        assert document["observer_id"] == observer
        assert document["viewpoint"] == {"faction": "RED", "actor_id": "red_01"}
        assert len(document["observations"]) == 21
