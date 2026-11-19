"""Phase 23: which city coefficients change a conclusion."""

import copy
import json

from skyvault.domains.city.calibration import load_calibration
from skyvault.domains.city.reference import reference_scenarios
from skyvault.domains.city.sensitivity import (
    MISSION,
    SHIFT,
    criticality,
    flips,
    load_sensitivity,
    sweep,
    with_plan,
    with_rules,
)

CALIBRATION = load_calibration()
REPORT = load_sensitivity()


def test_rule_and_plan_changes_land_where_they_say():
    takeover = reference_scenarios()["city_takeover_001"]
    changed = with_rules(takeover, {"recovery": {"rebuild": 0.5}, "new": {"a": 1}})
    rules = changed["world_contract"]["rule_set"]["city"]
    assert rules["recovery"]["rebuild"] == 0.5
    assert rules["recovery"]["industry_up"] == 0.02  # the rest of the group stays
    assert rules["new"] == {"a": 1}
    assert (
        takeover["world_contract"]["rule_set"]["city"]["recovery"]["rebuild"] == 0.0002
    )
    plans = {p["plan_id"]: p for p in json.loads(MISSION.read_text())["plans"]}
    supplied = with_plan(takeover, plans["restore_supply_first"])
    units = {u["entity_id"]: u for u in supplied["entities"]}
    assert units["convoy_1"]["capabilities"]["capacity"] == 10
    assert units["depot_harbor"]["state"]["food"] == 200.0
    assert (
        supplied["world_contract"]["rule_set"]["city"]["supply"]["delay_factor"] == 0.75
    )


def test_a_flip_is_a_changed_verdict_or_best_plan_and_makes_it_high():
    base = {
        "scenarios": {"a": {"verdict": "order_restored", "governance": 0.7}},
        "best_plan": "negotiate",
    }
    same = copy.deepcopy(base)
    assert flips(base, same) == []
    moved = copy.deepcopy(base)
    moved["scenarios"]["a"]["verdict"] = "order_not_restored"
    moved["best_plan"] = "assault"
    assert flips(base, moved) == [
        "a: order_restored → order_not_restored",
        "best plan: negotiate → assault",
    ]
    assert criticality(["x"], 0.0) == "high"
    assert criticality([], SHIFT) == "medium"
    assert criticality([], SHIFT - 0.001) == "low"


def test_the_committed_report_covers_the_registry_and_sets_its_criticality():
    rows = {r["coefficient"]: r for r in REPORT["coefficients"]}
    entries = {c["coefficient"]: c for c in CALIBRATION["coefficients"]}
    assert REPORT["calibration_version"] == CALIBRATION["version"]
    assert list(rows) == list(entries)
    for name, entry in entries.items():
        row = rows[name]
        assert [row["ends"]["low"]["value"], row["ends"]["high"]["value"]] == entry[
            "range"
        ]
        assert row["confidence"] == entry["confidence"]
        assert entry["criticality"] == row["criticality"], name
    assert REPORT["data_first"] == [
        name
        for name, row in rows.items()
        if row["criticality"] == "high" and row["confidence"] == "assumed"
    ]


def test_the_committed_report_is_what_the_sweep_finds_now():
    # one coefficient again, on the report's seeds: a stale report fails here
    name = "repair.failure_ticks"
    found = sweep(
        reference_scenarios(), CALIBRATION, seeds=tuple(REPORT["seeds"]), only=[name]
    )
    assert found["baseline"] == REPORT["baseline"]
    row = next(r for r in REPORT["coefficients"] if r["coefficient"] == name)
    assert found["coefficients"] == [row]
