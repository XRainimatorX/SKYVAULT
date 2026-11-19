"""Military rules: cover, suppression, morale, ammunition, terrain movement, rally."""

import sys
from pathlib import Path

import pytest

from skyvault.action import Action, ActionTarget
from skyvault.domains.military import MILITARY

PACK = Path(__file__).resolve().parents[3] / "src" / "skyvault" / "domains" / "military"
TESTS = Path(__file__).resolve().parents[2]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


def fire(world, resolver, shooter="red_01", target="blue_01"):
    action = Action(
        world.ids.action(), shooter, "attack", target=ActionTarget(entity_id=target)
    )
    return resolver.execute(world, action), world.event_memory


def move(world, resolver, unit, cell):
    action = Action(
        world.ids.action(), unit, "move", target=ActionTarget(location=tuple(cell))
    )
    return resolver.execute(world, action)


def unit(world, entity_id):
    return world.get_entity(entity_id)


# ── attack ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("blue_at", "roll", "event"),
    [
        ([3, 1], 0.42, "ATTACK"),  # forest: 0.6 × (1 − 0.3) = 0.42, a roll of 0.42 hits
        ([3, 1], 0.43, "MISS"),
        ([3, 0], 0.60, "ATTACK"),  # open ground: 0.6
        ([3, 0], 0.61, "MISS"),
    ],
)
def test_cover_lowers_the_chance_to_hit(make_world, blue_at, roll, event):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", blue_at)], rng_value=roll
    )

    consequence, events = fire(world, resolver)

    assert consequence.accepted
    assert events[0].event_type == event


def test_a_suppressed_shooter_hits_half_as_often(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.31
    )
    unit(world, "red_01").state["suppression"] = 60

    fire(world, resolver)

    assert world.event_memory[0].event_type == "MISS"
    assert world.event_memory[0].data["chance"] == 0.3


def test_a_hit_costs_hp_morale_and_adds_suppression(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.0
    )

    fire(world, resolver)

    target = unit(world, "blue_01").state
    assert (target["hp"], target["suppression"], target["morale"]) == (20, 20, 70)


def test_crossing_the_suppression_threshold_costs_extra_morale(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.0
    )
    blue = unit(world, "blue_01")
    blue.state["suppression"] = 50
    fire(world, resolver)
    assert (blue.state["suppression"], blue.state["morale"]) == (70, 65)

    # Already suppressed: only the hit's own morale cost
    fire(world, resolver)
    assert (blue.state["suppression"], blue.state["morale"]) == (90, 55)


def test_a_miss_still_suppresses_by_half(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.99
    )

    fire(world, resolver)

    target = unit(world, "blue_01").state
    assert (target["hp"], target["suppression"], target["morale"]) == (30, 10, 80)


def test_every_shot_spends_ammunition_and_an_empty_weapon_cannot_fire(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.99
    )

    _, events = fire(world, resolver)
    assert [e.event_type for e in events] == ["MISS", "ENTITY_STATE_CHANGED"]
    assert unit(world, "red_01").state["ammo"] == 11

    unit(world, "red_01").state["ammo"] = 0
    refused, _ = fire(world, resolver)
    assert (refused.accepted, refused.reason) == (False, "Out of ammunition")


def test_a_target_beyond_weapon_range_is_refused(make_world):
    _, world, resolver = make_world([("rifleman", [0, 1])], [("rifleman", [7, 3])])

    refused, _ = fire(world, resolver)

    assert refused.reason == "Target out of range: distance=7, range=3"


def test_a_killing_hit_destroys_the_target(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [3, 0])], rng_value=0.0
    )
    unit(world, "blue_01").state["hp"] = 5

    _, events = fire(world, resolver)

    assert [e.event_type for e in events][:2] == ["ATTACK", "ENTITY_DESTROYED"]
    assert unit(world, "blue_01").state["status"] == "destroyed"


# ── movement ─────────────────────────────────────────────────────────────────


def test_terrain_cost_limits_how_far_a_unit_moves(make_world):
    _, world, resolver = make_world([("rifleman", [0, 1])], [("rifleman", [7, 3])])

    # open (1) then forest (2) = 3, beyond a move range of 2
    assert move(world, resolver, "red_01", [2, 1]).reason == (
        "Move target out of reach: move_range=2"
    )
    assert move(world, resolver, "red_01", [2, 0]).accepted  # two open cells
    assert world.event_memory[-1].data["cost"] == 2


def test_impassable_and_occupied_cells_are_refused(make_world):
    _, world, resolver = make_world([("rifleman", [1, 2])], [("rifleman", [3, 3])])

    assert move(world, resolver, "red_01", [2, 2]).reason == "Move target is impassable"
    assert move(world, resolver, "red_01", [3, 3]).reason == "Move target occupied"


CORRIDOR = ["^^^^^", ".....", "^^^^^"]


def test_an_enemy_blocks_the_way_but_a_friend_does_not(make_world):
    _, world, resolver = make_world(
        [("rifleman", [0, 1])], [("rifleman", [1, 1])], rows=CORRIDOR
    )
    assert move(world, resolver, "red_01", [2, 1]).reason.startswith(
        "Move target out of reach"
    )

    _, world, resolver = make_world(
        [("rifleman", [0, 1]), ("rifleman", [1, 1])],
        [("rifleman", [4, 1])],
        rows=CORRIDOR,
    )
    assert move(world, resolver, "red_01", [2, 1]).accepted


# ── rally and upkeep ─────────────────────────────────────────────────────────


def rally(world, resolver, entity_id):
    action = Action(world.ids.action(), entity_id, "rally")
    return resolver.execute(world, action)


def test_rally_sheds_suppression_and_restores_morale_up_to_the_start(make_world):
    _, world, resolver = make_world([("rifleman", [0, 1])], [("rifleman", [7, 3])])
    red = unit(world, "red_01")
    red.state.update(suppression=50, morale=60)
    rally(world, resolver, "red_01")
    assert (red.state["suppression"], red.state["morale"]) == (30, 65)

    red.state.update(suppression=0, morale=78)
    rally(world, resolver, "red_01")
    assert red.state["morale"] == 80

    assert rally(world, resolver, "red_01").reason == "Nothing to recover"


def test_upkeep_rallies_only_shaken_units(make_world):
    _, world, _ = make_world(
        [("rifleman", [0, 1]), ("rifleman", [0, 3])], [("rifleman", [7, 3])]
    )
    unit(world, "red_02").state["suppression"] = 20
    unit(world, "blue_01").state["morale"] = 50

    actions = MILITARY.upkeep(world)

    assert [(a.actor_id, a.action_type) for a in actions] == [
        ("red_02", "rally"),
        ("blue_01", "rally"),
    ]


@pytest.mark.parametrize("module", ["handlers.py", "terrain.py", "policy.py"])
def test_pack_rules_and_policy_never_change_the_world(module):
    # The same check the core handlers pass (tests/actions/test_framework.py)
    from actions.test_framework import handler_mutations

    assert handler_mutations((PACK / module).read_text(encoding="utf-8")) == []
