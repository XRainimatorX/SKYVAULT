"""Phase 22: the observers Formal Spec 5.2 adds — EIDEN-01, CYBERHOUND, STAR GUARD."""

import copy
from functools import cache
from pathlib import Path

import pytest

from skyvault.domains.city.reference import reference_scenarios
from skyvault.engine import SkyVaultEngine
from skyvault.observation.history import observations_for_run
from skyvault.observation.profiles import load_observer_profile
from skyvault.scenario_loader import load_scenario
from skyvault.worldservice.jobs import NotFound, changed_rules, scenario_for

DATA = Path(__file__).resolve().parents[2] / "data" / "scenarios"


@cache
def military() -> tuple[dict, dict]:
    scenario = load_scenario(DATA / "military_urban_001" / "v0.2.json")
    scenario["data_provenance"] = {
        "scenario_id": scenario["scenario_id"],
        "sources": [
            {"source_id": "recon_7", "source_type": "EIDEN_01", "confidence": 0.6},
            {
                "source_id": "map_1",
                "source_type": "historical_record",
                "confidence": 0.9,
            },
        ],
        "missing_data": ["red reinforcements"],
    }
    return scenario, SkyVaultEngine(copy.deepcopy(scenario)).run()


@cache
def city(info: bool = True) -> tuple[dict, dict]:
    scenario = copy.deepcopy(reference_scenarios()["city_blackout_001"])
    if info:
        scenario["world_contract"]["rule_set"]["city"]["information"] = {
            "sources": [{"district": "market", "tick": 1, "until": 6, "magnitude": 20}]
        }
    return scenario, SkyVaultEngine(copy.deepcopy(scenario)).run()


def seen(observer: str, scenario: dict, package: dict, **viewpoint) -> list[dict]:
    return observations_for_run(
        package, scenario, load_observer_profile(observer), viewpoint
    )


def test_eiden_sees_sources_trust_assumptions_and_gaps():
    scenario, package = military()
    obs = seen("EIDEN_01", scenario, package, faction="BLUE")[6]
    summary = obs["visible_world_state"]["summary"]
    assert [s["source_id"] for s in summary["sources"]] == ["recon_7", "map_1"]
    assert summary["source_confidence"] == 0.75
    assert summary["assumptions"][0]["assumption_id"] == "actor_policy"
    assert summary["gaps"][0] == "red reinforcements"
    # the enemy as known: contacts only, never their state
    for known in obs["visible_world_state"]["known_entities"]:
        assert known["relation"] == "enemy" and known["state"] is None
    assert obs["uncertainty"]["delay_ticks"] == 1


def test_eiden_lists_enemies_out_of_sight_as_a_gap():
    scenario, package = military()
    first = seen("EIDEN_01", scenario, package, faction="BLUE")[0]
    gaps = first["visible_world_state"]["summary"]["gaps"]
    hidden = first["hidden_state"]["exists"]
    assert hidden == any(g.endswith("enemy unit(s) not in sight") for g in gaps)


def test_cyberhound_sees_pressure_spread_paths_and_cognitive_risk():
    scenario, package = city()
    obs = seen("CYBERHOUND", scenario, package, faction="CITY")[8]
    summary = obs["visible_world_state"]["summary"]
    assert summary["modelled"] is True
    districts = summary["districts"]
    assert districts["market"]["emotional_pressure"] > 0
    for path in summary["spread_paths"]:
        gap = (
            districts[path["from"]]["emotional_pressure"]
            - districts[path["to"]]["emotional_pressure"]
        )
        assert path["gap"] == pytest.approx(gap, abs=1e-3) and gap > 0
    assert summary["cognitive_risk"] == sorted(
        d for d, s in districts.items() if s["opinion_state"] == "inflamed"
    )
    for risk in obs["visible_world_state"]["known_risks"]:
        assert risk["risk"] in ("backlash", "inflamed")


def test_cyberhound_says_when_a_world_has_no_information_model():
    scenario, package = city(info=False)
    obs = seen("CYBERHOUND", scenario, package, faction="CITY")[3]
    assert obs["visible_world_state"]["summary"] == {"modelled": False}


def test_star_guard_sees_its_equipment_posture_energy_failures_and_value():
    scenario, package = military()
    obs = seen("STAR_GUARD", scenario, package, faction="BLUE", actor_id="blue_01")
    late = obs[-1]["visible_world_state"]
    summary = late["summary"]
    assert set(summary) == {
        "equipment",
        "posture",
        "energy",
        "failures",
        "maintenance_pressure",
        "mission_value",
    }
    assert late["known_entities"][0]["entity_id"] == "blue_01"
    assert 0 <= summary["failures"]["hp_lost_ratio"] <= 1
    assert summary["maintenance_pressure"] is None  # no endurance on this unit


def test_star_guard_counts_down_endurance_when_the_unit_has_it():
    scenario, _ = military()
    scenario = copy.deepcopy(scenario)
    unit = next(e for e in scenario["entities"] if e["entity_id"] == "blue_01")
    unit["capabilities"]["endurance_ticks"] = 4
    package = SkyVaultEngine(scenario).run()
    obs = seen("STAR_GUARD", scenario, package, faction="BLUE", actor_id="blue_01")
    assert (
        obs[2]["visible_world_state"]["summary"]["energy"]["endurance_ticks_left"] == 2
    )
    assert obs[2]["visible_world_state"]["summary"]["maintenance_pressure"] == 0.5
    assert obs[5]["visible_world_state"]["known_risks"] == [
        {"risk": "endurance_exhausted"}
    ]


def test_star_guard_needs_the_equipment_it_watches():
    scenario, package = military()
    with pytest.raises(ValueError, match="actor_id"):
        seen("STAR_GUARD", scenario, package, faction="BLUE")


# ── what a job may change: rules and stress ──────────────────────────────────


def test_rule_changes_merge_into_groups_the_world_has():
    scenario, _ = city(info=False)
    changed = changed_rules(
        scenario, {"city": {"information": {"spread": 0.4}, "order": {"noise": 0.0}}}
    )
    rules = changed["world_contract"]["rule_set"]["city"]
    assert rules["information"] == {"spread": 0.4}
    assert rules["order"]["noise"] == 0.0
    assert rules["order"]["stable"] == (
        scenario["world_contract"]["rule_set"]["city"]["order"]["stable"]
    )
    assert "information" not in scenario["world_contract"]["rule_set"]["city"]
    with pytest.raises(NotFound, match="no rule groups"):
        changed_rules(scenario, {"tactical": {}})


def test_a_job_s_stress_applies_failure_variables_as_a_new_version():
    stressed = scenario_for(
        {
            "scenario": "military_urban_001/v0.2",
            "stress": {"communication_failure": "severe"},
        }
    )
    assert stressed["scenario_version"] == "v0.2+communication_failure:severe"
