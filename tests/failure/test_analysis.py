"""Failure analysis on hand-made runs: every rule, every edge."""

import ast
import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import validate_failure_map
from skyvault.failure.analysis import (
    RECOMMENDATIONS,
    breaking_level,
    build_collapse_sequence,
    build_failure_map,
    build_survival_conditions,
    render_recommended_modifications,
    sensitivity,
    survival_rate,
)
from skyvault.failure.variables import FAILURE_VARIABLES

LEVELS = ["mild", "moderate", "severe", "collapse"]


def run(survived=True, score=0.5, losses=(), causes=(), seed=1, outcome="RED_survived"):
    losses = [{"tick": t, "entity": e, "by": b} for t, e, b in losses]
    return {
        "seed": seed,
        "scenario_version": "v1",
        "status": "risky" if survived else "fail",
        "survived": survived,
        "score": score,
        "outcome": outcome,
        "event_count": 10,
        "losses": losses,
        "first_loss_tick": losses[0]["tick"] if losses else None,
        "elimination_tick": None,
        "failure_causes": list(causes),
        "output_hash": "0" * 64,
    }


def runs(alive, dead, **failed):
    return [run(True) for _ in range(alive)] + [
        run(False, **failed) for _ in range(dead)
    ]


def sweep(*rates_per_level):
    """Levels with the given survival counts out of 4."""
    return {
        level: runs(alive, 4 - alive, losses=[(3, "a", "x")])
        for level, alive in zip(LEVELS, rates_per_level, strict=False)
    }


def exploration(variables, baseline=None, alternatives=(), branches=()):
    return {
        "scenario_id": "s",
        "scenario_version": "v1",
        "perspective": "RED",
        "profile_id": "balanced",
        "objective": "find_weakness",
        "repeat_count": 4,
        "seeds": [1, 2, 3, 4],
        "survival_threshold": 0.5,
        "stress_levels": LEVELS,
        "baseline": baseline if baseline is not None else runs(4, 0),
        "variables": {
            name: {
                "applicable": levels is not None,
                "reason": "" if levels is not None else "nothing to stress",
                "assumption": FAILURE_VARIABLES[name].assumption,
                "levels": levels or {},
            }
            for name, levels in variables.items()
        },
        "branches": list(branches),
        "alternatives": list(alternatives),
    }


# ── the basic measures ───────────────────────────────────────────────────────


def test_survival_and_sensitivity():
    baseline = runs(3, 1)

    assert survival_rate(baseline) == 0.75
    assert survival_rate([]) == 0.0
    assert sensitivity(baseline, {"mild": runs(1, 3)}) == 0.5
    assert sensitivity(baseline, {"mild": runs(4, 0)}) == -0.25  # the stress helped
    assert sensitivity(baseline, {}) == 0.0


def test_the_breaking_level_is_the_first_below_the_threshold():
    levels = sweep(4, 2, 1, 0)

    assert breaking_level(levels, LEVELS, 0.5) == "severe"
    assert breaking_level(levels, LEVELS, 0.6) == "moderate"
    assert breaking_level(sweep(4, 4, 4, 4), LEVELS, 0.5) is None


# ── the failure map ──────────────────────────────────────────────────────────


def test_the_crushing_variable_has_the_largest_drop_and_ties_go_to_the_sooner_break():
    # Equal drops. Alphabetically civilian_pressure comes first, but weather
    # breaks sooner, so only the breaking-level rule can pick weather
    data = exploration(
        {
            "civilian_pressure": sweep(4, 4, 4, 0),  # drop 1.0, breaks at collapse
            "weather_degradation": sweep(4, 1, 0, 0),  # drop 1.0, breaks at moderate
            "sensor_failure": sweep(4, 3, 3, 3),  # drop 0.25, never breaks
        }
    )

    result = validate_failure_map(build_failure_map(data))

    assert result["crushing_variable"] == "weather_degradation"
    assert result["crushing_assumption"] == "combat_resolution"
    breaks = {v["variable"]: v["breaking_level"] for v in result["variables"]}
    assert breaks == {
        "civilian_pressure": "collapse",
        "weather_degradation": "moderate",
        "sensor_failure": None,
    }


def test_no_variable_crushes_a_plan_that_stress_never_hurts():
    result = build_failure_map(exploration({"weather_degradation": sweep(4, 4, 4, 4)}))

    assert result["crushing_variable"] is None
    assert result["crushing_assumption"] is None


def test_a_plan_that_fails_unstressed_is_flagged():
    result = build_failure_map(
        exploration({"weather_degradation": sweep(1, 1, 1, 1)}, baseline=runs(1, 3))
    )

    assert result["baseline"]["fails_without_stress"] is True
    assert result["baseline"]["survival_rate"] == 0.25


def test_failure_points_and_causes_count_failed_runs():
    failing = [
        run(
            False,
            losses=[(4, "red_3", "blue_1")],
            causes=["time_cost 0.00: x", "time_cost 0.00: y"],
        ),
        run(
            False,
            losses=[(4, "red_3", "blue_1")],
            causes=["Anti-gaming: maximize_score_by_inaction"],
        ),
        run(False, losses=[(7, "red_1", "blue_2")], causes=["time_cost 0.10: z"]),
    ]
    result = build_failure_map(exploration({}, baseline=failing + runs(1, 0)))

    assert result["failure_points"] == [
        "red_3 lost at tick 4 to blue_1 (2 of 3 failed runs)",
        "red_1 lost at tick 7 to blue_2 (1 of 3 failed runs)",
    ]
    assert result["failure_causes"] == [
        "time_cost too low in 2 of 3 failed runs",
        "Anti-gaming: maximize_score_by_inaction in 1 of 3 failed runs",
    ]
    assert result["how_fast"]["mean_first_loss_tick"] == 5.0


@pytest.mark.parametrize(
    ("alt_baseline", "alt_levels", "verdict", "longer", "sooner"),
    [
        (runs(4, 0), sweep(4, 4, 4, 4), "holds_longer", ["weather_degradation"], []),
        (runs(4, 0), sweep(4, 0, 0, 0), "breaks_sooner", [], ["weather_degradation"]),
        (runs(2, 2), sweep(4, 4, 4, 4), "mixed", ["weather_degradation"], ["baseline"]),
        (runs(4, 0), sweep(4, 4, 1, 0), "same", [], []),
    ],
)
def test_an_alternative_is_judged_against_the_plan(
    alt_baseline, alt_levels, verdict, longer, sooner
):
    plan_levels = sweep(4, 4, 1, 0)  # the plan breaks at severe
    alternative = {
        "scenario_version": "v1-alt",
        "baseline": alt_baseline,
        "variables": exploration({"weather_degradation": alt_levels})["variables"],
    }

    result = build_failure_map(
        exploration({"weather_degradation": plan_levels}, alternatives=[alternative])
    )

    check_alternative(result, verdict, longer, sooner)


def check_alternative(result, verdict, longer, sooner):
    [judged] = result["alternatives"]
    assert judged["verdict"] == verdict
    assert judged["holds_longer_on"] == longer
    assert judged["breaks_sooner_on"] == sooner
    assert result["best_alternative"] == (
        "v1-alt" if verdict == "holds_longer" else None
    )


def test_an_alternative_that_survives_more_unstressed_holds_longer():
    # The plan survives half its unstressed runs; the alternative all of them
    alternative = {
        "scenario_version": "v1-alt",
        "baseline": runs(4, 0),
        "variables": exploration({"weather_degradation": sweep(4, 4, 1, 0)})[
            "variables"
        ],
    }

    result = build_failure_map(
        exploration(
            {"weather_degradation": sweep(4, 4, 1, 0)},
            baseline=runs(2, 2),
            alternatives=[alternative],
        )
    )

    check_alternative(result, "holds_longer", ["baseline"], [])


def test_the_best_alternative_is_the_one_that_survives_most():
    def alternative(version, alive):
        return {
            "scenario_version": version,
            "baseline": runs(4, 0),
            "variables": exploration({"weather_degradation": sweep(4, 4, alive, 4)})[
                "variables"
            ],
        }

    result = build_failure_map(
        exploration(
            {"weather_degradation": sweep(4, 4, 0, 0)},
            alternatives=[alternative("steady", 3), alternative("sturdier", 4)],
        )
    )

    assert result["best_alternative"] == "sturdier"


def test_the_analysis_never_changes_the_exploration():
    data = exploration({"weather_degradation": sweep(4, 2, 1, 0)})
    before = copy.deepcopy(data)

    build_failure_map(data)
    build_collapse_sequence(data)

    assert data == before


# ── collapse sequence, survival conditions, recommendations ─────────────────


def test_the_collapse_sequence_follows_the_crushing_variable_at_its_break():
    levels = sweep(4, 4, 1, 0)
    levels["severe"][1]["losses"] = [
        {"tick": 2, "entity": "red_1", "by": "blue_1"},
        {"tick": 5, "entity": "red_2", "by": "blue_3"},
    ]
    levels["severe"][1]["seed"] = 9

    sequence = build_collapse_sequence(exploration({"weather_degradation": levels}))

    assert sequence["stress"] == "weather_degradation:severe"
    assert sequence["seed"] == 9
    assert [loss["entity"] for loss in sequence["sequence"]] == ["red_1", "red_2"]


def test_without_any_failure_there_is_no_collapse():
    sequence = build_collapse_sequence(
        exploration({"weather_degradation": sweep(4, 4, 4, 4)})
    )

    assert sequence == {
        "scenario_id": "s",
        "stress": "baseline",
        "collapse": None,
        "reason": "no run failed under this stress",
    }


def test_survival_conditions_name_the_last_level_that_holds():
    result = build_failure_map(
        exploration(
            {
                "weather_degradation": sweep(4, 4, 1, 0),
                "equipment_overheat": sweep(0, 0, 0, 0),
                "sensor_failure": sweep(4, 4, 4, 4),
                "supply_delay": None,
            }
        )
    )

    conditions = build_survival_conditions(result)

    assert conditions["conditions"] == [
        "weather_degradation: holds up to moderate, breaks at severe",
        "equipment_overheat: breaks already at mild",
        "sensor_failure: holds at every tested level",
    ]
    assert conditions["per_variable"]["weather_degradation"] == {
        "holds_up_to": "moderate",
        "breaks_at": "severe",
    }
    assert conditions["untested"] == ["supply_delay: nothing to stress"]


def test_the_recommendations_put_the_crushing_variable_first():
    result = build_failure_map(
        exploration(
            {
                "weather_degradation": sweep(4, 4, 1, 0),
                "equipment_overheat": sweep(4, 0, 0, 0),
            },
            baseline=runs(1, 3),
        )
    )

    text = render_recommended_modifications(result, build_survival_conditions(result))

    must = (
        text.split("## Must change before acting\n\n")[1].split("\n\n")[0].splitlines()
    )
    assert must[0].startswith(
        "1. The plan already fails in most runs without any stress"
    )
    assert must[1] == (
        "2. **equipment_overheat** breaks the plan at moderate: "
        + RECOMMENDATIONS["equipment_overheat"]
    )
    assert must[2].startswith("3. **weather_degradation** breaks the plan at severe")


def test_a_plan_nothing_breaks_says_so():
    result = build_failure_map(exploration({"weather_degradation": sweep(4, 4, 4, 4)}))

    text = render_recommended_modifications(result, build_survival_conditions(result))

    assert "1. Nothing tested breaks the plan at the levels explored." in text
    assert "- No run failed." in text


def test_every_variable_has_a_recommendation():
    assert set(RECOMMENDATIONS) == set(FAILURE_VARIABLES)


@pytest.mark.parametrize("module", ["analysis.py", "variables.py"])
def test_analysis_and_variables_never_import_the_engine(module):
    path = SRC_PATH / "skyvault" / "failure" / module
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
            if module == "analysis.py":
                assert node.level == 0, "analysis.py imports nothing from the project"

    assert not names & {"engine", "verification", "explore"}
