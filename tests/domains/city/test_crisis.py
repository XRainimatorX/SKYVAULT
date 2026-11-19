"""Phase 22: city uses — crisis (Formal Spec 2.3), reconstruction, takeover branches."""

import copy
import json
from functools import cache
from pathlib import Path

import pytest

from skyvault.domains.city.disasters import active, closed_roads, damage, flooded_dark
from skyvault.domains.city.reference import load_rules, reference_scenarios
from skyvault.domains.city.scenario import build_city_scenario
from skyvault.domains.city.score import recovery_outcome
from skyvault.engine import SkyVaultEngine
from skyvault.interface.api import run_submission
from skyvault.interface.systems import domain_outcome
from skyvault.scenario_loader import load_scenario
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "data" / "domains" / "city" / "scenarios"
MISSION = ROOT / "data" / "missions" / "city_takeover_branches_001.json"
EDGES = [["a", "b", 1.0], ["b", "c", 2.0], ["a", "c", 5.0]]


def spec(name: str) -> dict:
    return json.loads((SPECS / f"{name}.json").read_text(encoding="utf-8"))


@cache
def crisis_run() -> tuple[dict, dict]:
    scenario = reference_scenarios()["urban_crisis_test_001"]
    return scenario, SkyVaultEngine(copy.deepcopy(scenario)).run()


@cache
def reconstruction_run() -> tuple[dict, dict]:
    scenario = reference_scenarios()["city_reconstruction_001"]
    return scenario, SkyVaultEngine(copy.deepcopy(scenario)).run()


def tagged(package: dict, tag: str) -> list[dict]:
    return [e for e in package["event_memory"] if tag in e["tags"]]


# ── disasters, as pure functions ─────────────────────────────────────────────


def test_a_disaster_lasts_from_its_tick_for_its_duration():
    flood = {"type": "flood", "tick": 3, "duration": 2, "district": "a"}
    assert [active(flood, t) for t in (2, 3, 4, 5)] == [False, True, True, False]
    assert active({"type": "fire", "tick": 1, "district": "a"}, 1)  # one step


def test_floods_cut_every_road_into_their_district_and_closures_one_road():
    rules = {
        "disasters": [
            {
                "type": "flood",
                "tick": 0,
                "duration": 2,
                "district": "a",
                "severity": 0.6,
            },
            {"type": "road_closure", "tick": 1, "duration": 1, "road": ["b", "c"]},
            {"type": "fire", "tick": 0, "duration": 5, "district": "c"},
        ]
    }
    assert closed_roads(rules, 0, EDGES) == {frozenset("ab"), frozenset("ac")}
    assert closed_roads(rules, 1, EDGES) == {
        frozenset("ab"),
        frozenset("ac"),
        frozenset("bc"),
    }
    assert closed_roads(rules, 2, EDGES) == set()
    rules["disasters"][2]["closes_roads"] = True
    assert frozenset("bc") in closed_roads(rules, 3, EDGES)


def test_a_flood_cuts_roads_from_road_cut_at_and_power_from_power_cut_at():
    shallow = {"type": "flood", "tick": 0, "duration": 1, "district": "a"}
    rules = {"disasters": [{**shallow, "severity": 0.59}]}
    # Phase 23: roads go at 60% inundation (calibration.json road_cut_at)
    assert closed_roads(rules, 0, EDGES) == set()
    assert flooded_dark(rules, 0) == {"a"}  # 97% of flooded sites lost power
    assert flooded_dark(rules, 1) == set()
    rules["disaster_effects"] = {"flood": {"road_cut_at": 0.5, "power_cut_at": 0.6}}
    assert closed_roads(rules, 0, EDGES) == {frozenset("ab"), frozenset("ac")}
    assert flooded_dark(rules, 0) == set()


def test_floods_and_fires_damage_what_they_say():
    state = {
        "food": 10.0,
        "medical": 0.8,
        "public_order": 50.0,
        "industry": 0.6,
        "administration": 0.4,
    }
    assert damage({"type": "flood", "severity": 0.5}, state) == {
        "food": 5.0,
        "medical": 0.6,
        "public_order": 45.0,
    }
    assert damage({"type": "fire", "severity": 0.5}, state) == {
        "industry": 0.3,
        "industry_capacity": 0.5,  # what burns has to be rebuilt
        "administration": 0.3,
        "medical": 0.6,
        "public_order": 47.5,
    }
    assert damage({"type": "road_closure", "road": ["a", "b"]}, state) == {}
    halved = {"disaster_effects": {"flood": {"food_loss": 0.5, "order_drop": 0.0}}}
    assert damage({"type": "flood", "severity": 0.5}, state, halved) == {
        "food": 7.5,
        "medical": 0.6,
        "public_order": 50.0,
    }


def test_the_builder_refuses_a_disaster_naming_nothing():
    for bad, problem in (
        ({"type": "quake", "tick": 1, "district": "center"}, "unknown disaster"),
        ({"type": "flood", "tick": 1, "district": "atlantis"}, "no district"),
        ({"type": "road_closure", "tick": 1, "road": ["north", "south"]}, "no road"),
    ):
        broken = spec("city_blackout_001")
        broken["disasters"] = [bad]
        with pytest.raises(ValueError, match=problem):
            build_city_scenario(broken, load_rules())


# ── urban_crisis_test_001: the world of Formal Spec 2.3 ──────────────────────


def test_the_crisis_world_is_the_world_section_2_3_describes():
    world = reference_scenarios()["urban_crisis_test_001"]["world_contract"]
    assert world["world_id"] == "urban_crisis_test_001"
    assert world["world_scope"] == "city_environment"
    assert world["purpose"] == [
        "crisis_response",
        "system_stress_test",
        "governance_recovery",
    ]
    assert world["space_model"]["type"] == "district_network"
    assert world["space_model"]["units"] == [
        "district",
        "road_node",
        "facility",
        "supply_point",
    ]
    assert world["time_model"] == {
        "type": "phase_event_hybrid",
        "phase_length": "6_hours",
        "max_duration": "14_days",
    }
    assert world["environment_state"] == {
        "power_grid": "unstable",
        "public_order": "low",
        "weather": "heavy_rain",
        "communication": "degraded",
    }
    assert world["actor_slots"] == [
        "NEXUS",
        "STARTX",
        "TAC_ANGEL",
        "EIDEN_01",
        "AEROGRID",
        "HADES",
    ]
    assert world["assumption_registry"]["supply_delay_model"] == ("regional_disruption")
    assert world["data_provenance"]["source_type"] == "mixed_input"
    assert world["failure_variables"] == [
        "supply_delay",
        "communication_failure",
        "public_order_collapse",
        "weather_degradation",
    ]
    assert world["evaluation_targets"][0] == "stability_recovery"


def test_the_crisis_runs_fourteen_days_in_six_hour_phases():
    scenario, package = crisis_run()
    assert scenario["runtime"]["max_ticks"] == 56
    assert package["final_world_state"]["tick"] == 14 * 24
    assert "phase_event_hybrid clock" in package["execution_protocol"][2]["detail"]
    times = sorted({e["time"] for e in package["event_memory"]})
    assert all(t % 6 == 0 for t in times)


def test_the_flood_fire_and_cut_road_land_in_their_phases():
    _, package = crisis_run()
    flood = tagged(package, "flood")
    fire = tagged(package, "fire")
    assert [(e["time"], e["target_entity_id"]) for e in flood] == [(12, "harbor")]
    assert [(e["time"], e["target_entity_id"]) for e in fire] == [(60, "works")]
    before = flood[0]["before_state"]["state"]["food"]
    assert flood[0]["after_state"]["state"]["food"] == round(before * 0.4, 4)
    cut = {
        (e["time"], e["target_entity_id"]): e["data"]["cut_off_from"]
        for e in tagged(package, "roads")
    }
    assert cut[(12, "harbor")] == ["market", "south", "works"]  # flooded: all roads
    assert "market" in cut[(24, "center")]  # the closed road from phase 4
    assert cut[(60, "harbor")] == []  # the flood is over after 8 phases


def test_rumor_spreads_in_the_crisis():
    _, package = crisis_run()
    assert tagged(package, "rumor") and tagged(package, "inform")


def test_a_military_world_on_a_phase_clock_is_refused():
    scenario = load_scenario(
        ROOT / "data" / "scenarios" / "military_squad_001" / "v0.1.json"
    )
    scenario["world_contract"]["time_model"] = {"type": "phase", "phase_length": 6}
    with pytest.raises(ValueError, match="tick clock, got 'grid' space"):
        SkyVaultEngine(scenario)


# ── reconstruction ───────────────────────────────────────────────────────────


def test_reconstruction_measures_how_fast_the_city_comes_back():
    scenario, package = reconstruction_run()
    found = recovery_outcome(package, scenario)
    assert set(found["measures"]) == {
        "industry",
        "administration",
        "medical",
        "power",
        "logistics",
    }
    power = found["measures"]["power"]
    # the southern substation is wrecked at step 1: power falls, then returns
    assert power["start"] == 1.0 and power["lowest"] < 1.0
    assert (
        power["recovered_at"] is not None and power["recovered_at"] > power["lowest_at"]
    )
    assert sorted(found["recovered"] + found["not_recovered"]) == sorted(
        found["measures"]
    )


def test_nexus_gets_the_recovery_with_the_governance_score():
    scenario, package = reconstruction_run()
    judged = domain_outcome(package, scenario)
    assert judged["recovery_outcome"] == recovery_outcome(package, scenario)
    assert "governance_outcome" in judged


# ── takeover branches: 強攻 / 封鎖 / 談判 / 先恢復供應 ─────────────────────────


@cache
def branches() -> dict:
    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    mission["repeat_count"] = 2
    return run_submission(
        {
            "system": "NEXUS",
            "kind": "task",
            "content": {"task_type": "mission", "mission": mission},
        },
        SQLiteStore(),
        load_governance(),
    )["returned"]


def test_the_four_takeover_branches_run_side_by_side():
    returned = branches()
    plans = {p["plan_id"]: p for p in returned["plans"]}
    assert set(plans) == {"assault", "blockade", "negotiate", "restore_supply_first"}
    assert set(returned["mission"]["scenarios"]) == set(plans)
    # sealing off the South Slums starves it: it fails where the others hold
    assert plans["blockade"]["risk"]["failure_frequency"] == 1.0
    for name in ("assault", "negotiate", "restore_supply_first"):
        assert plans[name]["risk"]["failure_frequency"] < 1.0
    assert returned["authority_handoff"]["reason"] == ["conflicting_branches"]
