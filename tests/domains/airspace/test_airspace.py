"""Phase 15: the airspace domain pack — model, builder, the sky's actions, HADES."""

import ast
import copy
import json
import random
from functools import cache
from pathlib import Path

import pytest

from skyvault.action import Action, ActionTarget
from skyvault.actions import ActionContext
from skyvault.domains import load_domain
from skyvault.domains.airspace.handlers import airspace_handlers
from skyvault.domains.airspace.model import (
    covered,
    detection_probability,
    distance,
    interception_window,
    step_toward,
)
from skyvault.domains.airspace.pack import AIRSPACE
from skyvault.domains.airspace.policy import AirDefencePolicy
from skyvault.domains.airspace.reference import (
    SPECS,
    load_rules,
    reference_scenarios,
    scenario_path,
)
from skyvault.domains.airspace.scenario import build_airspace_scenario
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.runtime.world import create_world
from skyvault.scenario_loader import load_scenario

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "skyvault"
RULES = load_rules()
NAME = "airspace_defence_001"
HANDLERS = airspace_handlers()
SEEDS = range(42, 52)


def spec() -> dict:
    return json.loads((SPECS / f"{NAME}.json").read_text(encoding="utf-8"))


def built(**hades) -> dict:
    scenario = copy.deepcopy(reference_scenarios()[NAME])
    scenario["world_contract"]["rule_set"]["airspace"]["hades"].update(hades)
    return scenario


def run(scenario: dict, seed: int | None = None) -> dict:
    scenario = copy.deepcopy(scenario)
    if seed is not None:
        scenario["runtime"]["random_seed"] = seed
    return SkyVaultTacticalReferenceEngine(scenario).run()


@cache
def reference_run(seed: int = 42) -> dict:
    return run(built(), seed)


def events(package: dict, *tags: str) -> list[dict]:
    return [e for e in package["event_memory"] if all(t in e["tags"] for t in tags)]


def entity(scenario: dict, entity_id: str) -> dict:
    return next(e for e in scenario["entities"] if e["entity_id"] == entity_id)


# ── the model ────────────────────────────────────────────────────────────────


def test_distance_is_chebyshev():
    assert distance((0, 0), (3, 1)) == 3
    assert distance([5, 5], [2, 9]) == 4
    assert distance((1, 1), (1, 1)) == 0


@pytest.mark.parametrize(
    "position,target,speed,after",
    [
        ([0, 0], [5, 3], 1, [1, 1]),
        ([0, 0], [5, 3], 3, [3, 3]),
        ([0, 0], [5, 3], 9, [5, 3]),  # never overshoots
        ([4, 4], [4, 0], 2, [4, 2]),
        ([4, 4], [4, 4], 2, [4, 4]),
        ([4, 4], [9, 9], 0, [4, 4]),  # speed 0 stays put
    ],
)
def test_a_flyer_steps_straight_at_its_target(position, target, speed, after):
    assert step_toward(position, target, speed) == after


SENSOR = {"at": [0, 0], "range": 8, "detection": 0.8, "low_altitude": 0.5}


@pytest.mark.parametrize(
    "target,altitude,p",
    [
        ((0, 0), "medium", 0.8),  # on top of the sensor: its full detection
        ((4, 0), "medium", 0.6),  # half the range: 0.8 × (1 − 0.5 · 4/8)
        ((8, 8), "medium", 0.4),  # at the edge: 0.8 × 0.5
        ((9, 0), "medium", 0.0),  # beyond range: never
        ((4, 0), "low", 0.3),  # a low flyer: × low_altitude
    ],
)
def test_detection_falls_off_with_distance_and_low_flight(target, altitude, p):
    assert detection_probability(SENSOR, target, altitude) == pytest.approx(p)


def test_detection_has_exact_bounds_at_zero_and_one():
    assert detection_probability({**SENSOR, "detection": 0.0}, (0, 0), "medium") == 0
    certain = {**SENSOR, "detection": 1.0}
    assert detection_probability(certain, (0, 0), "medium") == 1.0
    assert detection_probability(certain, (8, 0), "medium", falloff=0.0) == 1.0
    assert detection_probability({**SENSOR, "range": 0}, (0, 0), "medium") == 0.0
    assert detection_probability({**SENSOR, "detection": 3.0}, (0, 0), "low") == 1.0


def test_coverage_is_every_cell_inside_a_sensor_s_range():
    cells = covered([{"at": [0, 0], "range": 1}], (3, 3))
    assert cells == {(0, 0), (1, 0), (0, 1), (1, 1)}
    assert covered([], (3, 3)) == set()
    both = covered([{"at": [0, 0], "range": 1}, {"at": [2, 2], "range": 0}], (3, 3))
    assert (2, 2) in both and len(both) == 5


def test_an_interception_window_needs_a_track_range_and_time_before_the_hit():
    path = {1: [0, 0], 2: [1, 0], 3: [2, 0], 4: [3, 0], 5: [4, 0]}
    gun = [{"at": [4, 0], "range": 2}]
    assert interception_window(path, gun, 1) == [3, 4, 5]
    assert interception_window(path, gun, 4) == [4, 5]
    assert interception_window(path, gun, 1, until=5) == [3, 4]
    assert interception_window(path, gun, None) == []
    assert interception_window(path, [], 1) == []


# ── the builder ──────────────────────────────────────────────────────────────


def test_the_committed_airspace_scenario_is_what_the_spec_builds():
    for name, scenario in reference_scenarios().items():
        committed = json.loads(scenario_path(name).read_text(encoding="utf-8"))
        assert committed == scenario, name


def test_a_built_airspace_holds_the_defence_and_the_threats_in_reserve():
    scenario = reference_scenarios()[NAME]
    assert scenario["domain"] == "airspace"
    assert scenario["world_contract"]["space_model"]["type"] == "grid"
    kinds = {}
    for e in scenario["entities"]:
        kinds.setdefault(e["entity_type"], []).append(e)
    assert {t: len(v) for t, v in kinds.items()} == {
        "asset": 2,
        "sensor": 4,
        "interceptor": 3,
        "command": 1,
        "drone": 1,
        "threat": 7,
    }
    assert {e["faction"] for e in kinds["threat"]} == {"THREAT"}
    assert all(e["state"]["status"] == "reserve" for e in kinds["threat"])
    assert {e["faction"] for t, v in kinds.items() if t != "threat" for e in v} == {
        "DEFENCE"
    }
    assert entity(scenario, "radar_spare")["state"]["online"] is False
    assert entity(scenario, "radar_north")["state"]["online"] is True
    w2 = entity(scenario, "threat_w2_3")
    assert w2["position"] == [17, 0]
    assert w2["state"]["launch_tick"] == 10
    assert w2["state"]["target"] == "command_post"
    rules = scenario["world_contract"]["rule_set"]["airspace"]
    assert rules["hades"] == RULES["hades"]
    assert rules["command"] == spec()["command"]
    assert rules["size"] == [20, 20]
    assert "description" not in rules
    assert scenario["evaluation"]["success_outcomes"] == ["defended"]
    assert scenario["evaluation"]["perspective"] == "DEFENCE"


def test_the_behaviour_hades_submits_overrides_the_rules_key_by_key():
    scenario = build_airspace_scenario(spec(), RULES, {"salvo": 2})
    hades = scenario["world_contract"]["rule_set"]["airspace"]["hades"]
    assert hades == {**RULES["hades"], "salvo": 2}


def _without(key: str, **change) -> dict:
    s = spec()
    s.update(change)
    return s


@pytest.mark.parametrize(
    "change,message",
    [
        ({"size": [0, 5]}, "positive size"),
        (
            {"assets": [{"id": "a", "at": [20, 0], "value": 1}], "threats": []},
            "outside the airspace",
        ),
        (
            {
                "threats": [
                    {
                        "wave": 1,
                        "tick": 1,
                        "from": [[0, 0]],
                        "target": "moon",
                        "speed": 1,
                        "altitude": "low",
                    }
                ]
            },
            "unknown asset",
        ),
        (
            {
                "threats": [
                    {
                        "wave": 1,
                        "tick": 1,
                        "from": [[0, 0]],
                        "target": "power_station",
                        "speed": 1,
                        "altitude": "high",
                    }
                ]
            },
            "unknown altitude",
        ),
        ({"patrols": [{"id": "p", "route": [], "speed": 1}]}, "has no route"),
        (
            {"patrols": [{"id": "radar_north", "route": [[1, 1]], "speed": 1}]},
            "ids repeat",
        ),
    ],
)
def test_the_builder_refuses_an_airspace_that_does_not_hold_together(change, message):
    with pytest.raises(ValueError, match=message):
        build_airspace_scenario(_without("", **change), RULES)


@pytest.mark.parametrize(
    "behavior,message",
    [
        ({"priority": "loudest"}, "unknown engagement priority"),
        ({"engage_at": 1.5}, "share of the interceptor's range"),
    ],
)
def test_the_builder_refuses_rules_of_engagement_it_cannot_follow(behavior, message):
    with pytest.raises(ValueError, match=message):
        build_airspace_scenario(spec(), RULES, behavior)


# ── the pack in the engine ───────────────────────────────────────────────────


def test_the_airspace_pack_is_loaded_by_name_and_says_what_it_supports():
    assert load_domain("airspace") is AIRSPACE
    assert AIRSPACE.spaces == ("grid",)
    assert AIRSPACE.ends_with_last_faction is False
    assert AIRSPACE.end_reasons == ("threats_resolved",)
    assert set(AIRSPACE.handlers()) == {"launch", "fly", "sense", "engage", "move"}
    assert AIRSPACE.mission_goal(reference_scenarios()[NAME], "DEFENCE") == {
        "type": "defend",
        "assets": ["power_station", "command_post"],
    }


def test_the_core_imports_no_domain_pack():
    for path in SRC.rglob("*.py"):
        if "domains" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "airspace" not in (node.module or ""), path


def test_the_airspace_model_and_metrics_run_no_simulation():
    for name in ("model.py", "metrics.py"):
        tree = ast.parse(
            (SRC / "domains" / "airspace" / name).read_text(encoding="utf-8")
        )
        modules = {
            n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        assert not any("engine" in m or "batch" in m for m in modules), name
        imported = {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        }
        assert "random" not in imported, name


def test_the_reference_airspace_run_reads_like_a_defence():
    """The first run of a new domain, read field by field (Phase 14 change 1)."""
    package = reference_run()
    verdict = package["evaluation_result"]
    assert verdict["winner_or_result"] == "defended"
    assert verdict["termination_reason"] == "termination_condition_met:threats_resolved"
    assert verdict["overall_judgement"]["status"] == "pass"
    assert "maximize_score_by_inaction" not in json.dumps(verdict["anti_gaming"])
    final = package["final_world_state"]
    assert final["tick"] < 30
    threats = [e for e in final["entities"].values() if e["entity_type"] == "threat"]
    assert {t["state"]["status"] for t in threats} == {"destroyed"}
    assert len(events(package, "launch")) == 7
    assert len(events(package, "intercept", "intercepted")) == 7
    assert all(
        a["state"]["hits"] == 0
        for a in final["entities"].values()
        if a["entity_type"] == "asset"
    )


def test_threats_fly_straight_one_cell_a_tick_from_their_launch():
    package = reference_run()
    launch = {e["target_entity_id"]: e["time"] for e in events(package, "launch")}
    assert launch["threat_w1_1"] == 2 and launch["threat_w2_1"] == 10
    for move in events(package, "fly"):
        assert distance(move["data"]["from"], move["data"]["to"]) == 1
        assert move["time"] > launch[move["source"]["actor_id"]]


def test_detection_is_drawn_so_seeds_differ_in_what_is_seen_and_shot():
    seen = set()
    for seed in SEEDS:
        package = reference_run(seed)
        detections = [
            (e["time"], d["sensor"], d["target"])
            for e in events(package, "sense")
            for d in e["data"]["detections"]
        ]
        seen.add(
            (
                tuple(detections),
                package["evaluation_result"]["winner_or_result"],
                package["final_world_state"]["tick"],
            )
        )
    assert len(seen) == len(SEEDS)
    outcomes = {o for _, o, _ in seen}
    assert outcomes == {"defended", "breached"}


def test_the_same_seed_gives_the_same_sky():
    first = run(built(), 7)
    again = run(built(), 7)
    assert first["event_memory"] == again["event_memory"]


def test_a_run_ends_when_every_threat_is_dealt_with_or_at_its_time_limit():
    for seed in SEEDS:
        package = reference_run(seed)
        final = package["final_world_state"]
        statuses = {
            e["state"]["status"]
            for e in final["entities"].values()
            if e["entity_type"] == "threat"
        }
        assert statuses <= {"destroyed", "leaked"}
        assert package["evaluation_result"]["termination_reason"] == (
            "termination_condition_met:threats_resolved"
        )
    slow = built()
    for e in slow["entities"]:
        if e["entity_type"] == "threat":
            e["capabilities"]["speed"] = 0
    for e in slow["entities"]:
        if e["entity_type"] == "interceptor":
            e["state"]["ammo"] = 0
    package = run(slow)
    assert package["final_world_state"]["tick"] == 30
    assert package["evaluation_result"]["termination_reason"] == (
        "duration_limit_reached"
    )
    assert package["evaluation_result"]["winner_or_result"] == "defended"


def test_breached_is_a_failure_and_defended_a_success():
    breached = next(
        reference_run(s)
        for s in SEEDS
        if reference_run(s)["evaluation_result"]["winner_or_result"] == "breached"
    )
    verdict = breached["evaluation_result"]
    assert verdict["scores"]["mission_success"] == 0
    assert verdict["overall_judgement"]["status"] == "fail"
    assert reference_run()["evaluation_result"]["scores"]["mission_success"] == 1


def test_only_drones_and_interceptors_with_a_chance_decide():
    package = reference_run()
    deciders = {
        e["source"]["actor_id"]
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_SELECTED"
    }
    assert deciders == {"skyfox_1", "gun_west", "gun_north", "missile_east"}
    # an interceptor's turn only comes with a cleared threat track in range
    for e in package["event_memory"]:
        if e["event_type"] == "ACTION_SELECTED" and e["source"]["actor_id"] != (
            "skyfox_1"
        ):
            assert e["data"]["action_type"] == "engage"


# ── the sky's actions, one at a time ─────────────────────────────────────────


def airspace_world(scenario: dict | None = None, seed: int = 1):
    world = create_world(scenario or reference_scenarios()[NAME])
    return world, ActionContext(rng=random.Random(seed), system_id="test")


def order(world, actor, action_type, entity_id=None, location=None, **metadata):
    return Action(
        action_id=world.ids.action(),
        actor_id=actor,
        action_type=action_type,
        target=ActionTarget(entity_id=entity_id, location=location),
        metadata=metadata,
    )


def changes_of(consequence, entity_id: str) -> list[dict]:
    return [e.changes for e in consequence.effects if e.entity_id == entity_id]


def test_a_launch_puts_the_threat_in_the_air_where_it_waited():
    world, context = airspace_world()
    done = HANDLERS["launch"].resolve(
        world, order(world, "command", "launch", "threat_w1_1"), context
    )
    (effect,) = done.effects
    assert effect.changes == {"state": {"status": "active"}}
    assert effect.data == {"wave": 1, "at": [0, 8]}


def test_a_threat_that_reaches_its_asset_hits_it_and_is_spent():
    world, context = airspace_world()
    threat = world.get_entity("threat_w1_2")
    threat.position = (9, 10)
    done = HANDLERS["fly"].resolve(world, order(world, "threat_w1_2", "fly"), context)
    assert done.reason == "Fly resolved: hit"
    assert changes_of(done, "threat_w1_2")[1] == {"state": {"status": "leaked"}}
    assert changes_of(done, "power_station") == [{"state": {"hits": 1}}]
    world.get_entity("power_station").state["hits"] = 1
    again = HANDLERS["fly"].resolve(world, order(world, "threat_w1_2", "fly"), context)
    assert changes_of(again, "power_station") == [
        {"state": {"hits": 2, "status": "destroyed"}}
    ]


def test_a_threat_born_on_its_asset_hits_it_on_its_first_flight():
    world, context = airspace_world()
    world.get_entity("threat_w1_1").position = (10, 10)
    done = HANDLERS["fly"].resolve(world, order(world, "threat_w1_1", "fly"), context)
    assert done.reason == "Fly resolved: hit"


def test_a_threat_meeting_a_drone_at_its_altitude_destroys_both():
    world, context = airspace_world()
    threat = world.get_entity("threat_w2_1")
    threat.state.update(status="active")
    drone = world.get_entity("skyfox_1")
    drone.position = (14, 5)
    threat.position = (15, 4)  # on its way to the command post at [12, 9]
    done = HANDLERS["fly"].resolve(world, order(world, "threat_w2_1", "fly"), context)
    destroyed = [e for e in done.effects if e.event_type == "ENTITY_DESTROYED"]
    assert {e.entity_id for e in destroyed} == {"skyfox_1", "threat_w2_1"}
    assert all("collision" in e.tags for e in destroyed)
    # a low flyer passes under a medium-altitude drone
    low = world.get_entity("threat_w1_1")
    low.state.update(status="active")
    drone.position = (1, 9)
    low.position = (0, 8)
    under = HANDLERS["fly"].resolve(world, order(world, "threat_w1_1", "fly"), context)
    assert not [e for e in under.effects if e.event_type == "ENTITY_DESTROYED"]


def sense(world, context):
    return HANDLERS["sense"].resolve(world, order(world, "command", "sense"), context)


def test_a_certain_sensor_sees_every_flyer_in_range_and_none_beyond():
    world, context = airspace_world()
    for sensor in ("radar_north", "radar_south", "eo_tower"):
        world.get_entity(sensor).capabilities.update(detection=1.0, false_alarm=0.0)
    world.rules.require("airspace")["detection"]["falloff"] = 0.0
    for s in ("radar_north", "radar_south"):
        world.get_entity(s).capabilities["low_altitude"] = 1.0
    world.get_entity("threat_w1_1").state["status"] = "active"
    world.get_entity("threat_w1_1").position = (4, 8)  # 6 from radar_north
    world.get_entity("threat_w2_1").state["status"] = "active"  # [19, 0]: 9 away
    (effect,) = sense(world, context).effects
    seen = {(d["sensor"], d["target"]) for d in effect.data["detections"]}
    assert ("radar_north", "threat_w1_1") in seen
    assert not any(t == "threat_w2_1" for _, t in seen)
    assert ("radar_north", "skyfox_1") in seen  # drones are seen too


def test_a_blind_or_offline_sensor_sees_nothing():
    world, context = airspace_world()
    for sensor in ("radar_north", "radar_south", "eo_tower"):
        world.get_entity(sensor).capabilities.update(detection=0.0, false_alarm=0.0)
    world.get_entity("radar_spare").capabilities.update(detection=1.0)
    world.get_entity("threat_w1_1").state["status"] = "active"
    world.get_entity("threat_w1_1").position = (1, 1)  # beside the offline spare
    (effect,) = sense(world, context).effects
    assert effect.data["detections"] == []
    assert effect.data["opened"] == []


def test_a_false_alarm_opens_a_phantom_track_taken_for_a_threat():
    world, context = airspace_world()
    world.get_entity("radar_north").capabilities["false_alarm"] = 1.0
    (effect,) = sense(world, context).effects
    phantom = next(p for p in effect.data["false_alarms"])
    assert phantom["sensor"] == "radar_north"
    assert distance(phantom["at"], (10, 4)) <= 8
    tracks = effect.changes["state"]["tracks"]
    fake = next(t for t in tracks.values() if t["kind"] == "false")
    assert fake["identified"] == "threat" and fake["target"] is None
    assert fake["position"] == phantom["at"]
    quiet, quiet_context = airspace_world()
    for sensor in ("radar_north", "radar_south", "eo_tower"):
        quiet.get_entity(sensor).capabilities["false_alarm"] = 0.0
    (calm,) = sense(quiet, quiet_context).effects
    assert calm.data["false_alarms"] == []


def certain_command(world, identify=1.0):
    for sensor in ("radar_north", "radar_south", "eo_tower"):
        world.get_entity(sensor).capabilities.update(
            detection=1.0, false_alarm=0.0, low_altitude=1.0
        )
    world.rules.require("airspace")["detection"]["falloff"] = 0.0
    world.rules.require("airspace")["command"]["identify"] = identify


def test_a_first_detection_opens_a_track_cleared_after_the_reaction_delay():
    world, context = airspace_world()
    certain_command(world)
    world.tick = 5
    threat = world.get_entity("threat_w1_1")
    threat.state["status"] = "active"
    threat.position = (6, 8)
    (effect,) = sense(world, context).effects
    tracks = effect.changes["state"]["tracks"]
    (track,) = [t for t in tracks.values() if t["target"] == "threat_w1_1"]
    assert track["identified"] == "threat" and track["kind"] == "threat"
    assert track["opened"] == 5 and track["engageable_from"] == 6
    assert effect.changes["state"]["next_track"] == 3  # the drone got T1 or T2
    # seen again: the same track follows it
    world.get_entity("command").state.update(effect.changes["state"])
    world.tick = 6
    threat.position = (7, 8)
    (later,) = sense(world, context).effects
    assert later.data["opened"] == []
    again = later.changes["state"]["tracks"][track["track_id"]]
    assert again["last_seen"] == 6 and again["position"] == [7, 8]


def test_a_track_not_seen_for_longer_than_its_timeout_is_dropped():
    world, context = airspace_world()
    certain_command(world)
    node = world.get_entity("command")
    node.state["tracks"] = {
        "T1": {
            "track_id": "T1",
            "target": None,
            "kind": "false",
            "identified": "threat",
            "opened": 0,
            "last_seen": 0,
            "engageable_from": 1,
            "position": [3, 3],
            "confidence": 0.5,
            "engaged": 0,
        },
    }
    node.state["next_track"] = 2
    world.tick = 2  # timeout 2: still kept
    (kept,) = sense(world, context).effects
    assert "T1" in kept.changes["state"]["tracks"]
    world.tick = 3
    (dropped,) = sense(world, context).effects
    assert "T1" in dropped.data["lost"]
    assert "T1" not in dropped.changes["state"]["tracks"]


def test_identification_can_take_a_friend_for_a_threat_and_a_threat_for_a_friend():
    world, context = airspace_world()
    certain_command(world, identify=0.0)
    threat = world.get_entity("threat_w1_1")
    threat.state["status"] = "active"
    threat.position = (6, 8)
    (effect,) = sense(world, context).effects
    tracks = effect.changes["state"]["tracks"].values()
    by_target = {t["target"]: t for t in tracks}
    assert by_target["skyfox_1"]["identified"] == "threat"
    assert by_target["skyfox_1"]["kind"] == "friend"
    assert by_target["threat_w1_1"]["identified"] == "friend"


def engage_world(track_kind="threat", target="threat_w1_1", **gun):
    world, context = airspace_world()
    if target:
        world.get_entity(target).state["status"] = "active"
        world.get_entity(target).position = (7, 10)
    world.get_entity("gun_west").capabilities.update(gun)
    world.tick = 4
    world.get_entity("command").state["tracks"] = {
        "T1": {
            "track_id": "T1",
            "target": target,
            "kind": track_kind,
            "identified": "threat",
            "opened": 2,
            "last_seen": 4,
            "engageable_from": 3,
            "position": [7, 10],
            "confidence": 0.6,
            "engaged": 0,
        },
    }
    return world, context


@pytest.mark.parametrize(
    "setup,reason",
    [
        (lambda w: w.get_entity("gun_west").state.update(ammo=0), "Out of ammunition"),
        (lambda w: w.get_entity("gun_west").state.update(ready_at=5), "Reloading"),
        (lambda w: w.get_entity("command").state.update(tracks={}), "No such track"),
        (
            lambda w: w.get_entity("command")
            .state["tracks"]["T1"]
            .update(engageable_from=5),
            "not cleared to engage yet",
        ),
        (
            lambda w: w.get_entity("command")
            .state["tracks"]["T1"]
            .update(position=[1, 10]),
            "out of range",
        ),
    ],
)
def test_an_interceptor_fires_only_when_it_can(setup, reason):
    world, context = engage_world()
    setup(world)
    verdict = HANDLERS["engage"].validate(
        world, order(world, "gun_west", "engage", track="T1"), context
    )
    assert not verdict.valid and reason in verdict.reason


def test_only_interceptors_engage_and_only_drones_fly_on_orders():
    world, context = engage_world()
    no = HANDLERS["engage"].validate(
        world, order(world, "skyfox_1", "engage", track="T1"), context
    )
    assert not no.valid and "Only interceptors" in no.reason
    nope = HANDLERS["move"].validate(
        world, order(world, "gun_west", "move", location=(9, 9)), context
    )
    assert not nope.valid and "Only drones" in nope.reason


def test_a_certain_shot_destroys_its_target_and_the_gun_reloads():
    world, context = engage_world(kill=1.0)
    action = order(world, "gun_west", "engage", track="T1", shots=1)
    assert HANDLERS["engage"].validate(world, action, context).valid
    done = HANDLERS["engage"].resolve(world, action, context)
    assert changes_of(done, "gun_west") == [{"state": {"ammo": 29, "ready_at": 5}}]
    (destroyed,) = [e for e in done.effects if e.event_type == "ENTITY_DESTROYED"]
    assert destroyed.entity_id == "threat_w1_1"
    assert "intercepted" in destroyed.tags
    assert "T1" not in changes_of(done, "command")[0]["state"]["tracks"]


def test_a_shot_that_cannot_kill_misses_and_the_track_stays():
    world, context = engage_world(kill=0.0)
    done = HANDLERS["engage"].resolve(
        world, order(world, "gun_west", "engage", track="T1", shots=3), context
    )
    assert [e.event_type for e in done.effects][-1] == "MISS"
    assert done.effects[0].data["shots"] == 3
    tracks = changes_of(done, "command")[0]["state"]["tracks"]
    assert tracks["T1"]["engaged"] == 1


def test_a_salvo_is_cut_to_the_ammunition_left():
    world, context = engage_world(kill=0.0)
    world.get_entity("gun_west").state["ammo"] = 2
    done = HANDLERS["engage"].resolve(
        world, order(world, "gun_west", "engage", track="T1", shots=5), context
    )
    assert changes_of(done, "gun_west")[0]["state"]["ammo"] == 0


def test_shooting_down_a_friend_taken_for_a_threat_is_fratricide():
    world, context = engage_world(track_kind="friend", target="skyfox_1", kill=1.0)
    done = HANDLERS["engage"].resolve(
        world, order(world, "gun_west", "engage", track="T1"), context
    )
    (destroyed,) = [e for e in done.effects if e.event_type == "ENTITY_DESTROYED"]
    assert destroyed.entity_id == "skyfox_1" and "fratricide" in destroyed.tags


def test_a_phantom_absorbs_the_salvo():
    world, context = engage_world(track_kind="false", target=None, kill=1.0)
    done = HANDLERS["engage"].resolve(
        world, order(world, "gun_west", "engage", track="T1", shots=2), context
    )
    assert done.effects[-1].event_type == "MISS"
    assert changes_of(done, "gun_west")[0]["state"]["ammo"] == 28


def test_a_drone_moves_within_its_speed_and_follows_its_route():
    world, context = airspace_world()
    far = HANDLERS["move"].validate(
        world, order(world, "skyfox_1", "move", location=(8, 6)), context
    )
    assert not far.valid and "out of reach" in far.reason
    outside = HANDLERS["move"].validate(
        world, order(world, "skyfox_1", "move", location=(20, 6)), context
    )
    assert not outside.valid and "outside the airspace" in outside.reason
    step = order(world, "skyfox_1", "move", location=(7, 6))
    assert HANDLERS["move"].validate(world, step, context).valid
    done = HANDLERS["move"].resolve(world, step, context)
    assert done.effects[0].changes == {"position": [7, 6], "state": {"leg": 1}}
    drone = world.get_entity("skyfox_1")
    drone.position, drone.state["leg"] = (13, 6), 1
    arrive = HANDLERS["move"].resolve(
        world, order(world, "skyfox_1", "move", location=(14, 6)), context
    )
    assert arrive.effects[0].changes["state"] == {"leg": 2}


# ── HADES's rules of engagement ──────────────────────────────────────────────


def track(key, target, position, opened=1, confidence=0.6, identified="threat"):
    return {
        "track_id": key,
        "target": target,
        "kind": "threat",
        "identified": identified,
        "opened": opened,
        "last_seen": 4,
        "engageable_from": opened + 1,
        "position": position,
        "confidence": confidence,
        "engaged": 0,
    }


def policy_world(*tracks):
    world, _ = airspace_world()
    world.tick = 4
    world.get_entity("command").state["tracks"] = {t["track_id"]: t for t in tracks}
    return world


def test_the_baseline_fires_one_shot_at_the_track_nearest_an_asset():
    world = policy_world(
        track("T1", "threat_w1_1", [7, 10], opened=1),
        track("T2", "threat_w1_2", [8, 11], opened=2),
    )
    action = AirDefencePolicy().decide_action(world, world.get_entity("gun_west"))
    assert action.action_type == "engage"
    assert action.metadata == {"track": "T2", "shots": 1}
    assert action.target.entity_id == "threat_w1_2"


def test_first_tracked_salvo_engage_at_and_hold_fire_change_the_decision():
    world = policy_world(
        track("T1", "threat_w1_1", [7, 10], opened=1, confidence=0.3),
        track("T2", "threat_w1_2", [8, 11], opened=2),
    )
    gun = world.get_entity("gun_west")
    first = AirDefencePolicy({"priority": "first_tracked", "salvo": 3})
    assert first.decide_action(world, gun).metadata == {"track": "T1", "shots": 3}
    held = AirDefencePolicy({"priority": "first_tracked", "hold_fire_below": 0.5})
    assert held.decide_action(world, gun).metadata["track"] == "T2"
    close = AirDefencePolicy({"engage_at": 0.4})  # 3 × 0.4: only 1 cell out
    assert close.decide_action(world, gun).metadata["track"] == "T2"
    assert AirDefencePolicy({"engage_at": 0.0}).decide_action(world, gun) is None


def test_hades_holds_fire_on_friends_uncleared_tracks_and_when_it_cannot_fire():
    friend = track("T1", "skyfox_1", [8, 10], identified="friend")
    fresh = track("T2", "threat_w1_1", [8, 10], opened=4)
    world = policy_world(friend, fresh)
    gun = world.get_entity("gun_west")
    assert AirDefencePolicy().decide_action(world, gun) is None
    ready = policy_world(track("T3", "threat_w1_1", [8, 10]))
    gun = ready.get_entity("gun_west")
    gun.state["ammo"] = 0
    assert AirDefencePolicy().decide_action(ready, gun) is None
    gun.state.update(ammo=5, ready_at=9)
    assert AirDefencePolicy().decide_action(ready, gun) is None
    assert AirDefencePolicy().decide_action(ready, ready.get_entity("radar_north")) is (
        None
    )


@pytest.mark.parametrize(
    "behavior,message",
    [
        ({"aggression": 1}, "unknown rules of engagement"),
        ({"priority": "loudest"}, "unknown engagement priority"),
        ({"engage_at": -0.1}, "share of the interceptor's range"),
        ({"salvo": 0}, "at least one shot"),
    ],
)
def test_the_policy_refuses_rules_it_cannot_follow(behavior, message):
    with pytest.raises(ValueError, match=message):
        AirDefencePolicy(behavior)


def test_a_drone_patrols_its_route_and_rests_when_it_cannot_move():
    world, _ = airspace_world()
    drone = world.get_entity("skyfox_1")
    step = AirDefencePolicy().decide_action(world, drone)
    assert step.action_type == "move" and step.target.location == (7, 6)
    drone.capabilities["speed"] = 0
    assert AirDefencePolicy().decide_action(world, drone) is None


def test_an_interceptor_has_a_turn_only_with_an_opportunity():
    world = policy_world(track("T1", "threat_w1_1", [8, 10]))
    gun = world.get_entity("gun_west")
    assert AIRSPACE.acts(gun, world)
    assert not AIRSPACE.acts(gun)  # no world: no opportunity to judge
    gun.state["ready_at"] = 9
    assert not AIRSPACE.acts(gun, world)
    gun.state.update(ready_at=0, ammo=0)
    assert not AIRSPACE.acts(gun, world)
    quiet = policy_world(track("T1", "threat_w1_1", [8, 10], identified="friend"))
    assert not AIRSPACE.acts(quiet.get_entity("gun_west"), quiet)
    assert AIRSPACE.acts(quiet.get_entity("skyfox_1"), quiet)
    assert not AIRSPACE.acts(quiet.get_entity("radar_north"), quiet)


def test_hades_rules_are_a_policy_a_run_can_name():
    scenario = built()
    scenario["runtime"]["policy"] = {"name": "hades_rules", "params": {"salvo": 2}}
    package = run(scenario)
    shots = {
        e["data"]["shots"]
        for e in events(package, "engage")
        if e["event_type"] == "ENTITY_STATE_CHANGED" and "track" not in e["tags"]
    }
    assert shots <= {1, 2} and 2 in shots  # salvo 2, cut to ammo at the end
    engine = SkyVaultTacticalReferenceEngine(load_scenario(scenario_path(NAME)))
    assert type(engine.policy).__name__ == "AirDefencePolicy"


# ── acceptance 1: the rules HADES submits change the outcome ─────────────────


def leaks(package: dict) -> int:
    return len(events(package, "leak"))


def test_closing_in_lets_more_threats_through_than_the_baseline():
    baseline = sum(leaks(reference_run(s)) for s in SEEDS)
    close = sum(leaks(run(built(engage_at=0.5), s)) for s in SEEDS)
    assert close > baseline


def test_a_rule_that_changes_nothing_leaves_the_run_unchanged():
    same = run(built(salvo=1, engage_at=1.0, priority="nearest_to_asset"))
    assert same["event_memory"] == reference_run()["event_memory"]


# ── boundary values ──────────────────────────────────────────────────────────


def boundary(**change) -> dict:
    s = spec()
    s.update(change)
    return build_airspace_scenario(s, RULES)


@pytest.mark.parametrize(
    "change",
    [
        {"sensors": []},
        {"interceptors": []},
        {"patrols": []},
        {"threats": []},
        {
            "threats": [
                {
                    "wave": 1,
                    "tick": 1,
                    "from": [],
                    "target": "power_station",
                    "speed": 1,
                    "altitude": "low",
                }
            ]
        },
        {
            "threats": [
                {
                    "wave": 1,
                    "tick": 1,
                    "from": [[10, 10]],
                    "target": "power_station",
                    "speed": 1,
                    "altitude": "low",
                }
            ]
        },
    ],
)
def test_boundary_airspaces_run_to_the_end(change):
    package = run(boundary(**change))
    assert package["evaluation_result"]["winner_or_result"] in ("defended", "breached")
    assert package["final_world_state"]["tick"] <= 30


def test_without_sensors_nothing_is_seen_and_every_threat_gets_through():
    package = run(boundary(sensors=[]))
    assert events(package, "intercept") == []
    assert leaks(package) == 7
    assert package["evaluation_result"]["winner_or_result"] == "breached"


def test_with_no_threats_the_defence_is_untroubled_from_the_first_tick():
    package = run(boundary(threats=[]))
    assert package["evaluation_result"]["winner_or_result"] == "defended"
    assert package["final_world_state"]["tick"] <= 1


def test_a_threat_born_on_its_asset_hits_at_once():
    s = boundary(
        threats=[
            {
                "wave": 1,
                "tick": 1,
                "from": [[10, 10]],
                "target": "power_station",
                "speed": 1,
                "altitude": "low",
            }
        ]
    )
    package = run(s)
    (hit,) = events(package, "leak")
    assert hit["time"] == 2  # launched at 1, flies at 2
    assert package["evaluation_result"]["winner_or_result"] == "breached"


def test_out_of_ammunition_the_defence_never_fires():
    scenario = built()
    for e in scenario["entities"]:
        if e["entity_type"] == "interceptor":
            e["state"]["ammo"] = 0
    package = run(scenario)
    assert events(package, "engage") == []
    assert leaks(package) == 7
