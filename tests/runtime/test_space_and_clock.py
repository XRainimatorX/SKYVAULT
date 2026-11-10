import itertools
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.runtime import (
    EventDrivenClock,
    GraphSpace,
    GridSpace,
    NetworkSpace,
    PhaseClock,
    TickClock,
    build_clock,
    build_space,
)


def phase4_distance(model: str, a: tuple, b: tuple) -> int:
    """The distance formula SpaceModel used before Phase 2, kept as the reference."""
    ax, ay = a
    bx, by = b
    if model == "manhattan":
        return abs(ax - bx) + abs(ay - by)
    if model == "euclidean_floor":
        return int(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)
    return max(abs(ax - bx), abs(ay - by))


# ── grid: identical to the space the tactical reference always used ─────────


@pytest.mark.parametrize("model", ["chebyshev", "manhattan", "euclidean_floor"])
def test_grid_distance_matches_the_phase_4_space_at_every_pair(model):
    grid = GridSpace(10, 10, model)
    cells = list(itertools.product(range(10), range(10)))

    for a in cells:
        for b in cells:
            assert grid.distance(a, b) == phase4_distance(model, a, b)


def test_grid_is_inside_matches_its_bounds():
    grid = GridSpace(10, 6)

    assert grid.is_inside((0, 0))
    assert grid.is_inside((9, 5))
    assert not grid.is_inside((10, 0))
    assert not grid.is_inside((0, 6))
    assert not grid.is_inside((-1, 3))


def test_grid_neighbors_follow_the_distance_model():
    assert len(GridSpace(5, 5, "chebyshev").neighbors((2, 2))) == 8
    assert GridSpace(5, 5, "manhattan").neighbors((2, 2)) == [
        (1, 2),
        (2, 1),
        (2, 3),
        (3, 2),
    ]
    assert GridSpace(5, 5).neighbors((0, 0)) == [(0, 1), (1, 0), (1, 1)]


def test_grid_rejects_an_unknown_distance_model():
    with pytest.raises(ValueError):
        GridSpace(5, 5, "taxicab")


# ── graph and network ────────────────────────────────────────────────────────


def road_graph() -> GraphSpace:
    return GraphSpace(
        ["A", "B", "C", "D", "E", "F"],
        [["A", "B"], ["B", "C"], ["C", "D"], ["A", "E"]],
    )


def test_graph_distance_counts_links():
    graph = road_graph()

    assert graph.distance("A", "A") == 0
    assert graph.distance("A", "D") == 3
    assert graph.distance("E", "C") == 3


def test_disconnected_places_are_infinitely_far_apart():
    assert road_graph().distance("A", "F") == math.inf


def test_graph_neighbors_and_membership():
    graph = road_graph()

    assert graph.neighbors("A") == ["B", "E"]
    assert graph.neighbors("F") == []
    assert graph.is_inside("C")
    assert not graph.is_inside("Z")
    assert not graph.is_inside((0, 0))


def test_network_distance_is_the_cheapest_total_weight():
    network = NetworkSpace(
        ["depot", "north", "city"],
        [["depot", "north", 4], ["north", "city", 3], ["depot", "city", 10]],
    )

    assert network.distance("depot", "city") == 7
    assert network.neighbors("depot") == ["city", "north"]


def test_build_space_reads_each_space_type_and_describes_it_back():
    grid = {"type": "grid", "width": 4, "height": 3, "distance_model": "manhattan"}
    graph = {"type": "graph", "nodes": ["A", "B"], "edges": [["A", "B"]]}
    network = {"type": "network", "nodes": ["A", "B"], "edges": [["A", "B", 2]]}

    assert isinstance(build_space(grid), GridSpace)
    assert type(build_space(graph)) is GraphSpace
    assert isinstance(build_space(network), NetworkSpace)

    for model in (grid, graph, network):
        assert build_space(model).describe() == model


def test_build_space_defaults_a_grid_to_chebyshev():
    space = build_space({"type": "grid", "width": 3, "height": 3})

    assert space.describe()["distance_model"] == "chebyshev"


def test_build_space_rejects_an_unknown_type():
    with pytest.raises(ValueError):
        build_space({"type": "hexgrid"})


# ── clocks ───────────────────────────────────────────────────────────────────


def test_tick_clock_advances_one_step_at_a_time():
    clock = TickClock()

    assert [clock.advance() for _ in range(3)] == [1, 2, 3]
    assert clock.now == 3


def test_phase_clock_advances_by_phase_length():
    clock = PhaseClock(6, "hours")

    assert [clock.advance() for _ in range(3)] == [6, 12, 18]
    assert clock.phase == 3
    assert clock.describe() == {
        "type": "phase",
        "phase_length": 6,
        "time_unit": "hours",
    }


def test_phase_clock_needs_a_positive_length():
    with pytest.raises(ValueError):
        PhaseClock(0)


def test_event_driven_clock_jumps_to_the_next_scheduled_moment():
    clock = EventDrivenClock()
    clock.schedule(40, "convoy arrives")
    clock.schedule(5, "storm starts")
    clock.schedule(5, "radio fails")

    assert clock.advance() == 5
    assert clock.due() == ["storm starts", "radio fails"]
    assert clock.advance() == 40
    assert clock.due() == ["convoy arrives"]
    assert clock.pending == 0


def test_event_driven_clock_refuses_to_schedule_into_the_past():
    clock = EventDrivenClock()
    clock.schedule(10, "x")
    clock.advance()

    with pytest.raises(ValueError):
        clock.schedule(3, "too late")


def test_event_driven_clock_with_nothing_scheduled_cannot_advance():
    with pytest.raises(LookupError):
        EventDrivenClock().advance()


def test_build_clock_reads_each_time_type():
    assert isinstance(build_clock({"type": "tick"}), TickClock)
    assert isinstance(build_clock({"type": "phase", "phase_length": 6}), PhaseClock)
    assert isinstance(build_clock({"type": "event_driven"}), EventDrivenClock)

    with pytest.raises(ValueError):
        build_clock({"type": "phase_event_hybrid"})
