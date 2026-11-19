"""Phase 12 step B: the nine system adapters, on the fixture submissions."""

import pytest
from external_runs import carry_out, fixture_run, submission

from skyvault.contracts import (
    SYSTEMS,
    ContractError,
    validate_job_request,
    validate_result_package,
)
from skyvault.interface.systems import ADAPTERS, KINDS, to_request, to_return
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.jobs import (
    NotFound,
    changed_entities,
    compare_variants,
    plan,
    scenario_for,
)

KEYS = ("win_rate", "failure_frequency", "mean_score", "mean_hp_lost")


def minus(a: dict, b: dict) -> dict:
    return {k: round(a[k] - b[k], 4) for k in KEYS}


# ── every system, its own kind ───────────────────────────────────────────────


def test_every_system_has_an_adapter_and_a_kind():
    assert set(ADAPTERS) == set(SYSTEMS) == set(KINDS)
    assert all(ADAPTERS[name].system == name for name in SYSTEMS)


def test_a_system_submits_only_its_own_kind():
    wrong = {**submission("TAC_ANGEL"), "kind": "branches"}
    with pytest.raises(ValueError, match="TAC_ANGEL submits actions, not branches"):
        to_request(wrong)


def test_a_submission_names_a_scenario():
    with pytest.raises(ValueError, match="names a scenario"):
        to_request({**submission("STARTX"), "scenario": None})


def test_an_unknown_system_is_refused_by_the_contract():
    with pytest.raises(ContractError):
        to_request({**submission("NEXUS"), "system": "SKYNET"})


def test_every_job_names_its_system_and_passes_the_job_contract():
    for system in SYSTEMS:
        request = to_request(submission(system))
        assert request["system"] == system
        for job in request["jobs"]:
            assert job["source_system"] == system
            validate_job_request(job)


# ── NEXUS ────────────────────────────────────────────────────────────────────


def test_nexus_gets_the_full_result_package_briefing_and_status():
    request, results, returned = fixture_run("NEXUS")
    assert request["jobs"] == [
        {
            "kind": "scenario_run",
            "scenario": "tactical_reference_001/v0.1",
            "source_system": "NEXUS",
        }
    ]
    package = returned["result_package"]
    validate_result_package(package)
    assert package["evaluation_result"]["winner_or_result"] == "RED_survived"
    assert len(package["event_memory"]) == 97
    assert returned["scenario_report"].startswith(
        "# SKYVAULT briefing — tactical_reference_001 v0.1"
    )
    status = returned["system_status"]
    assert status["lifecycle_state"] == "completed"
    assert status["governance"]["usage"]["events"] == 97
    # the reference run (seed 42) asks for a strategic trade-off decision
    assert status["handoff"]["reason"] == ["strategic_tradeoff"]
    assert status["handoff"]["skyvault_position"]["may_execute_final_decision"] is False


def test_nexus_without_a_report_gets_no_briefing():
    _, _, returned = carry_out(submission("NEXUS", report_format="none"))
    assert returned["scenario_report"] is None
    assert returned["result_package"] is not None


def test_nexus_tasks_are_runs_batches_and_explorations():
    batch = to_request(submission("NEXUS", task_type="batch", batch="reference_batch"))
    assert batch["jobs"][0]["kind"] == "batch"
    assert batch["jobs"][0]["batch"] == "reference_batch"
    with pytest.raises(ValueError, match="task_type"):
        to_request(submission("NEXUS", task_type="replay"))


def test_nexus_briefing_is_for_one_run_only():
    job = {
        "job_id": "job_000009",
        "request": {"kind": "batch"},
        "lifecycle_state": "completed",
        "governance": None,
        "summary": {},
        "error": None,
    }
    returned = to_return(
        [{"job": job, "result": {}, "scenario": None}], submission("NEXUS")
    )
    assert returned["scenario_report"] is None
    assert returned["gaps"] == ["a briefing is written for one run's result package"]


# ── STARTX ───────────────────────────────────────────────────────────────────


def test_startx_branches_come_back_against_the_baseline():
    request, results, returned = fixture_run("STARTX")
    (job,) = request["jobs"]
    assert job["kind"] == "branch_compare"
    assert job["repeat_count"] == 5
    assert [b["branch_id"] for b in job["branches"]] == ["press", "hold"]
    stored = {v["variant_id"]: v for v in results[0]["result"]["variants"]}
    assert set(stored) == {"branch:press", "branch:hold", "branch:none"}
    assert returned["baseline"] == stored["branch:none"]
    for branch in returned["branches"]:
        stats = stored[f"branch:{branch['branch_id']}"]
        assert branch["consequences"]["outcomes"] == stats["outcomes"]
        assert sum(stats["outcomes"].values()) == 5
        assert branch["risk"]["failure_frequency"] == stats["failure_frequency"]
        assert branch["resource_pressure"]["mean_hp_lost"] == stats["mean_hp_lost"]
        assert branch["score"]["mean"] == stats["mean_score"]
        assert branch["versus_baseline"] == minus(stats, stored["branch:none"])
    # the two branches really differ: red_002 presses forward or holds
    press, hold = returned["branches"]
    assert press["resource_pressure"] != hold["resource_pressure"]


# ── TAC ANGEL ────────────────────────────────────────────────────────────────


def test_tac_angel_gets_the_state_action_outcome_of_its_own_orders():
    request, results, returned = fixture_run("TAC_ANGEL")
    orders = request["jobs"][0]["runtime"]["scheduled_actions"]
    assert {o["system_id"] for o in orders} == {"TAC_ANGEL"}
    sao = returned["state_action_outcome"]
    assert [(t["tick"], t["action"]["actor_id"]) for t in sao] == [
        (1, "red_001"),
        (2, "red_001"),
        (3, "red_001"),
    ]
    assert [t["action"]["target_location"] for t in sao] == [[1, 1], [2, 2], [3, 3]]
    assert all(t["action"]["system_id"] == "TAC_ANGEL" for t in sao)
    assert [t["next_state"]["position"] for t in sao][:2] == [[1, 1], [2, 2]]
    outcome = returned["tactical_outcome"]
    assert outcome["orders_carried_out"] == 3
    assert outcome["orders_rejected"] == []
    assert [u["entity_id"] for u in outcome["units"]] == ["red_001"]
    assert (
        outcome["output_hash"] == results[0]["result"]["reproducibility"]["output_hash"]
    )


def test_tac_angel_hears_which_orders_skyvault_refused():
    plan_ = submission("TAC_ANGEL")
    plan_["content"]["actions"].append(
        {
            "tick": 4,
            "actor_id": "red_001",
            "action_type": "attack",
            "target": {"entity_id": "blue_003"},
            "intent": "tac_angel_strike",
        }
    )
    _, _, returned = carry_out(plan_)
    outcome = returned["tactical_outcome"]
    assert outcome["orders_carried_out"] == 3
    (refused,) = outcome["orders_rejected"]
    assert refused["tick"] == 4
    assert refused["action_type"] == "attack"
    assert "range" in refused["reason"].lower()


def test_tac_angel_in_a_running_world_goes_through_its_window():
    request = to_request(submission("TAC_ANGEL", world_id="job_000003"))
    assert request["jobs"] == []
    assert request["world_actions"]["world_id"] == "job_000003"
    assert len(request["world_actions"]["actions"]) == 3
    assert {a["system_id"] for a in request["world_actions"]["actions"]} == {
        "TAC_ANGEL"
    }


# ── EIDEN-01 ─────────────────────────────────────────────────────────────────


def test_eiden_parameters_that_map_become_variants_the_rest_gaps():
    request, results, returned = fixture_run("EIDEN_01")
    (job,) = request["jobs"]
    assert job["branches"] == [
        {
            "branch_id": "blue_002.accuracy",
            "entity_changes": {"blue_002": {"capabilities": {"accuracy": 0.75}}},
        }
    ]
    assert returned["gaps"] == [
        "blue_009: no such unit in tactical_reference_001",
        "world parameter weather='storm': tactical_reference_001 has no model for it",
    ]
    source = returned["provenance"]["sources"][0]
    assert (source["source_id"], source["source_type"], source["confidence"]) == (
        "eiden_report_017",
        "EIDEN_01",
        0.7,
    )
    # the run's scenario carries EIDEN-01 as its data provenance
    scenario = results[0]["scenario"]
    assert scenario["data_provenance"]["sources"][0]["source_id"] == "eiden_report_017"
    assert scenario["data_provenance"]["scenario_id"] == "tactical_reference_001"


def test_eiden_effect_is_the_intel_variant_against_the_baseline():
    _, results, returned = fixture_run("EIDEN_01")
    stored = {v["variant_id"]: v for v in results[0]["result"]["variants"]}
    with_intel, baseline = stored["branch:blue_002.accuracy"], stored["branch:none"]
    effect = returned["effect_on_result"]
    assert effect["versus_baseline"] == minus(with_intel, baseline)
    assert effect["with_intel"] == {k: with_intel[k] for k in KEYS}
    (only,) = returned["sensitive_variables"]
    assert only["parameter"] == "blue_002.accuracy"
    # a sharper blue_002 costs RED: lower score, more hp lost
    assert effect["versus_baseline"]["mean_score"] < 0
    assert effect["versus_baseline"]["mean_hp_lost"] > 0


def test_eiden_ranks_several_parameters_and_runs_them_together():
    intel = submission(
        "EIDEN_01",
        repeat_count=2,
        parameters=[
            {"entity_id": "blue_002", "capability": "accuracy", "value": 0.95},
            {"entity_id": "blue_001", "capability": "attack_damage", "value": 11},
        ],
    )
    request, _, returned = carry_out(intel)
    assert [b["branch_id"] for b in request["jobs"][0]["branches"]] == [
        "blue_002.accuracy",
        "blue_001.attack_damage",
        "all_intel",
    ]
    ranked = returned["sensitive_variables"]
    assert {p["parameter"] for p in ranked} == {
        "blue_002.accuracy",
        "blue_001.attack_damage",
    }
    sizes = [abs(p["versus_baseline"]["mean_score"]) for p in ranked]
    assert sizes == sorted(sizes, reverse=True)
    assert returned["gaps"] == []


def test_eiden_with_nothing_that_maps_runs_nothing():
    intel = submission("EIDEN_01", parameters=[{"world": "weather", "value": "fog"}])
    request = to_request(intel)
    assert request["supported"] is False
    assert request["jobs"] == []
    assert len(request["gaps"]) == 1


def test_eiden_capability_the_unit_lacks_is_a_gap():
    intel = submission(
        "EIDEN_01",
        parameters=[{"entity_id": "blue_002", "capability": "stealth", "value": 1}],
    )
    assert to_request(intel)["gaps"] == [
        "blue_002: the scenario does not model stealth"
    ]


# ── AEROGRID ─────────────────────────────────────────────────────────────────


def test_aerogrid_gets_coverage_gaps_and_its_reaction_window():
    request, results, returned = fixture_run("AEROGRID")
    assert request["jobs"][0]["kind"] == "scenario_run"
    coverage = returned["coverage"]
    assert 0 < coverage["min_ratio"] <= coverage["mean_ratio"] <= 1
    assert coverage["threshold"] == 0.8
    window = returned["reaction_window"]
    assert window["ticks"] == window["first_hit_tick"] - window["first_contact_tick"]
    package = results[0]["result"]
    red = {
        u
        for u, e in package["initial_world_state"]["entities"].items()
        if e["faction"] == "RED"
    }
    first_hit = min(
        e["time"]
        for e in package["event_memory"]
        if e["event_type"] == "ATTACK" and e["target_entity_id"] in red
    )
    assert window["first_hit_tick"] == first_hit
    assert returned["gaps"] == [
        "airspace configuration has a model only in airspace scenarios (Phase 15)"
    ]


def test_aerogrid_threshold_decides_which_ticks_are_thin():
    _, results, _ = fixture_run("AEROGRID")
    never = to_return(results, submission("AEROGRID", coverage_threshold=0.0))
    always = to_return(results, submission("AEROGRID", coverage_threshold=1.01))
    assert never["coverage"]["ticks_below_threshold"] == 0
    ticks = results[0]["result"]["final_world_state"]["tick"] + 1
    assert always["coverage"]["ticks_below_threshold"] == ticks


# ── SKYFOX ───────────────────────────────────────────────────────────────────


def test_skyfox_flies_its_route_under_its_own_adapter():
    request, results, returned = fixture_run("SKYFOX")
    assert [j["runtime"]["random_seed"] for j in request["jobs"]] == [42, 43, 44]
    (participant,) = request["jobs"][0]["runtime"]["participants"]
    assert participant["controls"] == {"entity_ids": ["red_01"]}
    assert participant["policy"]["params"]["route"] == [[3, 3], [5, 1]]
    for entry in results:
        moves = [
            e
            for e in entry["result"]["event_memory"]
            if e["event_type"] == "ACTION_SELECTED"
            and e["source"]["actor_id"] == "red_01"
        ]
        assert moves and {e["source"]["system_id"] for e in moves} == {"SKYFOX"}
    assert returned["mission_success_rate"] == 1.0
    assert all(r["waypoints_reached"] == [True, True] for r in returned["runs"])
    assert returned["rejected_moves"] == sum(
        len(r["rejected_moves"]) for r in returned["runs"]
    )


def test_skyfox_route_off_the_map_fails_with_refused_moves():
    _, _, returned = carry_out(
        submission("SKYFOX", route=[[3, 3], [99, 99]], repeat_count=1)
    )
    (run,) = returned["runs"]
    assert run["waypoints_reached"] == [True, False]
    assert run["mission_success"] is False
    assert returned["mission_success_rate"] == 0.0
    assert run["rejected_moves"]


# ── HADES ────────────────────────────────────────────────────────────────────


def test_hades_defence_effectiveness_reaction_and_gaps():
    request, results, returned = fixture_run("HADES")
    assert len(request["jobs"]) == 3
    assert request["jobs"][0]["runtime"]["participants"][0]["policy"] == {
        "name": "hades_adapter"
    }
    for run, entry in zip(returned["runs"], results, strict=True):
        reaction = run["reaction_time"]
        assert reaction["ticks"] == (
            reaction["first_intercept_tick"] - reaction["first_threat_tick"]
        )
        assert reaction["ticks"] >= 0
        package = entry["result"]
        engaged = {
            e["target_entity_id"]
            for e in package["event_memory"]
            if e["event_type"] in ("ATTACK", "MISS")
            and e["source"]["actor_id"] == "red_04"
        }
        assert not set(run["coverage_gaps"]) & engaged
        assert all(g.startswith("blue_") for g in run["coverage_gaps"])
        assert run["defence_effectiveness"]["intercepts"] > 0
    assert returned["coverage_gaps"] == sorted(
        {g for r in returned["runs"] for g in r["coverage_gaps"]}
    )


# ── CYBERHOUND ───────────────────────────────────────────────────────────────


def test_cyberhound_runs_the_information_environment_in_a_city():
    request, results, returned = fixture_run("CYBERHOUND")
    assert request["supported"] is True
    # without the environment, with it, with it and no counter-messaging
    assert len(request["jobs"]) == 3 * 2 == len(results)
    assert request["gaps"] == [
        "propagation_model: the information model has no such parameter"
    ]
    environment = request["jobs"][2]["rule_changes"]["city"]["information"]
    assert environment["spread"] == 0.3 and environment["backlash_threshold"] == 55
    assert environment["sources"][0]["district"] == "market"
    assert environment["initial"] == {"harbor": 30}
    assert "rule_changes" not in request["jobs"][0]
    assert request["jobs"][4]["rule_changes"]["city"]["information"]["inform_at"] > 100

    opinion = returned["opinion_change"]
    assert opinion["mean_pressure_series"][0]["mean_pressure"] > 0
    assert any(p["from"] == "market" for p in opinion["spread_paths"])
    order = returned["order_pressure"]
    # the information environment costs the city public order
    assert order["versus_without"] < 0 and order["order_lost_to_pressure"] > 0
    backlash = returned["backlash_risk"]
    assert backlash["counter_messages_per_run"] > 0
    # counter-messaging lowers the pressure it answers
    assert backlash["counter_messaging_effect"]["final_mean_pressure"] < 0
    assert 0 <= backlash["patrols_backfired"] <= 1


def test_cyberhound_outside_a_city_is_never_simulated_by_pretending():
    sub = submission("CYBERHOUND")
    sub["scenario"] = "tactical_reference_001/v0.1"
    request, results, returned = carry_out(sub)
    assert request["supported"] is False
    assert request["jobs"] == [] and results == []
    assert returned["supported"] is False
    assert returned["gaps"] == [
        "environment: tactical_reference_001 is not a city; SKYVAULT's information "
        "environment model runs on a city's districts"
    ]


# ── STAR GUARD ───────────────────────────────────────────────────────────────


def test_star_guard_equipment_replaces_a_unit_next_to_the_baseline():
    request, results, returned = fixture_run("STAR_GUARD")
    jobs = request["jobs"]
    assert len(jobs) == 6
    assert [j.get("entity_changes") is not None for j in jobs] == [True] * 3 + [
        False
    ] * 3
    equipped = results[0]["result"]["initial_world_state"]["entities"]["red_02"]
    assert equipped["name"] == "EXO-1"
    assert equipped["state"]["hp"] == 50
    assert equipped["capabilities"]["attack_damage"] == 14
    # what the profile does not name stays as it was
    assert equipped["capabilities"]["weapon"] == "rifle"
    baseline = results[3]["result"]["initial_world_state"]["entities"]["red_02"]
    assert baseline["name"] == "Red Alpha Rifleman 1"
    useful = returned["tactical_usefulness"]
    assert useful["versus_baseline"] == {
        k: round(useful["equipped"][k] - useful["baseline"][k], 4)
        for k in useful["equipped"]
    }
    feasibility = returned["physical_possibility"]
    # the fixture's refusals are all of the moment (an occupied cell): the
    # equipment itself never hit a limit
    assert feasibility["feasible"] is True and feasibility["capability_limits"] == []
    assert {r["reason"] for r in feasibility["situational_rejections"]} == {
        "Move target occupied"
    }
    assert {r["actor_id"] for r in feasibility["situational_rejections"]} == {"red_02"}
    assert useful["equipped"]["mean_hp_lost"] <= 50


def test_star_guard_fields_without_a_model_are_gaps():
    equipment = submission("STAR_GUARD")
    equipment["content"]["profile"]["mass_kg"] = 140
    request = to_request(equipment)
    assert request["gaps"] == [
        "equipment field 'mass_kg' has no model (give section 18 groups: "
        "physical_parameters, engineering_parameters, operational_parameters)"
    ]
    assert "mass_kg" not in request["jobs"][0]["entity_changes"]["red_02"]


# ── unit changes in job requests ─────────────────────────────────────────────


def test_a_request_may_change_units_it_has_never_add_one():
    request = {
        "kind": "scenario_run",
        "scenario": "tactical_reference_001/v0.1",
        "entity_changes": {"blue_099": {"capabilities": {"accuracy": 1.0}}},
    }
    with pytest.raises(NotFound, match="no units \\['blue_099'\\]"):
        plan(request, load_governance(), 0)


def test_unit_changes_merge_capabilities_and_state():
    scenario = scenario_for({"scenario": "tactical_reference_001/v0.1"})
    changed = changed_entities(
        scenario, {"blue_002": {"capabilities": {"accuracy": 0.9}, "state": {"hp": 5}}}
    )
    unit = next(u for u in changed["entities"] if u["entity_id"] == "blue_002")
    assert unit["capabilities"] == {
        "attack_damage": 16,
        "attack_range": 2,
        "accuracy": 0.9,
    }
    assert unit["state"]["hp"] == 5 and unit["state"]["ap"] == 50
    original = next(u for u in scenario["entities"] if u["entity_id"] == "blue_002")
    assert original["capabilities"]["accuracy"] == 0.55


def test_a_unit_change_names_only_known_fields():
    with pytest.raises(ContractError):
        validate_job_request(
            {
                "kind": "scenario_run",
                "scenario": "tactical_reference_001/v0.1",
                "entity_changes": {"blue_002": {"faction": "RED"}},
            }
        )


def test_branches_carry_their_unit_changes():
    variants = compare_variants(
        {
            "scenario": "tactical_reference_001/v0.1",
            "source_system": "EIDEN_01",
            "branches": [
                {
                    "branch_id": "sharp",
                    "entity_changes": {
                        "blue_002": {"capabilities": {"accuracy": 0.95}}
                    },
                }
            ],
        }
    )
    sharp, none = variants
    blue = {u["entity_id"]: u for u in sharp.scenario["entities"]}["blue_002"]
    assert blue["capabilities"]["accuracy"] == 0.95
    assert {u["entity_id"]: u for u in none.scenario["entities"]}["blue_002"][
        "capabilities"
    ]["accuracy"] == 0.55
    assert sharp.scenario["runtime"]["scheduled_actions"] == []


def test_a_submission_names_only_scenarios_skyvault_has():
    with pytest.raises(ValueError, match="nothing named"):
        to_request({**submission("SKYFOX"), "scenario": "tactical_reference_001/v9.9"})
    # a path is not a name: the submission contract refuses it first
    with pytest.raises(ContractError):
        to_request({**submission("SKYFOX"), "scenario": "../batches/reference_batch"})


def test_skyfox_energy_floor_reaches_its_adapter():
    request = to_request(submission("SKYFOX", energy_floor=25))
    params = request["jobs"][0]["runtime"]["participants"][0]["policy"]["params"]
    assert params == {"route": [[3, 3], [5, 1]], "energy_floor": 25}


def test_tac_angel_in_a_domain_hears_each_side_s_mission():
    orders = [
        {
            "tick": 1,
            "actor_id": "red_01",
            "action_type": "move",
            "target": {"location": [1, 1]},
            "intent": "tac_angel_probe",
        }
    ]
    plan_ = {
        **submission("TAC_ANGEL", actions=orders),
        "scenario": "military_squad_001/v0.1",
    }
    _, results, returned = carry_out(plan_)
    missions = returned["tactical_outcome"]["missions"]
    assert set(missions) == {"RED", "BLUE"}
    assert all(isinstance(m["achieved"], bool) for m in missions.values())
    assert returned["state_action_outcome"][0]["action"]["actor_id"] == "red_01"
    # red_01's later moves, decided by the domain's policy, were refused —
    # TAC ANGEL hears only about its own orders
    others = [
        e
        for e in results[0]["result"]["event_memory"]
        if e["event_type"] == "ACTION_REJECTED" and e["source"]["actor_id"] == "red_01"
    ]
    assert others and {e["source"]["system_id"] for e in others} == {
        "military_baseline"
    }
    assert returned["tactical_outcome"]["orders_rejected"] == []


def test_star_guard_drills_find_what_the_equipment_cannot_do():
    # red_02 starts at [0, 1]: [0, 4] is three cells — EXO-1 (move_range 3)
    # reaches it, the rifleman it replaces (move_range 2) does not
    reach = [{"tick": 1, "action_type": "move", "target": {"location": [0, 4]}}]
    _, results, returned = carry_out(
        submission("STAR_GUARD", repeat_count=1, drills=reach)
    )
    assert returned["physical_possibility"]["feasible"] is True
    baseline_drill = [
        e["data"]["reason"]
        for e in results[1]["result"]["event_memory"]
        if e["event_type"] == "ACTION_REJECTED"
        and e["source"]["system_id"] == "STAR_GUARD"
    ]
    assert baseline_drill == ["Move target out of reach: move_range=2"]

    too_far = [{"tick": 1, "action_type": "move", "target": {"location": [0, 6]}}]
    _, _, returned = carry_out(submission("STAR_GUARD", repeat_count=1, drills=too_far))
    feasibility = returned["physical_possibility"]
    assert feasibility["feasible"] is False
    (limit,) = feasibility["capability_limits"]
    assert (limit["tick"], limit["reason"]) == (
        1,
        "Move target out of reach: move_range=3",
    )
    assert limit not in feasibility["situational_rejections"]


def test_a_unit_with_nowhere_to_go_waits_instead_of_crashing():
    turret = submission("STAR_GUARD", repeat_count=1)
    turret["content"]["profile"]["capabilities"]["move_range"] = 0
    _, results, _ = carry_out(turret)
    waits = [
        e
        for e in results[0]["result"]["event_memory"]
        if e["event_type"] == "ACTION_SELECTED"
        and e["source"]["actor_id"] == "red_02"
        and e["data"]["intent"] == "cannot_move"
    ]
    assert waits


def test_cyberhound_returns_its_gaps_even_when_asked_directly():
    sub = submission("CYBERHOUND")
    sub["scenario"] = None
    returned = to_return([], sub)
    assert returned["supported"] is False
    assert returned["gaps"] == ["environment: name a city scenario to run it in"]


def test_a_request_s_provenance_is_filed_under_its_scenario():
    scenario = scenario_for(
        {
            "scenario": "tactical_reference_001/v0.1",
            "data_provenance": {
                "sources": [
                    {"source_id": "r1", "source_type": "EIDEN_01", "confidence": 0.5}
                ]
            },
        }
    )
    assert scenario["data_provenance"]["scenario_id"] == "tactical_reference_001"


# ── Formal Spec 9.2: every item every system gets back ───────────────────────


@pytest.mark.parametrize("system", sorted(KINDS))
def test_every_system_gets_back_every_item_section_9_2_lists(system):
    from skyvault.interface.systems import RETURNS, STARTX_BRANCH

    _, _, returned = fixture_run(system)
    missing = sorted(set(RETURNS[system]) - set(returned))
    assert missing == [], f"{system} return lacks {missing}"
    if system == "STARTX":
        for branch in returned["branches"]:
            assert set(STARTX_BRANCH) <= set(branch)
            curve = [row["probability"] for row in branch["risk_curve"]]
            assert curve == sorted(curve)  # P(score < x) never falls as x rises
    for key in RETURNS[system]:
        if returned[key] is None:
            # an item the world does not model says why in gaps
            assert any(g.startswith(f"{key}:") for g in returned["gaps"]), key


def test_tac_angel_s_orders_are_stress_tested_under_the_scenario_s_variables():
    request, results, returned = fixture_run("TAC_ANGEL")
    stressed = [job["stress"] for job in request["jobs"][1:]]
    assert stressed and all(list(s.values()) == ["severe"] for s in stressed)
    assert [row["stress"] for row in returned["stress_test"]] == stressed
    for row, entry in zip(returned["stress_test"], results[1:], strict=True):
        assert row["output_hash"] == entry["result"]["reproducibility"]["output_hash"]
        assert "+" in entry["result"]["scenario_version"]  # a stressed version
