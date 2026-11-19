"""Phase 22: the information environment CYBERHOUND describes (Formal Spec 5.2, 9.2)."""

import copy
from functools import cache

import pytest

from skyvault.domains.city.information import (
    DEFAULTS,
    active_sources,
    backlash,
    information_rules,
    opinion_state,
    order_pull,
    pressure_of,
    pressure_step,
)
from skyvault.domains.city.reference import reference_scenarios
from skyvault.engine import SkyVaultEngine


def city(info: dict | None = None, name: str = "city_blackout_001") -> dict:
    scenario = copy.deepcopy(reference_scenarios()[name])
    if info is not None:
        scenario["world_contract"]["rule_set"]["city"]["information"] = info
    return scenario


@cache
def run_of(key: str) -> dict:
    infos = {
        "off": None,
        "on": {},
        "rumor": {
            "sources": [{"district": "market", "tick": 2, "until": 8, "magnitude": 15}]
        },
        "touchy": {"backlash_threshold": 1.0, "initial": {"center": 40.0}},
    }
    return SkyVaultEngine(city(infos[key])).run()


def tagged(package: dict, tag: str) -> list[dict]:
    return [e for e in package["event_memory"] if tag in e["tags"]]


# ── the model, as pure functions ─────────────────────────────────────────────


def test_the_model_is_off_unless_the_rules_carry_it():
    assert information_rules({"order": {}}) is None
    assert information_rules({"information": {"spread": 0.5}})["spread"] == 0.5
    assert information_rules({"information": {}})["decay"] == DEFAULTS["decay"]


@pytest.mark.parametrize(
    "pressure, state",
    [
        (0, "calm"),
        (24.9, "calm"),
        (25, "uneasy"),
        (50, "agitated"),
        (75, "inflamed"),
        (100, "inflamed"),
    ],
)
def test_opinion_bands(pressure, state):
    assert opinion_state(pressure) == state


def test_pressure_comes_from_state_then_initial_then_zero():
    info = information_rules({"information": {"initial": {"a": 30}}})
    assert pressure_of({"emotional_pressure": 12}, info, "a") == 12
    assert pressure_of({}, info, "a") == 30
    assert pressure_of({}, info, "b") == 0


def test_sources_are_active_from_tick_until():
    info = information_rules(
        {
            "information": {
                "sources": [{"district": "a", "tick": 2, "until": 4, "magnitude": 5}]
            }
        }
    )
    assert active_sources(info, 1) == {}
    assert active_sources(info, 2) == active_sources(info, 4) == {"a": 5.0}
    assert active_sources(info, 5) == {}


def test_one_tick_spreads_from_more_pressure_to_less_along_roads():
    info = information_rules({"information": {"spread": 0.5, "decay": 0.0}})
    districts = {
        "a": {
            "pressure": 60.0,
            "short": False,
            "powered": True,
            "order_state": "stable",
            "communication": 1.0,
        },
        "b": {
            "pressure": 20.0,
            "short": True,
            "powered": False,
            "order_state": "riot",
            "communication": 0.5,
        },
        "c": {
            "pressure": 0.0,
            "short": False,
            "powered": True,
            "order_state": "stable",
            "communication": 1.0,
        },
    }
    step = pressure_step(
        districts, {"a": ["b"], "b": ["a", "c"], "c": ["b"]}, {"c": 3.0}, info
    )
    # b hears a: 0.5 × a's communication 1.0 × (60 - 20) = 20
    assert step["b"]["spread_from"] == [{"from": "a", "amount": 20.0}]
    parts = step["b"]["parts"]
    assert (
        parts["shortage"] == DEFAULTS["shortage"] and parts["dark"] == DEFAULTS["dark"]
    )
    assert parts["unrest"] == 2 * DEFAULTS["unrest"]  # riot counts twice
    assert step["b"]["after"] == pytest.approx(20 + parts["total"])
    # a hears nobody louder; c hears b through b's poor communication (0.5)
    assert step["a"]["spread_from"] == []
    assert step["c"]["spread_from"] == [{"from": "b", "amount": 5.0}]  # 0.5 × 0.5 × 20
    assert step["c"]["parts"]["rumor"] == 3.0
    # all move from the same before-state: c hears b at 20, not b's new value
    assert step["c"]["before"] == 0.0


def test_pressure_stays_within_0_and_100():
    info = information_rules({"information": {"decay": 0.0}})
    loud = {
        "pressure": 99.0,
        "short": True,
        "powered": False,
        "order_state": "riot",
        "communication": 1.0,
    }
    assert pressure_step({"a": loud}, {}, {"a": 50.0}, info)["a"]["after"] == 100.0
    quiet = {
        **loud,
        "pressure": 0.0,
        "short": False,
        "powered": True,
        "order_state": "stable",
    }
    assert (
        pressure_step({"a": quiet}, {}, {}, information_rules({"information": {}}))[
            "a"
        ]["after"]
        == 0.0
    )


def test_pressure_pulls_order_down_and_backlash_has_a_threshold():
    info = information_rules(
        {"information": {"order_weight": 3.0, "backlash_threshold": 60}}
    )
    assert order_pull(50, info) == -1.5
    assert order_pull(0, info) == 0
    assert backlash(60, info) and not backlash(59.9, info)


# ── in a running city ────────────────────────────────────────────────────────


def test_a_city_without_the_model_runs_as_before():
    package = run_of("off")
    assert not tagged(package, "information")
    for unit in package["final_world_state"]["entities"].values():
        assert "emotional_pressure" not in unit["state"]


def test_the_model_records_each_district_s_pressure_and_spread_path():
    package = run_of("rumor")
    moves = [e for e in tagged(package, "information") if "pressure_parts" in e["data"]]
    assert moves
    first = moves[0]
    assert set(first["data"]["pressure_parts"]) >= {
        "shortage",
        "dark",
        "rumor",
        "spread",
        "decay",
        "total",
    }
    assert {e["target_entity_id"] for e in tagged(package, "rumor")} == {"market"}
    spread = [e for e in moves if e["data"]["spread_from"]]
    assert spread
    for event in spread:
        assert {row["from"] for row in event["data"]["spread_from"]} <= set(
            event["affected"]["entities"]
        )
    updates = tagged(package, "district_update")
    assert all("emotional" in e["data"]["order_parts"] for e in updates)


def test_pressure_costs_the_city_public_order():
    def order(package: dict) -> float:
        districts = [
            u["state"]["public_order"]
            for u in package["final_world_state"]["entities"].values()
            if u["entity_type"] == "district"
        ]
        return sum(districts) / len(districts)

    assert order(run_of("rumor")) < order(run_of("off"))


def test_the_city_office_answers_with_counter_messaging():
    informs = tagged(run_of("rumor"), "inform")
    assert informs
    for event in informs:
        assert event["data"]["pressure"] < event["data"]["pressure_before"]


def test_a_patrol_in_a_district_past_the_threshold_backfires():
    backfired = tagged(run_of("touchy"), "backlash")
    assert backfired
    for event in backfired:
        data = event["data"]["backlash"]
        assert data["pressure"] > data["pressure_before"]


def test_inform_and_information_update_need_the_model():
    package = SkyVaultEngine(
        {
            **city(),
            "runtime": {
                **city()["runtime"],
                "scheduled_actions": [
                    {
                        "tick": 1,
                        "actor_id": next(
                            e["entity_id"]
                            for e in city()["entities"]
                            if e["entity_type"] == "city_office"
                        ),
                        "action_type": "inform",
                        "target": {"entity_id": "market"},
                        "system_id": "test",
                    }
                ],
            },
        }
    ).run()
    refused = [
        e
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
        and e["data"].get("action_type") == "inform"
    ]
    assert (
        refused and refused[0]["data"]["reason"] == "This city has no information model"
    )
