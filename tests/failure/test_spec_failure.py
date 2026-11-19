"""Phase 22: failure exploration as Formal Spec 14.2 – 14.4 asks."""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_analysis import exploration, runs, sweep  # noqa: E402

from skyvault.contracts import FAILURE_VARIABLE_NAMES, validate_failure_map
from skyvault.domains import load_domain
from skyvault.domains.city.reference import reference_scenarios
from skyvault.engine import SkyVaultEngine
from skyvault.evaluation.anti_gaming import BEHAVIORS
from skyvault.failure import FAILURE_TAXONOMY, variables_for
from skyvault.failure.analysis import RECOMMENDATIONS, build_failure_map
from skyvault.failure.variables import FAILURE_VARIABLES, apply_stress, variable_for
from skyvault.scenario_loader import load_scenario
from skyvault.virtualtest.physics import CHECKS

DATA = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def military() -> dict:
    return load_scenario(DATA / "military_urban_001" / "v0.2.json")


def airspace() -> dict:
    return load_scenario(DATA / "airspace_defence_001" / "v0.1.json")


def city() -> dict:
    return copy.deepcopy(reference_scenarios()["city_blackout_001"])


def stressed(scenario: dict, name: str, level: str, perspective: str) -> dict:
    return apply_stress(scenario, {name: level}, perspective)


# ── 14.2: every row maps to something SKYVAULT has ───────────────────────────


def test_every_row_of_section_14_2_is_tested_by_something():
    rows = {label["label"]: label["failures"] for label in FAILURE_TAXONOMY.values()}
    assert set(rows) == {
        "戰術方案",
        "城市接管",
        "裝備方案",
        "HADES / AEROGRID",
        "SKYFOX",
        "STARTX 方案",
        "TAC ANGEL 行動",
    }
    assert set(rows["戰術方案"]) == {"被包圍", "補給斷", "情報錯", "隊形崩"}
    assert set(rows["SKYFOX"]) == {"失聯", "撞機", "能源耗盡", "路徑阻塞"}
    for ways in rows.values():
        for way, tested in ways.items():
            assert tested.get("variables") or tested.get("checks"), way


def test_every_variable_the_table_names_exists_and_has_a_recommendation():
    named = {name for plan in FAILURE_TAXONOMY for name in variables_for(plan)}
    assert named <= set(FAILURE_VARIABLES) <= set(FAILURE_VARIABLE_NAMES)
    assert set(FAILURE_VARIABLE_NAMES) <= set(RECOMMENDATIONS)
    airspace_names = set(load_domain("airspace").failure_variables())
    assert {
        "misidentification",
        "reaction_delay",
        "target_saturation",
        "collision",
        "path_blocked",
    } <= airspace_names


def test_every_check_the_table_names_is_one_skyvault_runs():
    for plan in FAILURE_TAXONOMY.values():
        for tested in plan["failures"].values():
            for check in tested.get("checks", []):
                kind, *rest = check.split(".")
                if kind == "virtual_test" and rest[0] == "physical":
                    assert rest[1] in CHECKS
                elif kind == "virtual_test":
                    assert rest == ["engineering", "maintenance"]
                else:
                    assert kind == "anti_gaming" and rest[0] in BEHAVIORS.values()


# ── the new variables do what they say ───────────────────────────────────────


def test_encirclement_puts_part_of_the_enemy_behind_the_side():
    base = military()
    for level, share in (("mild", 0.25), ("collapse", 1.0)):
        after = stressed(base, "encirclement", level, "RED")
        blue_before = {
            e["entity_id"]: e["position"]
            for e in base["entities"]
            if e["faction"] == "BLUE"
        }
        moved = [
            e
            for e in after["entities"]
            if e["faction"] == "BLUE" and e["position"] != blue_before[e["entity_id"]]
        ]
        assert len(moved) == max(1, round(5 * share))
        # RED holds row 0 facing BLUE further down: the enemy now starts
        # on RED's side of the map, nearer RED than it was
        red = [e["position"] for e in base["entities"] if e["faction"] == "RED"]
        for unit in moved:
            before = blue_before[unit["entity_id"]]
            assert unit["position"][1] < before[1] and unit["position"][1] <= 2
            assert min(
                abs(unit["position"][0] - x) + abs(unit["position"][1] - y)
                for x, y in red
            ) < min(abs(before[0] - x) + abs(before[1] - y) for x, y in red)
        cells = [tuple(e["position"]) for e in after["entities"] if e.get("position")]
        assert len(cells) == len(set(cells))


def test_intelligence_error_makes_the_enemy_stronger_than_reported():
    base = military()
    after = stressed(base, "intelligence_error", "severe", "RED")
    for before, now in zip(base["entities"], after["entities"], strict=True):
        if before["faction"] == "BLUE":
            assert now["state"]["hp"] == round(before["state"]["hp"] * 1.6)
        else:
            assert now["state"]["hp"] == before["state"]["hp"]


def test_formation_collapse_lowers_own_morale():
    after = stressed(military(), "formation_collapse", "moderate", "RED")
    red = [e for e in after["entities"] if e["faction"] == "RED"]
    assert {e["state"]["morale"] for e in red} == {48.0}


def test_tempo_delay_holds_own_units_for_the_first_ticks():
    after = stressed(military(), "tempo_delay", "moderate", "RED")
    waits = [
        o for o in after["runtime"]["scheduled_actions"] if o["intent"] == "tempo_delay"
    ]
    assert {o["tick"] for o in waits} == {1, 2}
    assert len(waits) == 10 * 2
    package = SkyVaultEngine(after).run()
    held = [
        e
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_SELECTED"
        and e["data"].get("intent") == "tempo_delay"
    ]
    assert len(held) == 20
    assert variable_for(city(), "tempo_delay").applies(city(), "CITY")[0] is False


def test_administration_collapse_empties_every_administration():
    after = stressed(city(), "administration_collapse", "collapse", "CITY")
    districts = [e for e in after["entities"] if e["entity_type"] == "district"]
    assert districts and {e["state"]["administration"] for e in districts} == {0.0}


def test_public_sentiment_decline_turns_on_the_information_model():
    after = stressed(city(), "public_sentiment_decline", "severe", "CITY")
    info = after["world_contract"]["rule_set"]["city"]["information"]
    districts = {
        e["entity_id"] for e in after["entities"] if e["entity_type"] == "district"
    }
    assert info["initial"] == {d: 55.0 for d in districts}
    package = SkyVaultEngine(after).run()
    assert any("information" in e["tags"] for e in package["event_memory"])
    assert (
        variable_for(military(), "public_sentiment_decline").applies(military(), "RED")[
            0
        ]
        is False
    )


def test_endurance_and_energy_shortfalls_need_what_they_shorten():
    base = military()
    assert variable_for(base, "endurance_shortfall").applies(base, "RED")[0] is False
    unit = next(e for e in base["entities"] if e["entity_id"] == "red_01")
    unit["capabilities"]["endurance_ticks"] = 20
    unit["state"]["energy"] = 100.0
    after = stressed(base, "endurance_shortfall", "moderate", "RED")
    assert (
        next(e for e in after["entities"] if e["entity_id"] == "red_01")[
            "capabilities"
        ]["endurance_ticks"]
        == 10
    )
    after = stressed(base, "energy_depletion", "collapse", "RED")
    assert (
        next(e for e in after["entities"] if e["entity_id"] == "red_01")["state"][
            "energy"
        ]
        == 10.0
    )


def test_airspace_reads_misidentification_and_reaction_delay_on_its_command():
    base = airspace()
    command = base["world_contract"]["rule_set"]["airspace"]["command"]
    after = stressed(base, "misidentification", "severe", "DEFENCE")
    assert after["world_contract"]["rule_set"]["airspace"]["command"]["identify"] == (
        round(command["identify"] * 0.6, 4)
    )
    after = stressed(base, "reaction_delay", "collapse", "DEFENCE")
    assert (
        after["world_contract"]["rule_set"]["airspace"]["command"]["reaction_delay"]
        == command["reaction_delay"] + 5
    )


def test_target_saturation_adds_threats_launched_a_tick_later():
    base = airspace()
    threats = [e for e in base["entities"] if e["entity_type"] == "threat"]
    after = stressed(base, "target_saturation", "severe", "DEFENCE")
    added = [e for e in after["entities"] if e["entity_id"].endswith("_s1")]
    assert len(added) == len(threats)
    original = {t["entity_id"]: t for t in threats}
    for twin in added:
        source = original[twin["entity_id"].removesuffix("_s1")]
        assert twin["state"]["launch_tick"] == source["state"]["launch_tick"] + 1
    assert SkyVaultEngine(after).run()["evaluation_result"]


def test_collision_sends_threats_to_the_drones_altitude():
    after = stressed(airspace(), "collision", "collapse", "DEFENCE")
    altitudes = {
        e["state"]["altitude"]
        for e in after["entities"]
        if e["entity_type"] == "threat"
    }
    assert altitudes == {"medium"}


def test_a_blocked_route_closes_waypoints_and_moves_there_are_refused():
    after = stressed(airspace(), "path_blocked", "collapse", "DEFENCE")
    closed = after["world_contract"]["rule_set"]["airspace"]["no_fly"]
    assert closed == [[14, 6], [14, 14], [6, 14]]
    after["runtime"]["scheduled_actions"] = [
        {
            "tick": 1,
            "actor_id": "skyfox_1",
            "action_type": "move",
            "target": {"location": [7, 6]},
            "system_id": "test",
        },
    ]
    after["entities"] = [
        e if e["entity_id"] != "skyfox_1" else {**e, "position": [13, 6]}
        for e in after["entities"]
    ]
    after["runtime"]["scheduled_actions"][0]["target"]["location"] = [14, 6]
    package = SkyVaultEngine(after).run()
    refused = [
        e["data"]["reason"]
        for e in package["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
        and e["source"]["actor_id"] == "skyfox_1"
    ]
    assert "Move target is closed to flight" in refused


def test_airspace_only_variables_say_so_elsewhere():
    for name in (
        "misidentification",
        "reaction_delay",
        "target_saturation",
        "collision",
        "path_blocked",
    ):
        applies, reason = variable_for(military(), name).applies(military(), "RED")
        assert applies is False and "airspace" in reason


# ── 14.3 output and the seven answers of 14.4 ────────────────────────────────


def test_the_map_carries_the_14_3_output_and_answers_the_seven_questions():
    explored = exploration(
        {"sensor_failure": sweep(4, 3, 1, 0), "supply_delay": sweep(4, 4, 4, 3)},
        alternatives=[],
    )
    found = validate_failure_map(build_failure_map(explored))
    output, answers = found["output"], found["answers"]
    assert output["failure_points"] == found["failure_points"]
    assert output["collapse_sequence"] == [{"tick": 3, "entity": "a", "by": "x"}]
    assert (
        "sensor_failure: holds up to moderate, breaks at severe"
        in output["survival_conditions"]
    )
    assert output["recommended_modifications"][0].startswith(
        "sensor_failure breaks the plan at severe"
    )
    assert set(answers) == {
        "where_it_failed",
        "why_it_failed",
        "how_fast_it_failed",
        "which_assumption_caused_it",
        "which_variable_pushed_it_over",
        "which_alternative_survived_longer",
        "what_must_change",
    }
    assert answers["which_variable_pushed_it_over"] == {
        "variable": "sensor_failure",
        "breaking_level": "severe",
    }
    assert answers["which_assumption_caused_it"] == "combat_resolution"
    assert answers["how_fast_it_failed"]["mean_first_loss_tick"] == 3.0
    assert answers["what_must_change"] == output["recommended_modifications"]


def test_a_plan_nothing_breaks_still_says_what_to_change():
    explored = exploration({"sensor_failure": sweep(4, 4, 4, 4)}, baseline=runs(4, 0))
    found = build_failure_map(explored)
    assert found["answers"]["which_variable_pushed_it_over"] is None
    assert found["answers"]["what_must_change"] == [
        "Nothing tested breaks the plan at the levels explored."
    ]
    assert found["output"]["collapse_sequence"] == []


def test_encirclement_never_puts_a_unit_on_impassable_ground():
    base = military()
    terrain = base["world_contract"]["environment_state"]["terrain"]
    rows = [list(row) for row in terrain["rows"]]
    # flood row 1 — the free cells right behind RED — with water
    rows[1] = ["w"] * len(rows[1])
    terrain["rows"] = ["".join(row) for row in rows]
    after = stressed(base, "encirclement", "collapse", "RED")
    for unit in after["entities"]:
        if unit["faction"] == "BLUE":
            x, y = unit["position"]
            assert terrain["rows"][y][x] != "w", unit["entity_id"]


def test_tempo_delay_keeps_an_order_already_given():
    base = military()
    base["runtime"]["scheduled_actions"] = [
        {
            "tick": 1,
            "actor_id": "red_01",
            "action_type": "move",
            "target": {"location": [1, 1]},
            "system_id": "TAC_ANGEL",
        }
    ]
    after = stressed(base, "tempo_delay", "mild", "RED")
    at_tick_1 = [o for o in after["runtime"]["scheduled_actions"] if o["tick"] == 1]
    red_01 = [o for o in at_tick_1 if o["actor_id"] == "red_01"]
    assert red_01 == base["runtime"]["scheduled_actions"]
    assert len(at_tick_1) == 10  # the order, and nine units held
