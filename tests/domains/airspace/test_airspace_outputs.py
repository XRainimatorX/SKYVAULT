"""Phase 15 step C: detection gap, response time, failure points, every input."""

import copy
import json
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from skyvault.batch.run import run_batch
from skyvault.contracts import ContractError, validate_job_request
from skyvault.domains.airspace.failures import airspace_failure_variables
from skyvault.domains.airspace.metrics import (
    detection_gap,
    failure_points,
    response_times,
)
from skyvault.domains.airspace.model import covered
from skyvault.domains.airspace.pack import AIRSPACE
from skyvault.domains.airspace.reference import (
    load_rules,
    load_spec,
    reference_scenarios,
)
from skyvault.domains.airspace.report import REASONS, airspace_report
from skyvault.domains.airspace.scenario import build_airspace_scenario
from skyvault.engine import SkyVaultEngine
from skyvault.failure import build_failure_map, explore_failures
from skyvault.failure.variables import FAILURE_VARIABLES, apply_stress, variable_for
from skyvault.interface.api import run_submission
from skyvault.scenario_loader import default_evaluation_profile
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[3]
NAME = "airspace_defence_001"
SEEDS = range(42, 52)


def scenario(**spec_changes) -> dict:
    if not spec_changes:
        return copy.deepcopy(reference_scenarios()[NAME])
    spec = load_spec(NAME)
    spec.update(spec_changes)
    return build_airspace_scenario(spec, load_rules())


def run(s: dict, seed: int | None = None) -> dict:
    s = copy.deepcopy(s)
    if seed is not None:
        s["runtime"]["random_seed"] = seed
    return SkyVaultEngine(s).run()


REFERENCE = scenario()


@cache
def reference_run(seed: int = 42) -> dict:
    return run(REFERENCE, seed)


def submit(system: str, kind: str, content: dict) -> dict:
    return run_submission(
        {
            "system": system,
            "kind": kind,
            "scenario": f"{NAME}/v0.1",
            "content": content,
        },
        SQLiteStore(),
        load_governance(),
    )["returned"]


def reasons(package: dict, s: dict) -> set[str]:
    return {p["reason"] for p in failure_points(package, s)}


# ── acceptance 4: detection gap ──────────────────────────────────────────────


def test_the_detection_gap_is_the_share_no_online_sensor_covers():
    gap = detection_gap(reference_run(), REFERENCE)
    online = [
        {"at": e["position"], "range": e["capabilities"]["range"]}
        for e in REFERENCE["entities"]
        if e["entity_type"] == "sensor" and e["state"]["online"]
    ]
    assert len(online) == 3  # the spare is not switched on
    seen = len(covered(online, (20, 20)))
    assert gap["uncovered_cells"] == 400 - seen
    assert gap["uncovered_share"] == round(1 - seen / 400, 4)
    spare_on = scenario()
    next(e for e in spare_on["entities"] if e["entity_id"] == "radar_spare")["state"][
        "online"
    ] = True
    assert detection_gap(reference_run(), spare_on)["uncovered_share"] < (
        gap["uncovered_share"]
    )


def test_every_threat_has_its_launch_first_detection_and_the_ticks_between():
    gap = detection_gap(reference_run(), REFERENCE)
    assert len(gap["threats"]) == 7
    for threat in gap["threats"].values():
        assert threat["first_detected"] >= threat["launch_tick"]
        assert threat["ticks_to_detect"] == (
            threat["first_detected"] - threat["launch_tick"]
        )
    waits = [t["ticks_to_detect"] for t in gap["threats"].values()]
    assert gap["mean_ticks_to_detect"] == round(sum(waits) / len(waits), 4)
    assert gap["worst_ticks_to_detect"] == max(waits)
    assert gap["undetected_leaks"] == []


def test_without_sensors_every_threat_leaks_undetected():
    blind = scenario(sensors=[])
    package = run(blind)
    gap = detection_gap(package, blind)
    assert gap["uncovered_share"] == 1.0
    assert gap["mean_ticks_to_detect"] is None
    assert len(gap["undetected_leaks"]) == 7
    assert reasons(package, blind) == {"never_detected"}


# ── acceptance 4: response time ──────────────────────────────────────────────


def test_response_and_reaction_are_measured_from_the_track_and_the_window():
    times = response_times(reference_run(), REFERENCE)
    assert set(times["threats"]) == {
        e["entity_id"] for e in REFERENCE["entities"] if e["entity_type"] == "threat"
    }
    for entry in times["threats"].values():
        assert entry["first_engaged"] >= entry["track_opened"]
        assert entry["response_ticks"] == (
            entry["first_engaged"] - entry["track_opened"]
        )
        # the tick it was shot down in is inside its window
        assert entry["first_engaged"] >= entry["engageable_from"]
        assert entry["reaction_ticks"] == (
            entry["first_engaged"] - entry["engageable_from"]
        )
        assert entry["reaction_ticks"] <= entry["response_ticks"]
    responses = [e["response_ticks"] for e in times["threats"].values()]
    assert times["worst"] == max(responses)
    assert times["never_engaged"] == []


def test_a_defence_that_cannot_fire_never_responds():
    dry = scenario()
    for e in dry["entities"]:
        if e["entity_type"] == "interceptor":
            e["state"]["ammo"] = 0
    times = response_times(run(dry), dry)
    assert times["mean"] is None and times["mean_reaction"] is None
    assert len(times["never_engaged"]) == len(times["threats"]) > 0


# ── acceptance 4: failure points, one reason each ────────────────────────────


def test_every_leak_is_a_failure_point_with_one_reason():
    for seed in SEEDS:
        package = reference_run(seed)
        points = failure_points(package, REFERENCE)
        leaked = [
            u
            for u, e in package["final_world_state"]["entities"].items()
            if e["entity_type"] == "threat" and e["state"]["status"] == "leaked"
        ]
        assert sorted(p["entity_id"] for p in points if p["kind"] == "leak") == sorted(
            leaked
        )
        for point in points:
            assert point["reason"] in REASONS


def test_a_clean_defence_has_no_failure_points():
    assert failure_points(reference_run(), REFERENCE) == []


def with_command(**command) -> dict:
    spec = load_spec(NAME)
    spec["command"].update(command)
    return build_airspace_scenario(spec, load_rules())


def interceptors(**changes) -> list[dict]:
    found = copy.deepcopy(load_spec(NAME)["interceptors"])
    for i in found:
        i.update(changes)
    return found


@pytest.mark.parametrize(
    "build,reason",
    [
        (lambda: with_command(identify=0.0), "misidentified"),
        (lambda: with_command(reaction_delay=50), "detected_too_late"),
        (lambda: scenario(interceptors=interceptors(at=[0, 19])), "no_window"),
        (lambda: scenario(interceptors=interceptors(kill=0.0)), "missed_in_window"),
        (lambda: scenario(interceptors=interceptors(ammo=0)), "not_engaged"),
    ],
)
def test_each_way_a_threat_gets_through_has_its_reason(build, reason):
    s = build()
    package = run(s)
    found = [p for p in failure_points(package, s) if p["kind"] == "leak"]
    assert reason in {p["reason"] for p in found}
    if reason != "missed_in_window":  # a gun that cannot kill is also kept busy
        assert {p["reason"] for p in found} == {reason}
    first = found[0]
    assert first["target"] in ("power_station", "command_post")
    assert first["at"] == next(
        e["position"] for e in s["entities"] if e["entity_id"] == first["target"]
    )


def test_a_missed_threat_was_fired_on_inside_its_window():
    s = scenario(interceptors=interceptors(kill=0.0))
    points = failure_points(run(s), s)
    missed = [p for p in points if p["reason"] == "missed_in_window"]
    assert missed
    for point in missed:
        assert point["salvos"] > 0 and point["interception_window"]
    for point in points:
        if point["reason"] == "not_engaged":
            assert point["salvos"] == 0 and point["interception_window"]


def test_a_drone_that_collides_with_a_threat_is_a_failure_point():
    s = scenario(
        sensors=[], patrols=[{"id": "skyfox_1", "route": [[15, 4]], "speed": 1}]
    )
    package = run(s)
    (lost,) = [p for p in failure_points(package, s) if p["kind"] == "drone_lost"]
    assert lost["reason"] == "collision" and lost["at"] == [15, 4]
    assert package["final_world_state"]["entities"]["threat_w2_1"]["state"][
        "status"
    ] == ("destroyed")


# ── acceptance 2: SKYFOX in the same airspace ────────────────────────────────


def fratricide(package: dict) -> int:
    return sum(
        1
        for e in package["event_memory"]
        if e["event_type"] == "ENTITY_DESTROYED" and "fratricide" in e["tags"]
    )


def test_a_skyfox_taken_for_a_threat_can_be_shot_down_by_its_own_side():
    confused = with_command(identify=0.0)
    losses = [fratricide(run(confused, seed)) for seed in SEEDS]
    assert any(losses)
    package = next(run(confused, s) for s in SEEDS if fratricide(run(confused, s)))
    points = failure_points(package, confused)
    assert {"kind": "drone_lost", "reason": "fratricide"}.items() <= next(
        p for p in points if p["kind"] == "drone_lost"
    ).items()
    assert AIRSPACE.airspace_outcome(package, confused)["fratricide"] == 1


def test_a_skyfox_never_misidentified_is_never_shot_by_its_own_side():
    certain = with_command(identify=1.0)
    assert [fratricide(run(certain, seed)) for seed in SEEDS] == [0] * len(SEEDS)


def test_skyfox_flies_its_route_in_the_airspace_under_its_own_adapter():
    returned = submit(
        "SKYFOX",
        "mission",
        {"drone": "skyfox_1", "route": [[7, 6], [8, 6]], "repeat_count": 2},
    )
    assert returned["supported"] is True
    assert returned["mission_success_rate"] == 1.0
    for r in returned["runs"]:
        assert r["waypoints_reached"] == [True, True]
        assert r["rejected_moves"] == []


# ── acceptance 1 and 3 through the interface ─────────────────────────────────


def test_the_rules_hades_submits_change_how_many_threats_get_through():
    baseline = submit("HADES", "defence", {"behavior": {}, "repeat_count": 5})
    close = submit(
        "HADES", "defence", {"behavior": {"engage_at": 0.5}, "repeat_count": 5}
    )
    assert baseline["behavior"] == {} and close["behavior"] == {"engage_at": 0.5}
    assert close["airspace"]["mean_leaks"] > baseline["airspace"]["mean_leaks"]
    assert close["airspace"]["defended_rate"] < baseline["airspace"]["defended_rate"]
    assert len(baseline["airspace"]["runs"]) == 5
    assert baseline["gaps"] == []


def test_the_sensors_aerogrid_submits_change_coverage_and_detection():
    built = submit("AEROGRID", "airspace", {"sensors": {}, "repeat_count": 3})
    west = submit(
        "AEROGRID",
        "airspace",
        {
            "sensors": {"radar_spare": {"position": [5, 10], "online": True}},
            "repeat_count": 3,
        },
    )
    off = submit(
        "AEROGRID",
        "airspace",
        {"sensors": {"radar_south": {"online": False}}, "repeat_count": 3},
    )
    gap = {
        k: r["airspace"]["uncovered_share"]
        for k, r in (("built", built), ("west", west), ("off", off))
    }
    assert gap["west"] < gap["built"] < gap["off"]
    assert west["airspace"]["mean_ticks_to_detect"] < (
        built["airspace"]["mean_ticks_to_detect"]
    )
    assert built["gaps"] == []


def test_aerogrid_can_retune_a_sensor_and_reaches_only_sensors_it_has():
    returned = submit(
        "AEROGRID",
        "airspace",
        {"sensors": {"radar_north": {"range": 2, "detection": 0.1}}, "repeat_count": 1},
    )
    assert (
        returned["airspace"]["uncovered_share"]
        > detection_gap(reference_run(), REFERENCE)["uncovered_share"]
    )
    with pytest.raises(Exception, match="radar_moon"):
        submit(
            "AEROGRID",
            "airspace",
            {"sensors": {"radar_moon": {"online": True}}, "repeat_count": 1},
        )


def test_a_unit_change_may_move_a_unit_but_not_off_the_map():
    request = {
        "kind": "scenario_run",
        "scenario": f"{NAME}/v0.1",
        "entity_changes": {"radar_spare": {"position": [5, 10]}},
    }
    assert validate_job_request(request)["entity_changes"]["radar_spare"][
        "position"
    ] == [5, 10]
    with pytest.raises(ContractError):
        validate_job_request(
            {**request, "entity_changes": {"radar_spare": {"faction": "THREAT"}}}
        )
    with pytest.raises(Exception, match="outside|placed at"):
        submit(
            "AEROGRID",
            "airspace",
            {"sensors": {"radar_spare": {"position": [40, 40]}}, "repeat_count": 1},
        )


def test_nexus_gets_the_airspace_outcome_through_the_world_service():
    returned = run_submission(
        {"system": "NEXUS", "kind": "task", "scenario": f"{NAME}/v0.1", "content": {}},
        SQLiteStore(),
        load_governance(),
    )["returned"]
    package = returned["result_package"]
    assert package["evaluation_result"]["winner_or_result"] == "defended"
    outcome = returned["domain_outcome"]["airspace_outcome"]
    assert outcome == AIRSPACE.airspace_outcome(reference_run(), REFERENCE)


# ── failure variables, exploration and batch ─────────────────────────────────


def test_the_airspace_reads_three_variables_in_its_own_terms():
    for name in ("sensor_failure", "enemy_reaction_speed", "equipment_overheat"):
        assert variable_for(REFERENCE, name) is not FAILURE_VARIABLES.get(name)
    assert (
        variable_for(REFERENCE, "communication_failure")
        is FAILURE_VARIABLES["communication_failure"]
    )
    blind = apply_stress(REFERENCE, {"sensor_failure": "collapse"}, "DEFENCE")
    north = next(e for e in blind["entities"] if e["entity_id"] == "radar_north")
    assert north["capabilities"]["detection"] == 0.34  # 0.85 × 0.4
    fast = apply_stress(REFERENCE, {"enemy_reaction_speed": "mild"}, "DEFENCE")
    threat = next(e for e in fast["entities"] if e["entity_type"] == "threat")
    assert threat["capabilities"]["speed"] == 1.25
    hot = apply_stress(REFERENCE, {"equipment_overheat": "severe"}, "DEFENCE")
    gun = next(e for e in hot["entities"] if e["entity_id"] == "gun_west")
    assert gun["capabilities"]["kill"] == 0.375  # 0.75 × 0.5


def test_a_fractional_speed_carries_over_from_tick_to_tick():
    fast = apply_stress(REFERENCE, {"enemy_reaction_speed": "mild"}, "DEFENCE")
    package = run(fast)
    steps = [
        e["data"]
        for e in package["event_memory"]
        if "fly" in e["tags"] and e["source"]["actor_id"] == "threat_w1_2"
    ]
    lengths = [
        max(abs(a - b) for a, b in zip(s["from"], s["to"], strict=True)) for s in steps
    ]
    assert lengths[:4] == [1, 1, 1, 2]  # 1.25 a tick: a second cell every fourth


def test_an_airspace_without_the_thing_a_variable_degrades_says_so():
    variables = airspace_failure_variables()
    bare = copy.deepcopy(REFERENCE)
    bare["entities"] = [e for e in bare["entities"] if e["entity_type"] == "asset"]
    assert variables["sensor_failure"].applies(bare, "DEFENCE") == (
        False,
        "the airspace has no sensors",
    )
    assert variables["enemy_reaction_speed"].applies(bare, "DEFENCE")[0] is False
    assert variables["equipment_overheat"].applies(bare, "DEFENCE")[0] is False


def test_failure_exploration_finds_where_the_defence_breaks():
    profile = default_evaluation_profile(REFERENCE)
    config = copy.deepcopy(REFERENCE["failure_exploration"])
    config["run_policy"]["repeat_count"] = 5
    failure_map = build_failure_map(explore_failures(REFERENCE, profile, config))
    assert failure_map["baseline"]["survival_rate"] == 1.0
    by_name = {v["variable"]: v for v in failure_map["variables"]}
    assert by_name["sensor_failure"]["breaking_level"] == "moderate"
    assert by_name["equipment_overheat"]["breaking_level"] == "severe"
    for variable in by_name.values():
        rates = [level["survival_rate"] for level in variable["levels"]]
        assert rates[-1] < failure_map["baseline"]["survival_rate"]


def test_an_airspace_batch_counts_a_defended_run_as_a_win():
    spec = json.loads((ROOT / "data/batches/airspace_sensors.json").read_text())
    spec["run_policy"]["repeat_count"] = 10
    result = run_batch(spec)["batch_result"]
    rates = {v["variant_id"].rsplit("=", 1)[1]: v for v in result["variants"]}
    assert rates["True"]["win_rate"] == 0.7 and rates["True"]["loss_rate"] == 0.3
    assert rates["False"]["win_rate"] < rates["True"]["win_rate"]
    assert rates["False"]["draw_rate"] == 0.0


# ── the report and the script ────────────────────────────────────────────────


def test_the_report_says_what_happened_in_words():
    breached = with_command(identify=0.0)
    package = run(breached)
    outcome = AIRSPACE.airspace_outcome(package, breached)
    row = {
        "defended_rate": 0.5,
        "mean_leaks": 1.25,
        "uncovered_share": 0.2,
        "mean_ticks_to_detect": None,
        "mean_reaction_ticks": 1.5,
    }
    text = airspace_report(
        {
            "scenario": NAME,
            "seed": 42,
            "runs": 3,
            "reference": outcome,
            "behaviors": {"baseline": row},
            "configs": {"as built": row},
        }
    )
    assert "Outcome: breached" in text
    assert "taken for a friend" in text
    assert "seeds 42–44" in text
    assert "| baseline | 50% | 1.2 | 20% | — | 1.5 |" in text


def test_run_airspace_writes_the_outcome_comparisons_and_report(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_airspace.py"),
            "--output",
            str(tmp_path),
            "--runs",
            "2",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"{NAME}: defended, 0 leak(s)" in done.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "airspace_report.md",
        "behaviors.json",
        "configs.json",
        f"outcome_{NAME}.json",
    ]
    behaviors = json.loads((tmp_path / "behaviors.json").read_text())
    assert list(behaviors) == [
        "baseline",
        "close in (engage_at 0.5)",
        "first tracked",
        "hold fire below 0.6",
        "salvo 2",
    ]
    configs = json.loads((tmp_path / "configs.json").read_text())
    assert configs["south radar off"]["uncovered_share"] > (
        configs["as built"]["uncovered_share"]
    )
    outcome = json.loads((tmp_path / f"outcome_{NAME}.json").read_text())
    assert outcome == json.loads(
        json.dumps(AIRSPACE.airspace_outcome(reference_run(), REFERENCE))
    )
