"""Small deterministic exact-edge router for reviewed, synthetic road samples.

This is a correctness reference. OSM compilation and production routing are gated by
Tasks 2.4 and 3.5–3.6; no geographic semantics are inferred from edge labels here.
"""

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import pairwise
from typing import Literal

MAX_INTEGER = 9_007_199_254_740_991


@dataclass(frozen=True, slots=True)
class RoadEdge:
    id: str
    source: str
    target: str
    travel_seconds: int
    distance_mm: int
    profiles: tuple[str, ...]
    asset_id: str | None = None
    boundary_cut: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.source or not self.target or not self.profiles:
            raise ValueError("edge IDs, endpoints and reviewed profiles are required")
        if self.source == self.target:
            raise ValueError("self-loop road edges are outside the reference sample")
        if (type(self.travel_seconds) is not int or not 0 < self.travel_seconds <= MAX_INTEGER
                or type(self.distance_mm) is not int or not 0 <= self.distance_mm <= MAX_INTEGER):
            raise ValueError("edge travel seconds must be positive and distance nonnegative integers")
        if (any(type(profile) is not str or not profile for profile in self.profiles)
                or len(set(self.profiles)) != len(self.profiles)):
            raise ValueError("edge profiles must be unique and nonempty")
        if type(self.boundary_cut) is not bool:
            raise ValueError("boundary cut must be an explicit boolean")


@dataclass(frozen=True, slots=True)
class TurnRestriction:
    """A node turn or contiguous way-via path; uncertain cases exclude affected entry."""

    id: str
    kind: Literal["no", "only", "unsupported"]
    from_edge: str
    via_node: str | None
    via_edges: tuple[str, ...]
    to_edge: str | None
    review_state: Literal["reviewed", "ambiguous", "conditional"]


@dataclass(frozen=True, slots=True)
class RouteResult:
    status: Literal["found", "unreachable", "boundary_cut"]
    edge_ids: tuple[str, ...]
    travel_seconds: int | None
    distance_mm: int | None
    boundary_edges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoadGraph:
    nodes: tuple[str, ...]
    edges: tuple[RoadEdge, ...]
    restrictions: tuple[TurnRestriction, ...] = ()

    def __post_init__(self) -> None:
        if not self.nodes or len(set(self.nodes)) != len(self.nodes) or any(not n for n in self.nodes):
            raise ValueError("graph requires unique, nonempty node IDs")
        by_id = {edge.id: edge for edge in self.edges}
        if len(by_id) != len(self.edges):
            raise ValueError("duplicate edge ID")
        if any(edge.source not in self.nodes or edge.target not in self.nodes for edge in self.edges):
            raise ValueError("road edge references unknown graph node")
        if len({rule.id for rule in self.restrictions}) != len(self.restrictions):
            raise ValueError("duplicate restriction ID")
        for rule in self.restrictions:
            if not rule.id or rule.from_edge not in by_id or rule.kind not in ("no", "only", "unsupported"):
                raise ValueError("invalid restriction ID, type or from-edge")
            if rule.review_state not in ("reviewed", "ambiguous", "conditional"):
                raise ValueError("invalid restriction review state")
            if rule.to_edge is not None and rule.to_edge not in by_id:
                raise ValueError("restriction references unknown exit edge")
            if any(edge_id not in by_id for edge_id in rule.via_edges):
                raise ValueError("restriction references unknown via edge")
            if (rule.via_node is None) == (not rule.via_edges):
                raise ValueError("restriction requires exactly one node-via or way-via form")
            if rule.via_node is not None:
                if by_id[rule.from_edge].target != rule.via_node:
                    raise ValueError("node-via restriction does not meet incoming edge")
                if rule.to_edge is not None and by_id[rule.to_edge].source != rule.via_node:
                    raise ValueError("node-via restriction exit is disconnected")
            else:
                chain = (rule.from_edge, *rule.via_edges)
                if any(by_id[left].target != by_id[right].source
                       for left, right in pairwise(chain)):
                    raise ValueError("way-via restriction edges are not contiguous")
                if rule.to_edge is not None and by_id[chain[-1]].target != by_id[rule.to_edge].source:
                    raise ValueError("way-via restriction exit is disconnected")
            if rule.review_state == "reviewed" and rule.kind != "unsupported" and rule.to_edge is None:
                raise ValueError("reviewed restriction requires a known exit edge")


def _ends_with(history: tuple[str, ...], suffix: tuple[str, ...]) -> bool:
    return len(history) >= len(suffix) and history[-len(suffix):] == suffix


def _restricted(
    graph: RoadGraph, history: tuple[str, ...], candidate: RoadEdge,
) -> bool:
    for rule in graph.restrictions:
        prefix = (rule.from_edge, *rule.via_edges)
        if rule.review_state != "reviewed" or rule.kind == "unsupported":
            # An unresolved/conditional relation is conservatively excluded at entry.
            # For unknown node-via targets, every exit from the incoming edge is blocked.
            if _ends_with(history, (rule.from_edge,)) and (
                not rule.via_edges or candidate.id == rule.via_edges[0]
            ):
                return True
            continue
        if rule.via_node is not None:
            if not _ends_with(history, (rule.from_edge,)):
                continue
            if rule.kind == "no" and candidate.id == rule.to_edge:
                return True
            if rule.kind == "only" and candidate.id != rule.to_edge:
                return True
            continue
        if rule.kind == "only":
            for position in range(1, len(prefix)):
                if _ends_with(history, prefix[:position]) and candidate.id != prefix[position]:
                    return True
        if _ends_with(history, prefix):
            if rule.kind == "no" and candidate.id == rule.to_edge:
                return True
            if rule.kind == "only" and candidate.id != rule.to_edge:
                return True
    return False


def _search(
    graph: RoadGraph, source: str, target: str, profile: str,
    closed_edges: frozenset[str], closed_assets: frozenset[str], *,
    allow_boundary: bool,
) -> RouteResult | None:
    adjacency: dict[str, list[RoadEdge]] = {node: [] for node in graph.nodes}
    for edge in graph.edges:
        adjacency[edge.source].append(edge)
    for outgoing in adjacency.values():
        outgoing.sort(key=lambda edge: edge.id)
    history_limit = max((1 + len(rule.via_edges) for rule in graph.restrictions), default=1)
    # (cost, exact edge path, node, bounded history, distance). Positive edge weights
    # mean the first target popped has the minimum time and stable lexical tie break.
    queue: list[tuple[int, tuple[str, ...], str, tuple[str, ...], int]] = [
        (0, (), source, (), 0),
    ]
    best: dict[tuple[str, tuple[str, ...]], tuple[int, tuple[str, ...]]] = {
        (source, ()): (0, ()),
    }
    while queue:
        cost, path, node, history, distance = heappop(queue)
        if best.get((node, history)) != (cost, path):
            continue
        if node == target:
            boundary_edges = tuple(sorted(edge.id for edge in graph.edges
                                          if edge.boundary_cut and edge.id in path))
            return RouteResult("found", path, cost, distance, boundary_edges)
        for edge in adjacency[node]:
            if (profile not in edge.profiles or edge.id in closed_edges
                    or (edge.asset_id is not None and edge.asset_id in closed_assets)
                    or (edge.boundary_cut and not allow_boundary)
                    or _restricted(graph, history, edge)):
                continue
            next_cost = cost + edge.travel_seconds
            next_distance = distance + edge.distance_mm
            if next_cost > MAX_INTEGER or next_distance > MAX_INTEGER:
                raise ValueError("route totals exceed the safe integer range")
            next_path = (*path, edge.id)
            next_history = (*history, edge.id)[-history_limit:]
            key = (edge.target, next_history)
            candidate = (next_cost, next_path)
            if key not in best or candidate < best[key]:
                best[key] = candidate
                heappush(queue, (next_cost, next_path, edge.target, next_history,
                                 next_distance))
    return None


def shortest_route(
    graph: RoadGraph, source: str, target: str, profile: str, *,
    closed_edges: frozenset[str] = frozenset(),
    closed_assets: frozenset[str] = frozenset(),
) -> RouteResult:
    """Find an exact directed edge path, or report a cut/unreachable result."""
    if source not in graph.nodes or target not in graph.nodes:
        raise ValueError("route endpoint is outside the reviewed graph")
    all_edges = {edge.id for edge in graph.edges}
    all_assets = {edge.asset_id for edge in graph.edges if edge.asset_id is not None}
    if not closed_edges <= all_edges or not closed_assets <= all_assets:
        raise ValueError("closure references an unknown exact edge or asset")
    if not profile or profile not in {p for edge in graph.edges for p in edge.profiles}:
        raise ValueError("routing profile is not reviewed in this graph")
    found = _search(graph, source, target, profile, closed_edges, closed_assets,
                    allow_boundary=False)
    if found is not None:
        return found
    if any(edge.boundary_cut for edge in graph.edges):
        through_cut = _search(graph, source, target, profile, closed_edges,
                              closed_assets, allow_boundary=True)
        if through_cut is not None and through_cut.boundary_edges:
            return RouteResult("boundary_cut", (), None, None, through_cut.boundary_edges)
    return RouteResult("unreachable", (), None, None)
