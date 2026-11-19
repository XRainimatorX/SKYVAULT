"""Phase 23: the city's coefficients, where they come from, and what they reproduce."""

import copy
from functools import cache

import pytest

from skyvault.domains.city.calibration import (
    CONFIDENCE,
    coefficient_assumptions,
    load_calibration,
    registry_problems,
    value_at,
    with_value,
)
from skyvault.domains.city.disasters import EFFECTS
from skyvault.domains.city.information import DEFAULTS, counter, information_rules
from skyvault.domains.city.model import night_share
from skyvault.domains.city.reference import load_rules, reference_scenarios
from skyvault.domains.city.scenario import build_city_scenario
from skyvault.engine import SkyVaultEngine

CALIBRATION = load_calibration()
RULES = load_rules()
ENTRIES = {c["coefficient"]: c for c in CALIBRATION["coefficients"]}


@cache
def run(name: str) -> tuple[dict, dict]:
    scenario = reference_scenarios()[name]
    return scenario, SkyVaultEngine(copy.deepcopy(scenario)).run()


def states_of(package: dict, entity_id: str) -> list[tuple[int, dict]]:
    """(time, state after) for every event that changed entity_id."""
    return [
        (int(e["time"]), e["after_state"]["state"])
        for e in package["event_memory"]
        if e["target_entity_id"] == entity_id and e.get("after_state")
    ]


# ── the registry and the rules agree ─────────────────────────────────────────


def test_the_registry_and_the_rules_agree_coefficient_by_coefficient():
    assert registry_problems(RULES, CALIBRATION) == []
    # the three models' groups and order.dark are covered, nothing else
    groups = {name.split(".")[0] for name in ENTRIES}
    assert groups == {
        "information_defaults",
        "disaster_effects",
        "recovery",
        "repair",
        "order",
    }


def test_a_rule_the_registry_does_not_match_or_does_not_list_is_a_problem():
    changed = copy.deepcopy(RULES)
    changed["recovery"]["rebuild"] = 0.02
    changed["recovery"]["new_rate"] = 0.1
    assert registry_problems(changed, CALIBRATION) == [
        "recovery.rebuild: rules hold 0.02, registry 0.0002",
        "recovery.new_rate: no registry entry",
    ]
    broken = copy.deepcopy(CALIBRATION)
    entry = broken["coefficients"][0]
    entry.update(value=99.0, confidence="guessed", sources=["nowhere"])
    del changed["recovery"]["new_rate"]
    changed["recovery"]["rebuild"] = 0.0002
    changed[entry["coefficient"].split(".")[0]][
        entry["coefficient"].split(".")[1]
    ] = 99.0
    assert registry_problems(changed, broken) == [
        f"{entry['coefficient']}: 99.0 outside {entry['range']}",
        f"{entry['coefficient']}: unknown confidence 'guessed'",
        f"{entry['coefficient']}: unknown source 'nowhere'",
    ]
    missing = copy.deepcopy(RULES)
    del missing["repair"]
    assert "repair.failure_ticks: not in the rules" in registry_problems(
        missing, CALIBRATION
    )


def test_the_code_fallbacks_are_the_rules_values():
    # rules written without information_defaults / disaster_effects run on these
    assert {k: DEFAULTS[k] for k in RULES["information_defaults"]} == RULES[
        "information_defaults"
    ]
    assert set(DEFAULTS) - set(RULES["information_defaults"]) == {"initial", "sources"}
    assert RULES["disaster_effects"] == EFFECTS
    # a scenario's own information rules still override the pack's
    rules = {**RULES, "information": {"counter_share": 0.3}}
    assert information_rules(rules)["counter_share"] == 0.3
    assert information_rules(RULES) is None


def test_every_value_says_how_sure_it_is_and_why():
    for name, entry in ENTRIES.items():
        assert entry["unit"] and entry["method"] and entry["finding"], name
        if entry["confidence"] != "assumed":
            assert entry["sources"], f"{name} claims support but cites nothing"
    for source in CALIBRATION["sources"].values():
        assert source["url"].startswith("https://") and source["title"]
    # honest about how much is known
    counts = {
        level: sum(1 for e in ENTRIES.values() if e["confidence"] == level)
        for level in CONFIDENCE
    }
    assert counts == {"anchored": 1, "derived": 5, "assumed": 23}


def test_with_value_names_one_dotted_rule():
    change = with_value("disaster_effects.flood.road_cut_at", 0.3)
    assert change == {"disaster_effects": {"flood": {"road_cut_at": 0.3}}}
    assert value_at(RULES, "repair.failure_ticks") == 4


# ── the patterns the anchors describe ────────────────────────────────────────


def test_a_substation_takes_a_day_of_work_and_is_back_within_five_days():
    # Hazus: slight damage about 1 day; large storms: half wait up to 5 days
    steps = RULES["repair"]["failure_ticks"]
    assert steps * CALIBRATION["time"]["step_hours"] == 24
    scenario, package = run("urban_crisis_test_001")
    history = states_of(package, "sub_south")
    down = next(t for t, s in history if s.get("online") is False)
    back = next(t for t, s in history if t > down and s.get("online") is True)
    assert 24 <= back - down <= 5 * 24


def test_destroyed_capacity_comes_back_at_the_katrina_pace():
    # about 65% of businesses back 26 months after Katrina
    steps = 26 * 30.44 * 24 / CALIBRATION["time"]["step_hours"]
    assert RULES["recovery"]["rebuild"] * steps == pytest.approx(0.65, abs=0.02)
    scenario, package = run("city_reconstruction_001")
    final = package["final_world_state"]["entities"]
    start = {e["entity_id"]: e["state"] for e in scenario["entities"]}
    ticks = scenario["runtime"]["max_ticks"]
    for name, unit in final.items():
        if unit["entity_type"] != "district":
            continue
        state = unit["state"]
        assert state["industry"] <= state["industry_capacity"] + 1e-9
        rebuilt = state["industry_capacity"] - start[name]["industry_capacity"]
        assert rebuilt == pytest.approx(ticks * RULES["recovery"]["rebuild"], abs=1e-4)


def test_a_counter_message_removes_a_real_world_share_of_the_pressure():
    # corrections: r = .14 on real-world misinformation, .35 overall
    info = information_rules({**RULES, "information": {}})
    assert counter(50.0, info) == 43.0
    low, high = ENTRIES["information_defaults.counter_share"]["range"]
    assert counter(50.0, {"counter_share": high}) < counter(50.0, info)
    assert counter(0.0, info) == 0.0


def test_darkness_counts_by_the_night_share_of_a_step():
    assert [night_share(h, 6, 18, 6) for h in (0, 6, 12, 18)] == [1.0, 0.0, 0.0, 1.0]
    assert night_share(None, 0, 18, 6) == 0.5  # a tick clock has no time of day
    assert night_share(4, 4, 18, 6) == 0.5  # 04:00–08:00
    assert night_share(22, 4, 18, 6) == 1.0  # across midnight
    assert night_share(16, 4, 18, 6) == 0.5
    scenario, package = run("urban_crisis_test_001")
    dark = [
        (int(e["time"]), e["data"]["pressure_parts"]["dark"])
        for e in package["event_memory"]
        if "information" in e["tags"] and "pressure_parts" in e.get("data", {})
    ]
    assert any(part > 0 for _, part in dark)
    # six-hour phases from midnight: only 00–06 and 18–24 are night
    assert all(part == 0 for time, part in dark if time % 24 in (6, 12))


def test_a_flood_leaves_its_district_dark_while_it_lasts():
    # 97% of practices hit by the 2021 North Rhine flood lost power
    scenario, package = run("urban_crisis_test_001")
    flood = next(
        d
        for d in scenario["world_contract"]["rule_set"]["city"]["disasters"]
        if d["type"] == "flood"
    )
    hours = 6
    powered = states_of(package, flood["district"])
    dark_at = [t for t, s in powered if s.get("power") == 0]
    assert dark_at and min(dark_at) == flood["tick"] * hours


# ── every built city carries where its coefficients come from ───────────────


def test_every_city_scenario_carries_its_coefficients_as_assumptions():
    for name, scenario in reference_scenarios().items():
        registry = scenario["assumption_registry"]
        found = {
            a["assumption_id"]: a
            for a in registry["assumptions"]
            if a["category"] == "coefficient"
        }
        assert set(found) == {f"coefficient.{n}" for n in ENTRIES}, name
        for coefficient, entry in ENTRIES.items():
            got = found[f"coefficient.{coefficient}"]
            assert got["confidence"] == CONFIDENCE[entry["confidence"]]
            assert got["value"] == entry["value"]
        assert registry["critical_assumptions"] == [
            f"coefficient.{n}"
            for n, e in ENTRIES.items()
            if e.get("criticality") == "high"
        ]
        provenance = scenario["data_provenance"]
        cited = {s["source_id"] for s in provenance["sources"]}
        used = {s for e in ENTRIES.values() for s in e["sources"]}
        assert {f"calibration.{s}" for s in used} <= cited
        assert any("search abstracts" in n for n in provenance["reliability_notes"])
        flat = scenario["world_contract"]["assumption_registry"]["coefficients"]
        assert flat == "city calibration v0.1: 1 anchored, 5 derived, 23 assumed"


def test_a_city_on_other_rules_is_recorded_as_custom():
    spec = {
        "scenario_id": "custom_city",
        "scenario_version": "v0.1",
        "max_ticks": 2,
        "random_seed": 1,
        "districts": [
            {
                "id": "a",
                "population": 1000,
                "public_order": 70,
                "food": 5,
                "medical": 0.5,
                "industry": 0.5,
                "administration": 0.5,
            }
        ],
        "roads": [],
        "power": {"plants": [], "substations": []},
    }
    rules = copy.deepcopy(RULES)
    rules["order"]["dark"] = -6.0
    built = build_city_scenario(spec, rules)
    flat = built["world_contract"]["assumption_registry"]["coefficients"]
    assert flat == "custom: differs from the city calibration at 1 points"
    assert "assumption_registry" not in built  # no coefficients claimed
    assert coefficient_assumptions(CALIBRATION)[0]["category"] == "coefficient"
