"""Conservative compiler from the pinned small OSM import to ADR-028 edges.

Only an explicitly reviewed car policy is represented. Unknown access and turn
semantics are recorded or excluded; this is not a regional OSM rules engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import asin, ceil, cos, radians, sin, sqrt
from typing import Any, Literal

from packages.contracts.graphs import CompiledGraphRecord, GraphIssue
from packages.simulation.routing.reference import (
    RoadEdge,
    RoadGraph,
    RouteResult,
    TurnRestriction,
    shortest_route,
)

CAR_ROADS = frozenset({"motorway", "trunk", "primary", "secondary", "tertiary",
                       "unclassified", "residential", "service", "living_street",
                       "motorway_link", "trunk_link", "primary_link", "secondary_link",
                       "tertiary_link"})


@dataclass(frozen=True, slots=True)
class CompilePolicy:
    speed_fallback_kph: int
    reviewed_bridge_assets: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.speed_fallback_kph <= 130:
            raise ValueError("explicit fallback speed must be 1–130 km/h")
        all_ways = [way for _, ways in self.reviewed_bridge_assets for way in ways]
        if len(all_ways) != len(set(all_ways)):
            raise ValueError("bridge way belongs to multiple reviewed assets")


def _distance_mm(a: list[float], b: list[float]) -> int:
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return max(1, round(12_742_000_000 * asin(sqrt(value))))


def _speed(tags: dict[str, str], fallback: int) -> tuple[int, bool]:
    raw = tags.get("maxspeed", "")
    if raw.isdecimal() and 1 <= int(raw) <= 130:
        return int(raw), False
    return fallback, True


def _allowed(tags: dict[str, str]) -> bool:
    if tags.get("highway") not in CAR_ROADS:
        return False
    if any(tags.get(key) in {"no", "private", "destination", "delivery", "agricultural",
                             "forestry"} for key in ("access", "vehicle", "motor_vehicle", "motorcar")):
        return False
    # Construction, conditional access and unreviewed directional access are excluded.
    return not any("conditional" in key or "forward" in key or "backward" in key
                   for key in tags if key.startswith(("access", "vehicle", "motorcar")))


def compile_small_import(data: dict[str, Any], policy: CompilePolicy) -> tuple[RoadGraph, CompiledGraphRecord]:
    """Compile selected OSM segments; retain source identities and unresolved issues."""
    if data.get("schema_version") != "osm-small-import.v1" or not data.get("source_sha256"):
        raise ValueError("expected the pinned small-import artifact")
    nodes: dict[str, list[float]] = data["nodes"]
    cuts = {(str(c["way_id"]), c["segment_index"]) for c in data["boundary_cuts"]}
    south, north, west, east = data["buffered_bounds_lat_lon"]

    def inside(node_id: int) -> bool:
        latitude, longitude = nodes[str(node_id)]
        return bool(south <= latitude <= north and west <= longitude <= east)

    bridge_assets = {str(way): asset for asset, ways in policy.reviewed_bridge_assets for way in ways}
    edges: list[RoadEdge] = []
    issues: list[GraphIssue] = []
    for way_id, way in sorted(data["ways"].items(), key=lambda item: int(item[0])):
        tags: dict[str, str] = way["tags"]
        if not _allowed(tags):
            continue
        if tags.get("junction") == "roundabout" or tags.get("oneway") == "yes":
            directions: tuple[str, ...] = ("forward",)
        elif tags.get("oneway") == "-1":
            directions = ("reverse",)
        elif tags.get("oneway", "no") == "no":
            directions = ("forward", "reverse")
        else:
            issues.append(GraphIssue(f"way:{way_id}", "unsupported oneway value; excluded"))
            continue
        speed, assumed = _speed(tags, policy.speed_fallback_kph)
        if assumed:
            issues.append(GraphIssue(f"way:{way_id}", "unknown speed; explicit fallback used"))
        if tags.get("bridge") not in (None, "no"):
            asset = bridge_assets.get(way_id, f"osm:bridge-way:{way_id}")
        else:
            asset = None
        refs: list[int] = way["node_ids"]
        for index, (left, right) in enumerate(pairwise(refs)):
            if str(left) not in nodes or str(right) not in nodes:
                raise ValueError("selected way has a missing node")
            distance = _distance_mm(nodes[str(left)], nodes[str(right)])
            seconds = max(1, ceil(distance * 3600 / (speed * 1_000_000)))
            for direction in directions:
                source, target = (left, right) if direction == "forward" else (right, left)
                edges.append(RoadEdge(f"osm:{way_id}:{index}:{direction}", str(source),
                                      str(target), seconds, distance, ("car",), asset,
                                      (way_id, index) in cuts or not (inside(left) and inside(right))))
    by_way: dict[str, list[RoadEdge]] = {}
    node_layers: dict[str, set[str]] = {}
    for edge in edges:
        way_key = edge.id.split(":")[1]
        by_way.setdefault(way_key, []).append(edge)
        layer = data["ways"][way_key]["tags"].get("layer", "0")
        node_layers.setdefault(edge.source, set()).add(layer)
        node_layers.setdefault(edge.target, set()).add(layer)
    for node, layers in sorted(node_layers.items(), key=lambda item: int(item[0])):
        if len(layers) > 1:
            issues.append(GraphIssue(f"node:{node}", "shared road node spans layer tags; connector review required"))
    restrictions: list[TurnRestriction] = []
    for relation in data["restriction_relations"]:
        relation_id = relation["id"]
        members = relation["members"]
        from_ids = [str(m["id"]) for m in members if m["role"] == "from" and m["type"] == "way"]
        to_ids = [str(m["id"]) for m in members if m["role"] == "to" and m["type"] == "way"]
        via_nodes = [str(m["id"]) for m in members if m["role"] == "via" and m["type"] == "node"]
        if len(from_ids) != 1 or len(to_ids) != 1 or len(via_nodes) != 1:
            # For a way-via/unknown relation, exclude every turn leaving the
            # compiled entry way rather than treating the relation as absent.
            for from_id in from_ids:
                for entry in by_way.get(from_id, ()):
                    restrictions.append(TurnRestriction(
                        f"osm:relation:{relation_id}:{entry.id}", "unsupported",
                        entry.id, entry.target, (), None, "ambiguous"))
            issues.append(GraphIssue(f"relation:{relation_id}", "unsupported relation form; entry exits blocked"))
            continue
        via = via_nodes[0]
        incoming = [e for e in by_way.get(from_ids[0], ()) if e.target == via]
        outgoing = [e for e in by_way.get(to_ids[0], ()) if e.source == via]
        if not incoming:
            issues.append(GraphIssue(f"relation:{relation_id}", "incoming edge outside compiled graph"))
            continue
        tag = relation["tags"].get("restriction", "")
        kind: Literal["no", "only", "unsupported"] = (
            "only" if tag.startswith("only_") else
            "no" if tag.startswith("no_") else "unsupported")
        ambiguous = (len(outgoing) != 1 or kind == "unsupported"
                     or any("conditional" in key for key in relation["tags"]))
        for entry in sorted(incoming, key=lambda edge: edge.id):
            restrictions.append(TurnRestriction(f"osm:relation:{relation_id}:{entry.id}",
                                                "unsupported" if ambiguous else kind,
                                                entry.id, via, (),
                                                outgoing[0].id if len(outgoing) == 1 else None,
                                                "ambiguous" if ambiguous else "reviewed"))
        if ambiguous:
            issues.append(GraphIssue(f"relation:{relation_id}", "ambiguous turn; incoming exits blocked"))
    graph = RoadGraph(tuple(sorted({node for edge in edges for node in (edge.source, edge.target)})),
                      tuple(sorted(edges, key=lambda edge: edge.id)),
                      tuple(sorted(restrictions, key=lambda rule: rule.id)))
    record = CompiledGraphRecord(data["source_sha256"], "car", policy.speed_fallback_kph,
                                 "haversine rounded mm; ceiling seconds", len(edges),
                                 len(restrictions),
                                 tuple(sorted(e.id for e in edges if e.boundary_cut)),
                                 tuple(sorted(issues, key=lambda issue: (issue.source_id, issue.reason))))
    return graph, record


def route_compiled(graph: RoadGraph, start: str, end: str) -> RouteResult:
    """Expose a reviewed car route to the API without coupling it to the engine."""
    return shortest_route(graph, start, end, "car")


__all__ = ("CompilePolicy", "compile_small_import", "route_compiled")
