"""Screens: each view shows what the run recorded, in a fixed order."""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.timeline import render_timeline
from skyvault.views import (
    causal_view,
    comparison_view,
    failure_view,
    load_workspace,
    map_view,
    overview_view,
    package_view,
    timeline_view,
)


@pytest.fixture(scope="module")
def workspace(reference_workspace):
    return load_workspace(reference_workspace)


@pytest.fixture(scope="module")
def package(workspace):
    return workspace["result_package"]


# ── the workspace ────────────────────────────────────────────────────────────


def test_a_workspace_without_a_result_package_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError, match="no result package"):
        load_workspace(tmp_path)


def test_missing_optional_outputs_are_none(run_only_workspace):
    loaded = load_workspace(run_only_workspace)

    assert loaded["result_package"]["scenario_id"] == "tactical_reference_001"
    assert {key for key, value in loaded.items() if value is None} == {
        "failure_map",
        "collapse_sequence",
        "survival_conditions",
        "recommended_modifications",
        "batch_result",
        "branch_comparison",
        "conflict_package",
        "comparative_report",
    }
    assert failure_view(loaded) is None
    assert comparison_view(loaded) is None


# ── overview, timeline, losses ───────────────────────────────────────────────


def test_the_overview_reads_like_the_run(package):
    overview = overview_view(package)

    assert (overview["result"], overview["verdict"]) == ("RED_survived", "risky")
    assert (overview["score"], overview["profile_id"]) == (0.5045, "balanced")
    assert (overview["event_count"], overview["ticks"]) == (97, 10)
    assert overview["scores"]["recovery_ability"] == 0.0
    assert overview["flagged_behaviors"] == [
        "sacrifice_long_term_stability_for_short_term_success"
    ]


def test_losses_name_the_unit_the_tick_and_who_did_it(package):
    red, blue = overview_view(package)["losses"]

    assert (red["faction"], red["units"]) == ("RED", 3)
    assert red["lost"] == [
        {
            "entity_id": "red_003",
            "name": "Red Commander",
            "tick": 6,
            "by": "blue_002",
            "by_name": "Blue Support",
        }
    ]
    assert [(u["name"], u["tick"]) for u in blue["lost"]] == [
        ("Blue Commander", 6),
        ("Blue Support", 7),
        ("Blue Rifleman", 10),
    ]


def test_the_timeline_is_the_exporters_sentences_tick_by_tick(package):
    ticks = timeline_view(package)["ticks"]
    text = render_timeline(package["scenario_id"], package["event_memory"])

    assert [tick["tick"] for tick in ticks] == list(range(1, 11))
    assert ticks[5]["lines"][:3] == [
        "Red Rifleman selected ATTACK against Blue Commander",
        "Red Rifleman successfully attacked Blue Commander: HP 7 -> 0 (damage = 10)",
        "Blue Commander in the BLUE faction was destroyed by Red Rifleman",
    ]
    assert [d["name"] for d in ticks[5]["destroyed"]] == [
        "Blue Commander",
        "Red Commander",
    ]
    for tick in ticks:
        for line in tick["lines"]:
            assert line in text


# ── the map ──────────────────────────────────────────────────────────────────


def test_the_map_has_a_frame_for_the_start_and_every_tick(package):
    view = map_view(package)

    assert view["space"] == {"type": "grid", "width": 10, "height": 10}
    assert [frame["tick"] for frame in view["frames"]] == list(range(11))
    start = {u["entity_id"]: u for u in view["frames"][0]["units"]}
    assert start["red_001"]["position"] == [0, 0]
    assert view["frames"][0]["lines"] == []


def test_units_move_lose_hp_and_are_destroyed_frame_by_frame(package):
    frames = map_view(package)["frames"]
    commander = [
        next(u for u in frame["units"] if u["entity_id"] == "red_003")
        for frame in frames
    ]

    assert commander[0]["position"] != commander[5]["position"]
    assert (commander[5]["hp"], commander[5]["status"]) == (13, "active")
    assert (commander[6]["hp"], commander[6]["status"]) == (0, "destroyed")
    assert {unit["max_hp"] for unit in commander} == {commander[0]["hp"]}
    assert frames[6]["lines"][-1] == (
        "Red Commander in the RED faction was destroyed by Blue Support"
    )


def test_a_graph_space_is_drawn_on_a_circle_in_node_order():
    with (FIXTURES / "result_package_valid.json").open(encoding="utf-8") as file:
        package = json.load(file)
    graph = copy.deepcopy(package)
    graph["event_memory"] = []  # its one event carries a partial snapshot
    graph["initial_world_state"]["space"] = {
        "type": "graph",
        "nodes": ["a", "b", "c", "d"],
        "edges": [["a", "b"], ["b", "c"]],
    }

    space = map_view(graph)["space"]

    assert space["nodes"] == [
        {"id": "a", "x": 1.0, "y": 0.0},
        {"id": "b", "x": 0.0, "y": 1.0},
        {"id": "c", "x": -1.0, "y": 0.0},
        {"id": "d", "x": 0.0, "y": -1.0},
    ]
    assert space["edges"] == [["a", "b"], ["b", "c"]]
    assert "-0.0" not in json.dumps(space)


# ── causal chain, failure map, comparison, package ───────────────────────────


def test_every_action_is_a_named_chain(package):
    chains = causal_view(package)["chains"]

    assert len(chains) == 46
    assert chains[0]["actor"] == "Red Rifleman"
    assert chains[0]["event_types"] == ["MOVE"]
    attack = next(c for c in chains if "ENTITY_DESTROYED" in c["event_types"])
    assert (attack["tick"], attack["actor"], attack["target"]) == (
        6,
        "Red Rifleman",
        "Blue Commander",
    )


def test_the_failure_map_is_a_table_of_survival_by_level(workspace):
    view = failure_view(workspace)

    assert view["levels"] == ["mild", "moderate", "severe", "collapse"]
    rows = {row["variable"]: row for row in view["rows"]}
    assert rows["communication_failure"]["survival"] == [0.7, 0.8, 0.5, 0.0]
    assert rows["communication_failure"]["breaking_level"] == "collapse"
    assert len(rows) == 6
    assert view["baseline_survival"] == 0.6
    assert view["crushing_variable"] == "communication_failure"
    assert view["best_alternative"] == "v0.1-support-rear"
    assert view["recommendations"].startswith("# Recommended modifications")
    assert view["collapse_sequence"]["stress"] == "communication_failure:collapse"


def test_levels_follow_stress_order_and_gaps_stay_empty():
    failure_map = {
        "scenario_version": "v",
        "repeat_count": 1,
        "survival_threshold": 0.5,
        "baseline": {"survival_rate": 1.0, "fails_without_stress": False},
        "variables": [
            {
                "variable": "x",
                "applicable": True,
                "reason": "",
                "assumption": "a",
                "levels": [
                    {"level": "collapse", "survival_rate": 0.1},
                    {"level": "mild", "survival_rate": 0.9},
                ],
                "breaking_level": "collapse",
                "sensitivity": 0.9,
            },
            {
                "variable": "y",
                "applicable": True,
                "reason": "",
                "assumption": "a",
                "levels": [{"level": "severe", "survival_rate": 0.4}],
                "breaking_level": "severe",
                "sensitivity": 0.6,
            },
        ],
        "crushing_variable": "x",
        "crushing_assumption": "a",
        "failure_points": [],
        "failure_causes": [],
        "how_fast": {},
        "alternatives": [],
        "best_alternative": None,
    }

    view = failure_view({"failure_map": failure_map})

    assert view["levels"] == ["mild", "severe", "collapse"]
    assert [row["survival"] for row in view["rows"]] == [
        [0.9, None, 0.1],
        [None, 0.4, None],
    ]
    assert view["conditions"] == [] and view["recommendations"] is None


def test_the_comparison_shows_variants_not_runs(workspace):
    view = comparison_view(workspace)

    assert view["total_runs"] == 900
    assert [v["variant_id"] for v in view["variants"]][-3:] == [
        "branch:P1",
        "branch:P2+P3",
        "branch:none",
    ]
    assert view["best"]["mean_score"] == "support-rear"
    assert view["conflict_package"]["recommendation_to_nexus"]["required_decision"]
    assert "runs" not in view


def test_every_part_of_the_package_has_a_label_and_a_summary(package):
    sections = {s["key"]: s for s in package_view(package)["sections"]}

    assert list(sections) == list(package)
    assert sections["event_memory"]["label"] == "Everything that happened"
    assert sections["event_memory"]["summary"] == "97 events"
    assert sections["final_world_state"]["summary"] == "tick 10: 6 units, 2 active"
    assert sections["anti_gaming_report"]["summary"] == "1 flagged behaviour"
    assert sections["evaluation_result"]["raw"] is package["evaluation_result"]


# ── layering ─────────────────────────────────────────────────────────────────

ALLOWED = {
    "views": {"causal_chain", "replay", "timeline", "screens", "workspace"},
    "report": {"views", "briefing", "render"},
}


@pytest.mark.parametrize("package_name", list(ALLOWED))
def test_views_and_report_never_reach_the_simulation(package_name):
    for path in (SRC_PATH / "skyvault" / package_name).glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert (node.module or "") in ALLOWED[package_name], (path, node.module)
            elif isinstance(node, ast.ImportFrom | ast.Import):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    assert not name.startswith("skyvault"), (path, name)
