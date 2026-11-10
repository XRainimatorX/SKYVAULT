"""Phase 14: the city domain pack — model, builder, engine opening, three dynamics."""

import ast
import copy
import json
import sys
from functools import cache
from pathlib import Path

import pytest

from skyvault.domains import load_domain
from skyvault.domains.city.model import (
    consumption,
    eta,
    order_delta,
    order_state,
    power_flow,
)
from skyvault.domains.city.pack import CITY
from skyvault.domains.city.reference import (
    SPECS,
    load_rules,
    reference_scenarios,
    scenario_path,
)
from skyvault.domains.city.scenario import build_city_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/
from layers import imported, modules_below  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "skyvault"
RULES = load_rules()
SEEDS = range(42, 52)


def spec(name: str = "city_takeover_001") -> dict:
    return json.loads((SPECS / f"{name}.json").read_text(encoding="utf-8"))


def built(name: str = "city_takeover_001", **rule_changes) -> dict:
    scenario = copy.deepcopy(reference_scenarios()[name])
    city = scenario["world_contract"]["rule_set"]["city"]
    for path, value in rule_changes.items():
        group, key = path.split("__")
        city[group][key] = value
    return scenario


def run(scenario: dict, seed: int | None = None) -> dict:
    scenario = copy.deepcopy(scenario)
    if seed is not None:
        scenario["runtime"]["random_seed"] = seed
    return SkyVaultEngine(scenario).run()


@cache
def reference_run(name: str, seed: int = 42, delay: float = 1.0) -> dict:
    return run(built(name, supply__delay_factor=delay), seed)


def events(package: dict, *tags: str) -> list[dict]:
    return [e for e in package["event_memory"] if all(t in e["tags"] for t in tags)]


def end_order(package: dict, scenario: dict) -> float:
    return CITY.governance_outcome(package, scenario)["components"]["order"]


# ── the model ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,band",
    [
        (100, "stable"),
        (70, "stable"),
        (69.99, "tense"),
        (50, "tense"),
        (49.99, "unrest"),
        (30, "unrest"),
        (29.99, "riot"),
        (0, "riot"),
    ],
)
def test_order_bands_have_exact_thresholds(value, band):
    assert order_state(value, RULES) == band


def conditions(**changes):
    base = {
        "food_left": 5.0,
        "eaten": 0.5,
        "powered": True,
        "medical": 0.5,
        "administration": 0.4,
        "population": 100_000,
        "riot_next_door": False,
    }
    return {**base, **changes}


def test_a_fed_lit_district_at_par_recovers_by_the_recovery_rate():
    parts = order_delta(conditions(), RULES)
    assert parts["total"] == RULES["order"]["recovery"]
    assert parts["medical"] == parts["administration"] == 0


def test_hunger_hurts_more_where_more_people_live_and_stops_recovery():
    small = order_delta(conditions(food_left=0, population=10_000), RULES)
    big = order_delta(conditions(food_left=0, population=100_000), RULES)
    assert small["recovery"] == big["recovery"] == 0
    assert big["hunger"] == RULES["order"]["hunger"] * 2  # 1 + 1.0 × 100k / 100k
    assert big["hunger"] < small["hunger"] < 0


def test_short_food_is_not_hunger():
    # food left, but less than two ticks of eating: short, still fed
    parts = order_delta(conditions(food_left=0.9, eaten=0.5), RULES)
    assert parts["short_food"] == RULES["order"]["short_food"]
    assert parts["hunger"] == 0 and parts["recovery"] == RULES["order"]["recovery"]


def test_darkness_and_a_riot_next_door_pull_order_down():
    parts = order_delta(conditions(powered=False, riot_next_door=True), RULES)
    assert parts["dark"] == RULES["order"]["dark"]
    assert parts["riot_next_door"] == RULES["order"]["riot_neighbour"]
    assert parts["recovery"] == 0


GRID = {
    "a": {"capacity": 10, "serves": ["d1", "d2"], "backup": ["b", "c"], "online": True},
    "b": {"capacity": 6, "serves": ["d3"], "backup": ["a"], "online": True},
    "c": {"capacity": 6, "serves": ["d4"], "backup": [], "online": True},
}
LOADS = {"d1": 3.0, "d2": 4.0, "d3": 2.0, "d4": 2.0}


def test_every_district_is_fed_by_its_own_substation_when_all_are_online():
    flow = power_flow(GRID, LOADS)
    assert flow["feeds"] == {"d1": "a", "d2": "a", "d3": "b", "d4": "c"}
    assert flow["load"] == {"a": 7.0, "b": 2.0, "c": 2.0}
    assert flow["overloaded"] == [] and flow["moved"] == {}


def test_a_failed_substation_hands_its_districts_to_its_backups_in_turn():
    grid = copy.deepcopy(GRID)
    grid["a"]["online"] = False
    flow = power_flow(grid, LOADS)
    assert flow["feeds"]["d1"] == "b" and flow["feeds"]["d2"] == "c"
    assert flow["load"] == {"a": 0.0, "b": 5.0, "c": 6.0}
    # c carries exactly its capacity: full is not overloaded
    assert flow["overloaded"] == []
    assert flow["moved"] == {"d1": "a", "d2": "a"}


def test_a_tripped_substation_keeps_its_districts_dark():
    grid = copy.deepcopy(GRID)
    grid["a"].update(online=False, transfers=False)
    flow = power_flow(grid, LOADS)
    assert flow["feeds"]["d1"] is None and flow["feeds"]["d2"] is None
    assert flow["moved"] == {}


def test_with_no_backup_online_the_districts_go_dark_and_overload_is_strict():
    grid = copy.deepcopy(GRID)
    grid["c"]["online"] = False
    grid["b"]["capacity"] = 1.9
    flow = power_flow(grid, LOADS)
    assert flow["feeds"]["d4"] is None
    assert flow["overloaded"] == ["b"]


@pytest.mark.parametrize(
    "distance,factor,ticks",
    [(0, 3.0, 0), (1, 1.0, 1), (0.2, 1.0, 1), (2, 1.5, 3), (3, 1.0, 3), (5, 2.0, 10)],
)
def test_a_trip_takes_the_route_times_the_factor_rounded_up(distance, factor, ticks):
    assert eta(distance, factor) == ticks


def test_a_trip_without_a_road_is_refused():
    with pytest.raises(ValueError, match="no road"):
        eta(float("inf"), 1.0)


# ── the scenario ─────────────────────────────────────────────────────────────


def test_the_committed_city_scenarios_are_what_the_specs_build():
    for name, scenario in reference_scenarios().items():
        committed = json.loads(scenario_path(name).read_text(encoding="utf-8"))
        assert committed == scenario, f"rerun scripts/build_city_scenarios.py ({name})"


def test_a_built_city_is_a_road_network_of_one_faction():
    scenario = reference_scenarios()["city_takeover_001"]
    space = scenario["world_contract"]["space_model"]
    assert space["type"] == "network"
    assert ["center", "market", 1.0] in space["edges"]
    assert {e["faction"] for e in scenario["entities"]} == {"CITY"}
    kinds = sorted({e["entity_type"] for e in scenario["entities"]})
    assert kinds == [
        "city_office",
        "convoy",
        "depot",
        "district",
        "police",
        "power_plant",
        "repair_crew",
        "substation",
    ]
    south = next(e for e in scenario["entities"] if e["entity_id"] == "south")
    assert south["state"]["order_state"] == "riot"  # 20 < 30
    assert scenario["evaluation"]["success_outcomes"] == [
        "order_restored",
        "order_held",
    ]


@pytest.mark.parametrize(
    "change,message",
    [
        (lambda s: s["roads"].append(["center", "moon", 1]), "leaves the city"),
        (lambda s: s["roads"].append(["center", "west", -1]), "must take some time"),
        (lambda s: s["roads"].append(["center", "west", 0]), "must take some time"),
        (lambda s: s["depots"][0].update(at="moon"), "does not have"),
        (
            lambda s: s["power"]["substations"][1]["serves"].append("center"),
            "served by both",
        ),
        (
            lambda s: s["power"]["substations"][0]["backup"].append("sub_moon"),
            "unknown backup",
        ),
        (
            lambda s: s["incidents"].append(
                {"tick": 3, "type": "flood", "target": "x"}
            ),
            "unknown incident",
        ),
        (
            lambda s: s["incidents"].append(
                {"tick": 3, "type": "substation_failure", "target": "sub_moon"}
            ),
            "names nothing",
        ),
        (lambda s: s["districts"][0].update(public_order=120), "outside 0–100"),
        (
            lambda s: s["districts"].append(dict(s["districts"][0])),
            "district ids repeat",
        ),
        (
            lambda s: s["power"]["substations"][0]["serves"].append("moon"),
            "unknown district",
        ),
        (lambda s: s["districts"][0].update(population=-1), "negative population"),
        (
            lambda s: s["forces"]["police"].append({"id": "convoy_1", "at": "center"}),
            "ids repeat",
        ),
    ],
)
def test_the_builder_refuses_a_city_that_does_not_hold_together(change, message):
    broken = spec()
    change(broken)
    with pytest.raises(ValueError, match=message):
        build_city_scenario(broken, RULES)


# ── the engine opens to other spaces only through a pack ─────────────────────


def test_a_graph_world_without_a_domain_is_still_refused():
    scenario = load_scenario(
        ROOT / "tests/fixtures/reference/scenarios/tactical_reference_001/v0.1.json"
    )
    scenario["world_contract"]["space_model"] = {
        "type": "graph",
        "nodes": ["A", "B"],
        "edges": [["A", "B"]],
    }
    with pytest.raises(ValueError, match="needs a grid space and a tick clock"):
        SkyVaultEngine(scenario)


def test_the_city_pack_is_loaded_by_name_and_says_what_it_supports():
    pack = load_domain("city")
    assert pack is CITY
    assert pack.spaces == ("network", "graph") and pack.ends_with_last_faction is False


def test_a_city_runs_to_its_time_limit_with_one_faction():
    package = reference_run("city_takeover_001")
    assert package["final_world_state"]["tick"] == 30
    assert (
        package["evaluation_result"]["termination_reason"] == "duration_limit_reached"
    )
    assert package["evaluation_result"]["active_factions"] == ["CITY"]


def test_only_actors_off_the_road_decide():
    package = reference_run("city_takeover_001")
    deciders = {
        e["source"]["actor_id"]
        for e in package["event_memory"]
        if e["event_type"] in ("ACTION_SELECTED", "NO_ACTION")
    }
    kinds = {
        e["entity_id"]: e["entity_type"]
        for e in package["initial_world_state"]["entities"].values()
    }
    assert {kinds[d] for d in deciders} == {
        "police",
        "convoy",
        "repair_crew",
        "city_office",
    }
    # a traveller decides nothing between leaving and arriving
    for leave in events(package, "departure"):
        actor, arrives = (
            leave["target_entity_id"],
            leave["after_state"]["state"]["arrives_at"],
        )
        on_road = [
            e
            for e in package["event_memory"]
            if e["event_type"] == "ACTION_SELECTED"
            and e["source"]["actor_id"] == actor
            and leave["time"] < e["time"] < arrives
        ]
        assert on_road == []


def test_the_core_imports_no_domain_pack():
    # every module below the domains layer (tests/layers.py: a positive list)
    below = modules_below("domains")
    assert below
    for module in below:
        assert not any("city" in m for m in imported(module)), module


def test_the_city_model_and_score_run_no_simulation():
    for name in ("model.py", "score.py"):
        tree = ast.parse((SRC / "domains" / "city" / name).read_text(encoding="utf-8"))
        modules = {
            n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        assert not any("engine" in m or "batch" in m for m in modules), name


# ── acceptance 1: order is restored ──────────────────────────────────────────


def test_the_takeover_restores_order_in_every_seed():
    for seed in SEEDS:
        package = reference_run("city_takeover_001", seed)
        verdict = package["evaluation_result"]
        assert verdict["winner_or_result"] == "order_restored", seed
        assert verdict["overall_judgement"]["status"] == "pass", seed
        assert end_order(package, built()) >= 0.7


def test_without_police_or_convoys_order_is_not_restored():
    city = spec()
    city["forces"]["police"] = []
    city["forces"]["convoys"] = []
    package = run(build_city_scenario(city, RULES))
    verdict = package["evaluation_result"]
    assert verdict["winner_or_result"] in ("order_not_restored", "governance_collapsed")
    assert verdict["overall_judgement"]["status"] == "fail"


def test_a_city_that_was_never_disordered_is_held_not_restored():
    calm = spec()
    for district in calm["districts"]:
        district.update(public_order=90, food=20)
    package = run(build_city_scenario(calm, RULES))
    assert package["evaluation_result"]["winner_or_result"] == "order_held"
    assert package["evaluation_result"]["overall_judgement"]["status"] == "pass"


def test_order_changes_band_with_a_recorded_from_and_to():
    package = reference_run("city_takeover_001")
    south = [
        e for e in events(package, "public_order") if e["target_entity_id"] == "south"
    ]
    assert south[0]["data"]["from_state"] == "riot"  # 20 at the start
    assert south[-1]["data"]["to_state"] == "stable"
    for before, after in zip(south, south[1:], strict=False):
        assert after["data"]["from_state"] == before["data"]["to_state"]
    for event in south:
        assert event["after_state"]["state"]["order_state"] == event["data"]["to_state"]


# ── acceptance 2: a blackout cascades ────────────────────────────────────────


def test_a_failed_substation_trips_the_ones_that_took_its_load():
    package = reference_run("city_blackout_001")
    (failure,) = events(package, "power", "failure")
    assert (failure["time"], failure["target_entity_id"]) == (4, "sub_center")
    trips = events(package, "power", "trip")
    first = [t for t in trips if t["time"] == 5]
    assert sorted(t["target_entity_id"] for t in first) == ["sub_north", "sub_south"]
    for trip in first:
        assert trip["data"]["load_from"] == ["sub_center"]
        assert trip["data"]["caused_by_event"] == [failure["event_id"]]
        assert trip["data"]["load"] > trip["data"]["capacity"]
    # strain first (tick 4), trip one tick later
    strained = events(package, "power", "overload")
    assert {e["target_entity_id"] for e in strained if e["time"] == 4} == {
        "sub_north",
        "sub_south",
    }


def test_the_cascade_darkens_the_districts_and_order_falls():
    package = reference_run("city_blackout_001")
    dark = {
        e["target_entity_id"] for e in events(package, "blackout") if e["time"] == 5
    }
    assert dark == {"center", "market", "north", "east", "west", "south", "harbor"}
    assert end_order(package, built("city_blackout_001")) < end_order(
        reference_run("city_takeover_001"), built()
    )
    assert package["evaluation_result"]["overall_judgement"]["status"] == "fail"


def test_without_an_incident_nothing_fails_trips_or_goes_dark():
    package = reference_run("city_takeover_001")
    assert events(package, "power", "failure") == []
    assert events(package, "power", "trip") == []
    assert events(package, "blackout") == []


def test_a_failure_the_backups_can_carry_is_not_a_cascade():
    sturdy = spec("city_blackout_001")
    for sub in sturdy["power"]["substations"]:
        sub["capacity"] = 30
    package = run(build_city_scenario(sturdy, RULES))
    assert len(events(package, "power", "failure")) == 1
    assert events(package, "power", "trip") == []
    assert events(package, "blackout") == []


def test_the_crew_restores_the_failure_before_the_trips_and_nothing_retrips():
    package = reference_run("city_blackout_001")
    restored = [(e["time"], e["target_entity_id"]) for e in events(package, "restored")]
    assert restored[0][1] == "sub_center"
    assert {s for _, s in restored} == {"sub_center", "sub_north", "sub_south"}
    last = max(t for t, _ in restored)
    assert [e for e in events(package, "power", "trip") if e["time"] > last] == []


# ── acceptance 3: supply delay and public order ──────────────────────────────


def test_late_supplies_arrive_late_by_the_delay_factor():
    for delay in (1.0, 3.0):
        package = reference_run("city_takeover_001", 42, delay)
        leaves = {
            (e["target_entity_id"], e["time"]): e["data"]["ticks"]
            for e in events(package, "dispatch", "departure")
        }
        assert leaves
        assert all(ticks >= 1 for ticks in leaves.values())
        deliveries = [e for e in package["event_memory"] if e["event_type"] == "SUPPLY"]
        for delivery in deliveries:
            sent = delivery["data"]["dispatched_at"]
            assert (delivery["data"]["convoy"], sent) in leaves
            assert delivery["time"] - sent == leaves[(delivery["data"]["convoy"], sent)]
    one = reference_run("city_takeover_001", 42, 1.0)
    three = reference_run("city_takeover_001", 42, 3.0)

    def first(package):
        return min(
            e["time"] for e in package["event_memory"] if e["event_type"] == "SUPPLY"
        )

    assert first(three) > first(one)


def test_the_longer_supplies_take_the_worse_public_order():
    means = {}
    for delay in (1.0, 2.0, 3.0):
        orders = [
            end_order(reference_run("city_takeover_001", seed, delay), built())
            for seed in SEEDS
        ]
        means[delay] = sum(orders) / len(orders)
    assert means[1.0] > means[2.0] > means[3.0]
    assert means[1.0] - means[3.0] > 0.5


def test_without_a_delay_the_gap_is_not_there():
    a = [end_order(reference_run("city_takeover_001", s, 1.0), built()) for s in SEEDS]
    assert max(a) - min(a) < 0.1


# ── boundary values (Phase 12 lesson 2) ──────────────────────────────────────


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["districts"][0].update(population=0),
        lambda s: [d.update(food=0) for d in s["districts"]],
        lambda s: [sub.update(capacity=0) for sub in s["power"]["substations"]],
        lambda s: s["roads"].clear(),
        lambda s: s.update(depots=[]),
        lambda s: s["forces"].update(convoys=[], police=[], repair_crews=[]),
        lambda s: s["power"].update(plants=[]),
    ],
    ids=[
        "no_people",
        "no_food",
        "no_capacity",
        "no_roads",
        "no_depot",
        "no_forces",
        "no_plant",
    ],
)
def test_boundary_cities_run_to_the_end(change):
    edge = spec("city_blackout_001")
    change(edge)
    package = run(build_city_scenario(edge, RULES))
    assert package["evaluation_result"]["winner_or_result"] in (
        "order_restored",
        "order_held",
        "order_not_restored",
        "governance_collapsed",
    )
    CITY.governance_outcome(package, build_city_scenario(edge, RULES))


def test_food_consumption_scales_with_population():
    assert consumption(0, RULES) == 0
    assert consumption(50_000, RULES) == pytest.approx(0.4)


# ── what the world refuses ───────────────────────────────────────────────────

from skyvault.action import Action, ActionTarget  # noqa: E402
from skyvault.actions import ActionContext  # noqa: E402
from skyvault.domains.city.handlers import city_handlers  # noqa: E402
from skyvault.domains.city.policy import CityAdministrationPolicy  # noqa: E402
from skyvault.domains.city.score import population_order  # noqa: E402
from skyvault.runtime.world import create_world  # noqa: E402

HANDLERS = city_handlers()


def city_world():
    import random

    world = create_world(reference_scenarios()["city_blackout_001"])
    return world, ActionContext(rng=random.Random(1), system_id="test")


def order(world, actor, action_type, entity_id=None, location=None):
    return Action(
        action_id=world.ids.action(),
        actor_id=actor,
        action_type=action_type,
        target=ActionTarget(entity_id=entity_id, location=location),
    )


@pytest.mark.parametrize(
    "actor,action_type,entity_id,location,reason",
    [
        ("center", "travel", None, "market", "A district does not travel"),
        ("police_1", "travel", None, "moon", "needs a place in the city"),
        ("police_1", "travel", None, "center", "Already there"),
        ("convoy_1", "patrol", None, None, "Only police patrol"),
        ("police_1", "dispatch", "south", None, "Only convoys are dispatched"),
        ("convoy_1", "dispatch", "sub_south", None, "Dispatch needs a district"),
        ("police_1", "restore_power", "sub_center", None, "Only repair crews"),
        ("crew_1", "restore_power", "center", None, "needs a substation"),
        ("crew_1", "restore_power", "sub_works", None, "already online"),
        ("police_1", "administer", "south", None, "Only the city office"),
        ("city_office", "administer", "sub_works", None, "needs a district"),
        ("police_1", "arrive", "police_1", None, "Not arriving now"),
        ("plant_works", "district_update", "sub_works", None, "Not a district"),
    ],
)
def test_the_city_refuses_what_cannot_happen(
    actor, action_type, entity_id, location, reason
):
    world, context = city_world()
    verdict = HANDLERS[action_type].validate(
        world, order(world, actor, action_type, entity_id, location), context
    )
    assert not verdict.valid and reason in verdict.reason


def test_on_the_road_nobody_travels_or_patrols_and_a_crew_must_stand_there():
    world, context = city_world()
    world.get_entity("police_1").position = None
    for action_type, location in (("travel", "market"), ("patrol", None)):
        verdict = HANDLERS[action_type].validate(
            world, order(world, "police_1", action_type, location=location), context
        )
        assert not verdict.valid
    world.get_entity("sub_center").state["online"] = False
    verdict = HANDLERS["restore_power"].validate(
        world, order(world, "crew_1", "restore_power", "sub_center"), context
    )
    assert verdict.reason == "The crew is not at the substation"


def test_a_convoy_loads_only_at_home_from_a_depot_with_food():
    world, context = city_world()
    world.get_entity("convoy_1").position = "south"
    away = HANDLERS["dispatch"].validate(
        world, order(world, "convoy_1", "dispatch", "south"), context
    )
    assert away.reason == "A convoy loads only at its home depot"
    world.get_entity("convoy_1").position = "harbor"
    world.get_entity("depot_harbor").state["food"] = 0
    empty = HANDLERS["dispatch"].validate(
        world, order(world, "convoy_1", "dispatch", "south"), context
    )
    assert empty.reason == "The depot is empty"


def test_where_no_road_leads_nobody_goes():
    lonely = spec()
    lonely["roads"] = [r for r in lonely["roads"] if "works" not in r[:2]]
    import random

    world = create_world(build_city_scenario(lonely, RULES))
    context = ActionContext(rng=random.Random(1), system_id="test")
    travel = HANDLERS["travel"].validate(
        world, order(world, "police_1", "travel", location="works"), context
    )
    dispatch = HANDLERS["dispatch"].validate(
        world, order(world, "convoy_1", "dispatch", "works"), context
    )
    assert travel.reason == dispatch.reason == "No road leads there"


def test_the_policy_holds_when_there_is_nothing_left_to_do():
    from skyvault.actors.view import WorldView

    crowded = spec()
    places = [d["id"] for d in crowded["districts"]] + ["center"]
    crowded["forces"]["police"] = [
        {"id": f"police_{n}", "at": place} for n, place in enumerate(places, 1)
    ]
    world = create_world(build_city_scenario(crowded, RULES))
    view = WorldView(world)
    policy = CityAdministrationPolicy()
    assert policy.decide_action(view, view.get_entity("center")) is None
    # every district has another officer: the ninth holds where it stands
    held = policy.decide_action(view, view.get_entity("police_9"))
    assert (held.action_type, held.intent) == ("patrol", "hold_district")
    for district in [e for e in world.entities.values() if e.entity_type == "district"]:
        district.state["administration"] = 1.0
    assert policy.decide_action(view, view.get_entity("city_office")) is None


def test_a_convoy_with_nowhere_to_go_waits():
    from skyvault.actors.view import WorldView

    lonely = spec()
    lonely["roads"] = [r for r in lonely["roads"] if "harbor" not in r[:2]]
    world = create_world(build_city_scenario(lonely, RULES))
    view = WorldView(world)
    policy = CityAdministrationPolicy()
    # only the harbor district (where the depot stands) can be reached
    first = policy.decide_action(view, view.get_entity("convoy_1"))
    assert first.target.entity_id == "harbor"
    # and another convoy is already taking food there
    world.get_entity("convoy_2").state.update(leg="outbound", destination="harbor")
    assert policy.decide_action(view, view.get_entity("convoy_1")) is None


def test_population_order_and_the_score_with_nobody_living_there():
    assert population_order({"a": {"population": 0, "public_order": 50}}) == 0.0
    empty = spec()
    for district in empty["districts"]:
        district["population"] = 0
    scenario = build_city_scenario(empty, RULES)
    result = CITY.governance_outcome(run(scenario), scenario)
    assert result["components"]["order"] == 0 and result["components"]["services"] == 0


def test_the_city_says_what_it_is_asked_to_do():
    goal = CITY.mission_goal(built(), "CITY")
    assert goal["type"] == "restore_order"


def test_a_convoy_away_from_home_heads_back_first():
    from skyvault.actors.view import WorldView

    world, _ = city_world()
    world.get_entity("convoy_1").position = "south"
    view = WorldView(world)
    back = CityAdministrationPolicy().decide_action(view, view.get_entity("convoy_1"))
    assert (back.action_type, back.target.location) == ("travel", "harbor")


def test_a_delivery_next_door_comes_back_and_loads_again():
    # the harbor district is where the depot stands: make it the hungriest
    hungry = spec()
    for district in hungry["districts"]:
        district["food"] = 20 if district["id"] != "harbor" else 0
    hungry["forces"]["convoys"] = hungry["forces"]["convoys"][:1]
    package = run(build_city_scenario(hungry, RULES))
    trips = [
        (e["time"], e["data"]["to"]) for e in events(package, "dispatch", "departure")
    ]
    deliveries = [
        (e["time"], e["target_entity_id"])
        for e in package["event_memory"]
        if e["event_type"] == "SUPPLY"
    ]
    assert trips[0] == (1, "harbor") and deliveries[0] == (2, "harbor")
    # back home the tick after and dispatched again: never stranded on the road
    assert trips[1] == (3, "harbor") and deliveries[1] == (4, "harbor")
