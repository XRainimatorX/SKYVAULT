"""Profiles validate and fill defaults; specs build valid scenarios or say why not."""

import copy
import json

import pytest
from conftest import REPO_ROOT, load_spec, spec

from skyvault.contracts import validate_scenario
from skyvault.domains.military import build_scenario, validate_profiles
from skyvault.domains.military.profiles import ProfileError

RAW = json.loads(
    (REPO_ROOT / "data" / "domains" / "military" / "profiles.json").read_text()
)


def test_all_nine_profiles_load(profiles):
    for group in (
        "units",
        "formations",
        "terrain",
        "sensors",
        "weapons",
        "logistics",
        "morale",
        "command_delay",
        "missions",
    ):
        assert profiles[group], group
    assert profiles["morale"]["suppress_threshold"] == 60
    assert profiles["morale"]["panic_threshold"] == 85
    assert profiles["morale"]["retreat_threshold"] == 25
    assert {p["delay_ticks"] for p in profiles["command_delay"].values()} == {
        0,
        1,
        2,
        3,
    }


def test_left_out_defaults_are_filled_in():
    raw = copy.deepcopy(RAW)
    del raw["morale"]
    del raw["logistics"]["supply_range"]
    del raw["weapons"]["rifle"]["ammo_per_shot"]

    filled = validate_profiles(raw)

    assert filled["morale"]["panic_threshold"] == 85
    assert filled["logistics"]["supply_range"] == 1
    assert filled["weapons"]["rifle"]["ammo_per_shot"] == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p["units"]["rifleman"].update(sensor="radar"), "unknown sensor"),
        (lambda p: p["units"]["rifleman"].update(weapon="laser"), "unknown weapon"),
        (lambda p: p["terrain"]["road"].update(symbol="."), "symbols must be unique"),
        (
            lambda p: p["command_delay"]["radio"].update(delay_ticks=4),
            "less than or equal to 3",
        ),
        (
            lambda p: p["command_delay"]["radio"].update(loss_prob=0.3),
            "less than or equal to 0.2",
        ),
        (lambda p: p["morale"].update(suppress_threshold=90), "must not exceed"),
    ],
)
def test_broken_profiles_are_refused(change, message):
    raw = copy.deepcopy(RAW)
    change(raw)

    with pytest.raises(ProfileError, match=message):
        validate_profiles(raw)


@pytest.mark.parametrize(
    ("name", "units"),
    [
        ("military_squad_001", 8),
        ("military_urban_001", 15),
        ("military_mountain_001", 13),
        ("military_junction_001", 9),
    ],
)
def test_every_reference_spec_builds_a_valid_scenario(profiles, name, units):
    scenario = build_scenario(load_spec(name), profiles)

    assert validate_scenario(scenario) == scenario
    assert scenario["domain"] == "military"
    assert len(scenario["entities"]) == units


def test_units_carry_their_profiles(profiles):
    scenario = build_scenario(load_spec("military_squad_001"), profiles)
    leader, rifleman = scenario["entities"][0], scenario["entities"][1]

    assert (leader["entity_id"], leader["name"]) == ("red_01", "Red Alpha Squad Leader")
    assert rifleman["name"] == "Red Alpha Rifleman 1"
    assert rifleman["position"] == [0, 1]  # wedge slot 2 from the anchor [0, 0]
    assert rifleman["capabilities"]["attack_range"] == 3
    assert rifleman["capabilities"]["sensor_range"] == 5
    assert rifleman["state"] == {
        "hp": 30,
        "ammo": 12,
        "morale": 80,
        "suppression": 0,
        "readiness": 1.0,
        "status": "active",
    }
    world = scenario["world_contract"]
    assert world["environment_state"]["terrain"]["legend"]["f"] == "forest"
    assert world["resource_state"] == {"ammo": 40.0}
    assert world["rule_set"]["military"]["factions"]["BLUE"]["mission"] == {
        "type": "hold",
        "objective": [[7, 7]],
    }
    assert world["rule_set"]["military"]["factions"]["RED"]["command"] == {
        "delay_ticks": 1,
        "loss_prob": 0.05,
    }


def test_logistics_units_get_a_supply_range(profiles):
    scenario = build_scenario(load_spec("military_junction_001"), profiles)
    logistics = [e for e in scenario["entities"] if e["entity_type"] == "logistics"]

    assert [e["capabilities"]["supply_range"] for e in logistics] == [1]
    assert all(
        "supply_range" not in e["capabilities"]
        for e in scenario["entities"]
        if e not in logistics
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda s: s["factions"]["RED"]["groups"][0].update(anchor=[9, 0]),
            "outside the map",
        ),
        (
            lambda s: s["factions"]["RED"]["groups"][0].update(anchor=[2, 2]),
            "stands on rock",
        ),
        (
            lambda s: s.update(map=["..?.....", "........", "........", "........"]),
            "unknown terrain symbol",
        ),
        (lambda s: s.update(map=["....", "..."]), "rectangle"),
        (
            lambda s: s["factions"]["RED"]["groups"][0].update(units=["tank"]),
            "unknown unit type",
        ),
        (lambda s: s["factions"]["RED"].update(doctrine="blitz"), "unknown doctrine"),
        (
            lambda s: s["factions"]["RED"].update(command="telepathy"),
            "unknown command profile",
        ),
        (
            lambda s: s["factions"]["RED"].update(mission={"type": "seize"}),
            "needs an objective",
        ),
        (
            lambda s: s["factions"]["RED"]["groups"][0].update(units=["rifleman"] * 7),
            "slots",
        ),
    ],
)
def test_a_broken_spec_is_refused(profiles, change, message):
    broken = spec([("rifleman", [0, 0])], [("rifleman", [7, 3])])
    change(broken)

    with pytest.raises(ValueError, match=message):
        build_scenario(broken, profiles)
