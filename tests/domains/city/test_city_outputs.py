"""Phase 14 step C: the governance score, the city's outputs, and every input kind."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skyvault.batch.aggregate import aggregate
from skyvault.batch.run import run_batch
from skyvault.domains.city.failures import city_failure_variables
from skyvault.domains.city.pack import CITY
from skyvault.domains.city.reference import reference_scenarios
from skyvault.domains.city.report import cascade, city_report
from skyvault.domains.city.score import COMPONENTS, governance_stability
from skyvault.engine import SkyVaultEngine
from skyvault.failure import build_failure_map, explore_failures
from skyvault.failure.variables import FAILURE_VARIABLES, apply_stress, variable_for
from skyvault.interface.api import run_submission
from skyvault.scenario_loader import default_evaluation_profile
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[3]


def scenario(name="city_takeover_001"):
    return copy.deepcopy(reference_scenarios()[name])


def run(s):
    return SkyVaultEngine(copy.deepcopy(s)).run()


TAKEOVER = scenario()
BLACKOUT = scenario("city_blackout_001")
TAKEOVER_RUN = run(TAKEOVER)
BLACKOUT_RUN = run(BLACKOUT)


# ── acceptance 4: the governance stability score ─────────────────────────────


def test_every_city_run_has_a_governance_stability_score():
    for package, s in ((TAKEOVER_RUN, TAKEOVER), (BLACKOUT_RUN, BLACKOUT)):
        result = CITY.governance_outcome(package, s)
        assert 0 <= result["score"] <= 1
        assert set(result["components"]) == set(COMPONENTS)
        assert len(result["series"]) == package["final_world_state"]["tick"] + 1
        assert set(result["districts"]) == {
            "center",
            "market",
            "harbor",
            "north",
            "east",
            "south",
            "west",
            "works",
        }


def test_the_score_is_the_weighted_mean_over_the_last_third():
    result = governance_stability(TAKEOVER_RUN, TAKEOVER)
    weights = TAKEOVER["world_contract"]["rule_set"]["city"]["score"]["weights"]
    for row in result["series"]:
        assert row["score"] == pytest.approx(
            sum(weights[c] * row[c] for c in COMPONENTS), abs=1e-4
        )
    assert result["window"] == [21, 30]  # ceil(30 × 0.33) = 10 ticks
    window = [r for r in result["series"] if 21 <= r["tick"] <= 30]
    assert result["score"] == pytest.approx(
        sum(r["score"] for r in window) / 10, abs=1e-4
    )


def test_order_component_is_the_population_weighted_order():
    result = governance_stability(TAKEOVER_RUN, TAKEOVER)
    final = TAKEOVER_RUN["final_world_state"]["entities"]
    districts = [u["state"] for u in final.values() if u["entity_type"] == "district"]
    people = sum(d["population"] for d in districts)
    weighted = sum(d["public_order"] * d["population"] for d in districts) / people
    assert result["series"][-1]["order"] == pytest.approx(weighted / 100, abs=1e-4)


def test_a_restored_city_scores_above_a_blacked_out_one_and_above_its_start():
    restored = governance_stability(TAKEOVER_RUN, TAKEOVER)
    dark = governance_stability(BLACKOUT_RUN, BLACKOUT)
    assert restored["score"] > restored["start"] > dark["score"]
    assert restored["components"]["order"] > dark["components"]["order"]


def test_rising_order_trends_above_one_half_and_falling_below():
    series = governance_stability(BLACKOUT_RUN, BLACKOUT)["series"]
    falling = [r for r in series if 6 <= r["tick"] <= 9]
    assert all(r["trend"] < 0.5 for r in falling)
    rising = governance_stability(TAKEOVER_RUN, TAKEOVER)["series"][5:10]
    assert all(r["trend"] > 0.5 for r in rising)


# ── the cascade and the report ───────────────────────────────────────────────


def test_the_cascade_is_a_chain_from_the_incident():
    chain = cascade(BLACKOUT_RUN)
    root, *trips = chain["outages"][:3]
    assert (root["substation"], root["cause"], root["depth"]) == (
        "sub_center",
        "incident",
        0,
    )
    assert {t["substation"] for t in trips} == {"sub_north", "sub_south"}
    assert all(
        t["depth"] == 1 and t["caused_by_event"] == [root["event_id"]] for t in trips
    )
    assert chain["cascade_depth"] == 1
    assert chain["most_dark"] == 7
    assert chain["dark_districts"]["5"] == [
        "center",
        "east",
        "harbor",
        "market",
        "north",
        "south",
        "west",
    ]
    assert [r["substation"] for r in chain["restored"]][0] == "sub_center"


def test_no_outage_means_no_cascade():
    chain = cascade(TAKEOVER_RUN)
    assert chain == {
        "outages": [],
        "cascade_depth": 0,
        "dark_districts": {},
        "most_dark": 0,
        "restored": [],
    }


def test_the_report_says_what_happened_in_words():
    summary = {
        "scenarios": {
            "city_blackout_001": {
                "outcome": "order_not_restored",
                "verdict": "fail",
                "governance": governance_stability(BLACKOUT_RUN, BLACKOUT),
                "cascade": cascade(BLACKOUT_RUN),
            }
        },
        "supply_delay": {
            "scenario": "city_takeover_001",
            "seeds": [42, 43],
            "rows": [
                {
                    "delay_factor": 1.0,
                    "restored_rate": 1.0,
                    "mean_end_order": 96.0,
                    "mean_score": 0.83,
                }
            ],
        },
    }
    text = city_report(summary)
    assert "- Outcome: order_not_restored (verdict fail)" in text
    assert "- Tick 4: sub_center down (incident)" in text
    assert "- Tick 5: sub_north down (overload 13.5 > 11.0, after event_" in text
    assert "| 1 | 100% | 96.0 | 0.83 |" in text


def test_run_city_writes_the_scores_cascades_study_and_report(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "dev" / "run_city.py"),
            "--output",
            str(tmp_path),
            "--seeds",
            "2",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "city_blackout_001: order_not_restored" in done.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "cascade_city_blackout_001.json",
        "cascade_city_takeover_001.json",
        "city_report.md",
        "governance_city_blackout_001.json",
        "governance_city_takeover_001.json",
        "supply_delay.json",
    ]
    study = json.loads((tmp_path / "supply_delay.json").read_text())
    assert [r["delay_factor"] for r in study["rows"]] == [1.0, 1.5, 2.0, 2.5, 3.0]
    orders = [r["mean_end_order"] for r in study["rows"]]
    assert orders[0] > orders[-1]


# ── failure variables in city terms ──────────────────────────────────────────


def test_a_city_reads_three_variables_in_its_own_terms():
    assert (
        variable_for(TAKEOVER, "supply_delay") is not FAILURE_VARIABLES["supply_delay"]
    )
    assert (
        variable_for(TAKEOVER, "communication_failure")
        is FAILURE_VARIABLES["communication_failure"]
    )
    reference = {"world_contract": {}, "entities": []}
    assert variable_for(reference, "supply_delay") is FAILURE_VARIABLES["supply_delay"]


def test_city_supply_delay_slows_the_convoys_and_pressure_lowers_order():
    late = apply_stress(TAKEOVER, {"supply_delay": "severe"}, "CITY")
    assert late["world_contract"]["rule_set"]["city"]["supply"]["delay_factor"] == 2.0
    pressed = apply_stress(TAKEOVER, {"civilian_pressure": "collapse"}, "CITY")
    north = next(e for e in pressed["entities"] if e["entity_id"] == "north")
    assert north["state"]["public_order"] == 18.0  # 45 × 0.4
    assert north["state"]["order_state"] == "riot"
    short = apply_stress(TAKEOVER, {"resource_shortage": "collapse"}, "CITY")
    depot = next(e for e in short["entities"] if e["entity_type"] == "depot")
    assert depot["state"]["food"] == 0


def test_a_city_without_convoys_cannot_be_delayed():
    bare = copy.deepcopy(TAKEOVER)
    bare["entities"] = [e for e in bare["entities"] if e["entity_type"] != "convoy"]
    applicable, reason = city_failure_variables()["supply_delay"].applies(bare, "CITY")
    assert (applicable, reason) == (False, "the city has no convoys")


def test_failure_exploration_finds_where_the_city_breaks():
    profile = default_evaluation_profile(TAKEOVER)
    config = copy.deepcopy(TAKEOVER["failure_exploration"])
    config["run_policy"]["repeat_count"] = 3
    config["failure_variables"] = ["supply_delay", "resource_shortage"]
    failure_map = build_failure_map(explore_failures(TAKEOVER, profile, config))
    assert failure_map["baseline"]["survival_rate"] == 1.0
    by_name = {v["variable"]: v for v in failure_map["variables"]}
    assert by_name["supply_delay"]["breaking_level"] == "severe"
    assert by_name["resource_shortage"]["breaking_level"] == "severe"


# ── batch and the world service ──────────────────────────────────────────────


def test_a_city_batch_counts_restored_order_as_a_win():
    spec = json.loads((ROOT / "data/batches/city_supply_delay.json").read_text())
    spec["run_policy"]["repeat_count"] = 2
    spec["sweeps"][0]["values"] = [1.0, 3.0]
    result = run_batch(spec)["batch_result"]
    rates = {v["variant_id"].rsplit("=", 1)[1]: v for v in result["variants"]}
    assert rates["1.0"]["win_rate"] == 1.0 and rates["1.0"]["loss_rate"] == 0.0
    assert rates["3.0"]["win_rate"] == 0.0 and rates["3.0"]["loss_rate"] == 1.0
    assert rates["3.0"]["draw_rate"] == 0.0


def test_aggregate_without_success_outcomes_keeps_survival_wins():
    records = [
        {
            "variant_id": "v",
            "kind": "version",
            "scenario_version": "v0.1",
            "seed": 1,
            "outcome": outcome,
            "status": "pass",
            "score": 0.5,
            "hp_lost": 0,
            "risk_events": 0,
            "event_count": 1,
            "output_hash": "x",
        }
        for outcome in ("RED_survived", "BLUE_survived", "order_restored")
    ]
    (plain,) = aggregate(records, "RED")
    assert (plain["win_rate"], plain["loss_rate"]) == (0.3333, 0.3333)
    (city,) = aggregate(records, "CITY", ["order_restored"])
    assert (city["win_rate"], city["loss_rate"], city["draw_rate"]) == (
        0.3333,
        0.6667,
        0.0,
    )


def test_nexus_gets_the_city_s_governance_outcome_through_the_world_service():
    returned = run_submission(
        {
            "system": "NEXUS",
            "kind": "task",
            "scenario": "city_blackout_001/v0.1",
            "content": {},
        },
        SQLiteStore(),
        load_governance(),
    )["returned"]
    assert returned["result_package"]["evaluation_result"]["winner_or_result"] == (
        "order_not_restored"
    )
    governance = returned["domain_outcome"]["governance_outcome"]
    assert governance == governance_stability(BLACKOUT_RUN, BLACKOUT)
    assert "governance_collapsed' is not evaluated" not in returned["briefing"]


def test_the_collapse_threshold_is_evaluated_reached_or_not():
    evaluation = TAKEOVER_RUN["evaluation_result"]
    assert not any(
        "governance_collapsed" in t for t in evaluation["recommended_next_tests"]
    )
    collapsed = scenario()
    for district in collapsed["entities"]:
        if district["entity_type"] == "district":
            district["state"].update(public_order=0.0, order_state="riot", food=0.0)
    package = run(collapsed)
    verdict = package["evaluation_result"]
    assert (
        verdict["termination_reason"]
        == "termination_condition_met:governance_collapsed"
    )
    assert verdict["winner_or_result"] == "governance_collapsed"
    assert verdict["overall_judgement"]["status"] == "fail"
    assert package["final_world_state"]["tick"] == 1
