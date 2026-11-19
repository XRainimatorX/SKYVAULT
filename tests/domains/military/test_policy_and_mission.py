"""Baseline policy (perception, morale, doctrine, logistics, command) and missions."""

import copy

import pytest
from conftest import FixedRng

from skyvault.domains.military import build_scenario, mission_outcome
from skyvault.domains.military.policy import MilitaryBaselinePolicy
from skyvault.runtime.world import create_world


@pytest.fixture
def setup(profiles):
    """(red units, blue units, **spec options) -> (world, policy)."""
    from conftest import spec

    def make(red, blue, profile_changes=None, **options):
        changed = copy.deepcopy(profiles)
        if profile_changes:
            profile_changes(changed)
        scenario = build_scenario(spec(red, blue, **options), changed)
        world = create_world(scenario)
        world.tick = 1
        return world, MilitaryBaselinePolicy(FixedRng(), scenario, seed=7)

    return make


def decide(world, policy, unit="red_01"):
    return policy.decide(world, world.get_entity(unit))


# ── what a unit sees ─────────────────────────────────────────────────────────


def test_concealment_shrinks_how_far_a_unit_sees(setup):
    # eyes see 5; a forest cell (concealment 0.4) only 3
    world, policy = setup([("rifleman", [7, 1])], [("rifleman", [3, 1])])
    assert policy.seen_enemies(world, world.get_entity("red_01")) == []

    world, policy = setup([("rifleman", [7, 1])], [("rifleman", [3, 0])])
    assert [
        e.entity_id for e in policy.seen_enemies(world, world.get_entity("red_01"))
    ] == ["blue_01"]


# ── morale ───────────────────────────────────────────────────────────────────


def test_a_panicked_unit_does_nothing_but_wait(setup):
    world, policy = setup([("rifleman", [0, 1])], [("rifleman", [3, 0])])
    world.get_entity("red_01").state["suppression"] = 85

    action = decide(world, policy)

    assert (action.action_type, action.intent) == ("wait", "pinned_down")


def test_a_broken_unit_retreats_away_from_the_enemy(setup):
    world, policy = setup([("rifleman", [4, 0])], [("rifleman", [6, 0])])
    world.get_entity("red_01").state["morale"] = 20

    action = decide(world, policy)

    assert (action.action_type, action.intent) == ("move", "retreat")
    assert action.target.location[0] < 4


def test_a_suppressed_unit_with_no_target_takes_cover(setup):
    world, policy = setup([("rifleman", [1, 1])], [("rifleman", [7, 3])])
    world.get_entity("red_01").state["suppression"] = 60

    action = decide(world, policy)

    assert (action.action_type, action.intent) == ("move", "suppressed_take_cover")
    assert action.target.location == (2, 1)  # the forest next door


# ── firing and doctrines ─────────────────────────────────────────────────────


def test_the_weakest_enemy_in_range_is_engaged(setup):
    world, policy = setup(
        [("rifleman", [3, 3])], [("rifleman", [5, 3]), ("rifleman", [4, 3])]
    )
    world.get_entity("blue_01").state["hp"] = 5

    action = decide(world, policy)

    assert (action.action_type, action.target.entity_id) == ("attack", "blue_01")


def test_without_ammunition_a_unit_does_not_fire(setup):
    world, policy = setup([("rifleman", [3, 3])], [("rifleman", [5, 3])])
    world.get_entity("red_01").state["ammo"] = 0

    assert decide(world, policy).action_type != "attack"


def test_aggressive_units_head_for_where_the_enemy_started(setup):
    world, policy = setup([("rifleman", [0, 3])], [("rifleman", [7, 3])])

    action = decide(world, policy)

    assert (action.action_type, action.intent) == ("move", "advance")
    assert action.target.location == (2, 3)


def test_defensive_units_stay_in_cover_once_they_see_the_enemy(setup):
    world, policy = setup(
        [("rifleman", [1, 1])],
        [("rifleman", [6, 1])],
        red_side={"doctrine": "defensive"},
    )

    action = decide(world, policy)

    assert (action.action_type, action.intent) == ("move", "defend_from_cover")
    assert action.target.location == (2, 1)


def test_overwatch_units_take_turns_to_bound_and_to_fire(setup):
    world, policy = setup(
        [("rifleman", [3, 3]), ("rifleman", [3, 0])],
        [("rifleman", [5, 3])],
        red_side={"doctrine": "overwatch"},
    )
    world.tick = 2  # red_01 is index 0: (0 + 2) is even, so it bounds

    bounding = decide(world, policy, "red_01")
    covering = decide(world, policy, "red_02")

    assert bounding.action_type == "move"
    assert (covering.action_type, covering.intent) == ("attack", "engage")
    world.tick = 3
    assert decide(world, policy, "red_01").action_type == "attack"


def test_logistics_resupplies_a_friend_running_low(setup):
    world, policy = setup(
        [("logistics", [0, 3]), ("rifleman", [1, 3])], [("rifleman", [7, 0])]
    )
    world.get_entity("red_02").state["ammo"] = 5  # below half of 12

    action = decide(world, policy, "red_01")

    assert (action.action_type, action.target.entity_id) == ("supply", "red_02")

    world.get_entity("red_02").state["ammo"] = 6  # exactly half: not low
    assert decide(world, policy, "red_01").action_type != "supply"


def test_logistics_does_not_promise_ammunition_it_does_not_have(setup):
    def empty(profiles):
        profiles["logistics"]["ammo_stock"] = 5  # less than one resupply of 6

    world, policy = setup(
        [("logistics", [0, 3]), ("rifleman", [1, 3])],
        [("rifleman", [7, 0])],
        profile_changes=empty,
    )
    world.get_entity("red_02").state["ammo"] = 1

    assert decide(world, policy, "red_01").action_type != "supply"


# ── command delay ────────────────────────────────────────────────────────────


def test_with_no_delay_and_no_loss_the_order_arrives_at_once_untouched(setup):
    world, policy = setup([("rifleman", [0, 3])], [("rifleman", [7, 3])])
    before = policy.command_rng.getstate()

    arrived = policy.decide_action(world, world.get_entity("red_01"))

    assert (arrived.action_type, arrived.intent) == ("move", "advance")
    assert policy.command_rng.getstate() == before  # no loss roll at all
    assert policy.pending == {}


def test_a_delayed_order_arrives_ticks_later(setup):
    world, policy = setup(
        [("rifleman", [0, 3])], [("rifleman", [7, 3])], red_side={"command": "runner"}
    )
    policy.factions["RED"]["command"]["loss_prob"] = 0.0
    red = world.get_entity("red_01")

    first = policy.decide_action(world, red)
    world.tick = 2
    second = policy.decide_action(world, red)
    sent_at_1 = policy.pending[(3, "red_01")]
    world.tick = 3
    third = policy.decide_action(world, red)

    assert (first, second) == (None, None)
    assert third is sent_at_1


def test_orders_are_lost_at_the_loss_rate_without_touching_the_battle_dice(setup):
    world, policy = setup(
        [("rifleman", [0, 3])], [("rifleman", [7, 3])], red_side={"command": "degraded"}
    )
    policy.factions["RED"]["command"]["delay_ticks"] = 0
    red = world.get_entity("red_01")
    battle = policy.rng.getstate()

    arrived = 0
    for _ in range(2000):
        arrived += policy.decide_action(world, red) is not None

    assert 0.77 < arrived / 2000 < 0.83  # loss_prob 0.2
    assert policy.rng.getstate() == battle


# ── missions ─────────────────────────────────────────────────────────────────


def package_with(units, tick=10):
    return {
        "final_world_state": {
            "tick": tick,
            "entities": {
                u["entity_id"]: {
                    "entity_id": u["entity_id"],
                    "faction": u["faction"],
                    "position": u["position"],
                    "state": {"status": u.get("status", "active")},
                }
                for u in units
            },
        }
    }


def scenario_with(missions):
    return {
        "world_contract": {
            "rule_set": {
                "military": {
                    "factions": {
                        faction: {"mission": mission}
                        for faction, mission in missions.items()
                    }
                }
            }
        }
    }


def red(position, status="active"):
    return {
        "entity_id": f"r{position}",
        "faction": "RED",
        "position": position,
        "status": status,
    }


def blue(position, status="active"):
    return {
        "entity_id": f"b{position}",
        "faction": "BLUE",
        "position": position,
        "status": status,
    }


@pytest.mark.parametrize(
    ("mission", "units", "achieved", "reason"),
    [
        (
            {"type": "destroy"},
            [red([0, 0]), blue([1, 1], "destroyed")],
            True,
            "every enemy unit destroyed",
        ),
        (
            {"type": "destroy"},
            [red([0, 0]), blue([1, 1])],
            False,
            "1 enemy units still active",
        ),
        (
            {"type": "seize", "objective": [[2, 2]]},
            [red([2, 2]), blue([5, 5])],
            True,
            "1 own unit(s) on the objective; holds the objective",
        ),
        (
            {"type": "seize", "objective": [[2, 2], [2, 3]]},
            [red([2, 2]), blue([2, 3])],
            False,
            "1 enemy unit(s) still on the objective",
        ),
        (
            {"type": "seize", "objective": [[2, 2]]},
            [red([1, 1]), blue([5, 5])],
            False,
            "no own unit on the objective",
        ),
        (
            {"type": "hold", "objective": [[2, 2]]},
            [red([0, 0]), blue([5, 5])],
            True,
            "no enemy on the objective",
        ),
        (
            {"type": "hold", "objective": [[2, 2]]},
            [red([0, 0]), blue([2, 2])],
            False,
            "an enemy stands on the objective",
        ),
        (
            {"type": "hold", "objective": [[2, 2]]},
            [red([0, 0], "destroyed"), blue([5, 5])],
            False,
            "no own unit left",
        ),
        (
            {"type": "delay", "deadline": 10},
            [red([0, 0]), blue([5, 5])],
            True,
            "units still active at tick 10 (deadline 10)",
        ),
    ],
)
def test_each_mission_is_judged_from_the_final_world(mission, units, achieved, reason):
    outcome = mission_outcome(package_with(units), scenario_with({"RED": mission}))

    assert outcome["RED"] == {
        "type": mission["type"],
        "achieved": achieved,
        "reason": reason,
    }


def test_a_delay_that_ends_early_or_wiped_out_fails():
    early = mission_outcome(
        package_with([red([0, 0]), blue([5, 5])], tick=6),
        scenario_with({"RED": {"type": "delay", "deadline": 10}}),
    )
    wiped = mission_outcome(
        package_with([red([0, 0], "destroyed"), blue([5, 5])]),
        scenario_with({"RED": {"type": "delay", "deadline": 10}}),
    )

    assert early["RED"]["reason"] == "run ended at tick 6, before the deadline 10"
    assert wiped["RED"] == {
        "type": "delay",
        "achieved": False,
        "reason": "no own unit left",
    }
