"""Space = where things can be, and how far apart they are."""

import math
from typing import Any, Protocol

import networkx as nx

DISTANCE_MODELS = ("chebyshev", "manhattan", "euclidean_floor")


class Space(Protocol):
    """
    What every space offers the rest of the runtime.

    Important:
    A location is whatever the space uses: an (x, y) cell on a grid, a node id
    on a graph or network. Callers never inspect it, they only hand it back to
    the space, so the engine does not care which kind of space it runs on.
    """

    def is_inside(self, position: Any) -> bool: ...

    def distance(self, a: Any, b: Any) -> float: ...

    def neighbors(self, position: Any) -> list[Any]: ...

    def describe(self) -> dict[str, Any]: ...


class GridSpace:
    """
    A width x height grid of integer cells.

    Important:
    This is the space the tactical reference has always used, moved here
    unchanged. Movement and attack range are both measured with distance(), so
    changing distance_model changes both at once.
    """

    def __init__(self, width: int, height: int, distance_model: str = "chebyshev"):
        if distance_model not in DISTANCE_MODELS:
            raise ValueError(f"unknown distance_model {distance_model!r}")
        self.width = width
        self.height = height
        self.distance_model = distance_model

    def is_inside(self, position: Any) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height

    def distance(self, a: Any, b: Any) -> int:
        ax, ay = a
        bx, by = b

        if self.distance_model == "manhattan":
            return abs(ax - bx) + abs(ay - by)

        if self.distance_model == "euclidean_floor":
            return int(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)

        return max(abs(ax - bx), abs(ay - by))

    def neighbors(self, position: Any) -> list[tuple[int, int]]:
        """
        Cells one step away under this grid's distance_model.

        Important:
        Manhattan grids move in four directions; the other models allow
        diagonals, because a diagonal step costs 1 under them too.
        """
        x, y = position
        steps = [
            (dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)
        ]

        if self.distance_model == "manhattan":
            steps = [(dx, dy) for dx, dy in steps if dx == 0 or dy == 0]

        cells = [(x + dx, y + dy) for dx, dy in steps]
        return sorted(cell for cell in cells if self.is_inside(cell))

    def describe(self) -> dict[str, Any]:
        return {
            "type": "grid",
            "width": self.width,
            "height": self.height,
            "distance_model": self.distance_model,
        }


class GraphSpace:
    """
    Named places joined by unweighted links: a road map, a set of districts.

    Important:
    Distance is the fewest links between two places. Two places with no route
    between them are infinitely far apart, not an error — a cut road is a
    situation the world has to be able to express.
    """

    kind = "graph"

    def __init__(self, nodes: list[str], edges: list[list[Any]]):
        self.nodes = list(nodes)
        self.edges = [list(edge) for edge in edges]
        self.graph: nx.Graph[str] = nx.Graph()
        self.graph.add_nodes_from(self.nodes)
        self._add_edges()

    def _add_edges(self) -> None:
        for u, v, *_ in self.edges:
            self.graph.add_edge(u, v)

    def _weight(self) -> str | None:
        return None

    def is_inside(self, position: Any) -> bool:
        return isinstance(position, str) and position in self.graph

    def distance(self, a: Any, b: Any) -> float:
        try:
            return float(
                nx.shortest_path_length(self.graph, a, b, weight=self._weight())
            )
        except nx.NetworkXNoPath:
            return math.inf

    def neighbors(self, position: Any) -> list[str]:
        return sorted(self.graph.neighbors(position))

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "nodes": list(self.nodes),
            "edges": [list(e) for e in self.edges],
        }


class NetworkSpace(GraphSpace):
    """
    Named places joined by weighted links: a supply network, a power grid.

    Important:
    Distance is the cheapest total weight between two places, not the fewest
    links. Depot → city direct at cost 10 loses to depot → north → city at 4 + 3.
    """

    kind = "network"

    def _add_edges(self) -> None:
        for u, v, weight in self.edges:
            self.graph.add_edge(u, v, weight=weight)

    def _weight(self) -> str | None:
        return "weight"


def build_space(space_model: dict[str, Any]) -> Space:
    """The space a world contract's space_model describes."""
    kind = space_model["type"]

    if kind == "grid":
        return GridSpace(
            width=int(space_model["width"]),
            height=int(space_model["height"]),
            distance_model=space_model.get("distance_model") or "chebyshev",
        )

    if kind == "graph":
        return GraphSpace(space_model["nodes"], space_model["edges"])

    if kind == "network":
        return NetworkSpace(space_model["nodes"], space_model["edges"])

    raise ValueError(f"unknown space_model type {kind!r}")
