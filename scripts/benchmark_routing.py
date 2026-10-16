"""Measure the bounded reference router and an exploratory Valhalla route.

The two fixtures currently differ. Results are diagnostic and cannot support the
Task 2.4 production decision until a reviewed common OSM graph is available.
"""

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

from packages.simulation.routing.reference import (
    RoadEdge,
    RoadGraph,
    TurnRestriction,
    shortest_route,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/roads/reference-small.json"
UTRECHT = ROOT / "release/routing/utrecht_netherlands.osm.pbf"
BRIDGE_GRAPH = ROOT / "release/routing/utrecht-bridge-graph.json"
UTRECHT_LOCATIONS = ({"lat": 52.084, "lon": 5.11}, {"lat": 52.087, "lon": 5.115})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _peak_rss_bytes() -> int | None:
    if sys.platform == "win32":
        import ctypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        get_process_memory_info.restype = ctypes.c_bool
        if get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        ):
            return int(counters.peak_working_set_size)
        return None
    if sys.platform.startswith("linux"):
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    return None


def _latency(timings: list[int]) -> dict[str, int]:
    ordered = sorted(timings)
    return {
        "iterations": len(ordered),
        "median_ns": int(statistics.median(ordered)),
        "p95_ns": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def _reference(iterations: int) -> dict[str, Any]:
    fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    tracemalloc.start()
    for case in fixture["cases"]:
        rules = tuple(TurnRestriction(**fixture["restrictions"][rule_id])
                      for rule_id in case.get("restriction_ids", ()))
        graph = RoadGraph(
            nodes=tuple(fixture["nodes"]),
            edges=tuple(RoadEdge(**{**edge, "profiles": tuple(edge["profiles"])})
                        for edge in fixture["edges"]),
            restrictions=rules,
        )
        timings: list[int] = []
        observed: set[tuple[str, tuple[str, ...]]] = set()
        for _ in range(iterations):
            start = time.perf_counter_ns()
            result = shortest_route(
                graph, case["source"], case["target"], case["profile"],
                closed_edges=frozenset(case.get("closed_edges", ())),
                closed_assets=frozenset(case.get("closed_assets", ())),
            )
            timings.append(time.perf_counter_ns() - start)
            observed.add((result.status, result.edge_ids))
        expected = (case["status"], tuple(case["edge_ids"]))
        if observed != {expected}:
            raise AssertionError(f"reference case {case['id']} changed: {observed}")
        cases.append({"id": case["id"], "status": result.status,
                      "edge_ids": result.edge_ids, **_latency(timings)})
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "implementation": "stdlib-reference",
        "fixture": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"),
        "fixture_sha256": _digest(REFERENCE),
        "cases": cases,
        "peak_python_allocated_bytes": peak_python,
        "peak_process_working_set_bytes": _peak_rss_bytes(),
    }


def _valhalla(config: Path, iterations: int) -> dict[str, Any]:
    from valhalla import Actor

    if not config.is_file():
        raise FileNotFoundError(f"build Valhalla tiles and config first: {config}")
    actor = Actor(str(config))
    request = {"locations": list(UTRECHT_LOCATIONS), "costing": "auto"}
    tracemalloc.start()
    timings: list[int] = []
    signatures: set[str] = set()
    for _ in range(iterations):
        start = time.perf_counter_ns()
        result = actor.route(request)
        timings.append(time.perf_counter_ns() - start)
        signatures.add(json.dumps(result, sort_keys=True))
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    shape = result["trip"]["legs"][0]["shape"]
    trace = actor.trace_attributes({
        "encoded_polyline": shape, "costing": "auto", "shape_match": "map_snap",
        "filters": {"action": "include", "attributes": ["edge.id", "edge.way_id"]},
    })
    return {
        "implementation": "pyvalhalla-3.9.1",
        "fixture": str(UTRECHT.relative_to(ROOT)).replace("\\", "/"),
        "fixture_sha256": _digest(UTRECHT),
        "request": request,
        "route_reproducible": len(signatures) == 1,
        "reported_seconds": result["trip"]["summary"]["time"],
        "reported_km": result["trip"]["summary"]["length"],
        "trace_edge_ids": [edge["id"] for edge in trace["edges"]],
        "trace_way_ids": [edge["way_id"] for edge in trace["edges"]],
        **_latency(timings),
        "peak_python_allocated_bytes": peak_python,
        "peak_process_working_set_bytes": _peak_rss_bytes(),
    }


def _bridge_cases(bridge: dict[str, Any]) -> list[dict[str, Any]]:
    cases = [
        {"id": f"{direction}_{closure}", "source": source, "target": target,
         "closed": closure == "closed"}
        for direction, source, target in (
            ("forward", bridge["source_node"], bridge["target_node"]),
            ("reverse", bridge["target_node"], bridge["source_node"]),
        )
        for closure in ("open", "closed")
    ]
    cases.append({
        "id": "node_via_only", "source": "267976280", "target": "3163236364",
        "closed": False, "restriction": True,
    })
    cases.extend([
        {"id": "forward_edge_only_forward", "source": bridge["source_node"],
         "target": bridge["target_node"], "closed": False,
         "closed_edge": "osm:7010992:0:forward"},
        {"id": "forward_edge_only_reverse", "source": bridge["target_node"],
         "target": bridge["source_node"], "closed": False,
         "closed_edge": "osm:7010992:0:forward"},
    ])
    return cases


def _bridge_reference(iterations: int) -> dict[str, Any]:
    bridge = json.loads(BRIDGE_GRAPH.read_text(encoding="utf-8"))
    if bridge["pbf_sha256"] != _digest(UTRECHT):
        raise ValueError("bridge graph no longer matches pinned PBF")
    graph = RoadGraph(
        nodes=tuple(bridge["nodes"]),
        edges=tuple(RoadEdge(**{**edge, "profiles": tuple(edge["profiles"])})
                    for edge in bridge["edges"]),
    )
    if not any(relation["id"] == 153969 and relation["tags"].get("restriction")
               == "only_straight_on" for relation in bridge["restriction_relations_touching_ways"]):
        raise ValueError("reviewed turn relation 153969 is absent")
    turn_graph = RoadGraph(
        nodes=graph.nodes, edges=graph.edges,
        restrictions=(TurnRestriction(
            "osm:153969", "only", "osm:310833905:0:forward",
            "45150439", (), "osm:51978656:0:forward", "reviewed",
        ),),
    )
    tracemalloc.start()
    cases = []
    for case in _bridge_cases(bridge):
        timings: list[int] = []
        signatures: set[tuple[str, tuple[str, ...]]] = set()
        case_graph = turn_graph if case.get("restriction") else graph
        for _ in range(iterations):
            start = time.perf_counter_ns()
            route = shortest_route(
                case_graph, case["source"], case["target"], "car",
                closed_edges=frozenset([case["closed_edge"]]) if case.get("closed_edge")
                else frozenset(),
                closed_assets=frozenset([bridge["bridge_asset"]]) if case["closed"]
                else frozenset(),
            )
            timings.append(time.perf_counter_ns() - start)
            signatures.add((route.status, route.edge_ids))
        if len(signatures) != 1 or route.status != "found":
            raise AssertionError(f"unstable or missing bridge route: {case['id']}")
        way_ids = [int(edge_id.split(":")[1]) for edge_id in route.edge_ids]
        if (not case.get("restriction") and not case.get("closed_edge")
                and (7010992 in way_ids) == case["closed"]):
            raise AssertionError(f"bridge closure mismatch: {case['id']}")
        if case.get("restriction") and way_ids[:2] != [310833905, 51978656]:
            raise AssertionError("reviewed only-straight-on turn was not enforced")
        if case.get("closed_edge") and (
            (7010992 in way_ids) == (case["id"] == "forward_edge_only_forward")
        ):
            raise AssertionError("directed edge closure was not asymmetric")
        cases.append({
            "id": case["id"], "edge_ids": route.edge_ids, "way_ids": way_ids,
            "travel_seconds": route.travel_seconds, "distance_mm": route.distance_mm,
            **_latency(timings),
        })
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "implementation": "stdlib-reference-bounded-osm-probe",
        "pbf_sha256": _digest(UTRECHT),
        "graph_sha256": _digest(BRIDGE_GRAPH),
        "node_count": len(graph.nodes), "edge_count": len(graph.edges),
        "cases": cases,
        "peak_python_allocated_bytes": peak_python,
        "peak_process_working_set_bytes": _peak_rss_bytes(),
    }


def _bridge_valhalla(config: Path, iterations: int) -> dict[str, Any]:
    from valhalla import Actor

    bridge = json.loads(BRIDGE_GRAPH.read_text(encoding="utf-8"))
    if bridge["pbf_sha256"] != _digest(UTRECHT):
        raise ValueError("bridge graph no longer matches pinned PBF")
    coordinates = bridge["coordinates"]
    start, end = coordinates["45150992"], coordinates["45151845"]
    lat, lon = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
    radius = 0.00002
    polygon = [[lon-radius, lat-radius], [lon+radius, lat-radius],
               [lon+radius, lat+radius], [lon-radius, lat+radius],
               [lon-radius, lat-radius]]
    actor = Actor(str(config))
    tracemalloc.start()
    cases = []
    for case in _bridge_cases(bridge):
        if case.get("closed_edge"):
            continue
        source = coordinates[case["source"]]
        target = coordinates[case["target"]]
        request = {
            "locations": [{"lat": source[0], "lon": source[1]},
                          {"lat": target[0], "lon": target[1]}],
            "costing": "auto",
        }
        if case["closed"]:
            request["exclude_polygons"] = [polygon]
        timings: list[int] = []
        signatures: set[str] = set()
        for _ in range(iterations):
            start_time = time.perf_counter_ns()
            route = actor.route(request)
            timings.append(time.perf_counter_ns() - start_time)
            signatures.add(json.dumps(route, sort_keys=True))
        if len(signatures) != 1:
            raise AssertionError(f"Valhalla route changed: {case['id']}")
        trace = actor.trace_attributes({
            "encoded_polyline": route["trip"]["legs"][0]["shape"],
            "costing": "auto", "shape_match": "map_snap",
            "filters": {"action": "include", "attributes": ["edge.id", "edge.way_id"]},
        })
        way_ids = [edge["way_id"] for edge in trace["edges"]]
        if not case.get("restriction") and (7010992 in way_ids) == case["closed"]:
            raise AssertionError(f"bridge closure mismatch: {case['id']}")
        if case.get("restriction") and way_ids[:2] != [310833905, 51978656]:
            raise AssertionError("Valhalla did not follow reviewed turn relation 153969")
        cases.append({
            "id": case["id"], "request": request,
            "trace_edge_ids": [edge["id"] for edge in trace["edges"]],
            "way_ids": way_ids,
            "travel_seconds": route["trip"]["summary"]["time"],
            "distance_km": route["trip"]["summary"]["length"],
            **_latency(timings),
        })
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "implementation": "pyvalhalla-3.9.1-full-utrecht-tiles",
        "pbf_sha256": _digest(UTRECHT),
        "graph_sha256": _digest(BRIDGE_GRAPH),
        "closure_mechanism": "geometry polygon, not an exact edge-ID request",
        "unsupported_cases": [
            "forward_edge_only_forward", "forward_edge_only_reverse",
        ],
        "cases": cases,
        "peak_python_allocated_bytes": peak_python,
        "peak_process_working_set_bytes": _peak_rss_bytes(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("reference", "valhalla", "bridge-reference", "bridge-valhalla"),
        required=True,
    )
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations < 2:
        parser.error("at least two iterations are required")
    if args.mode in ("valhalla", "bridge-valhalla") and args.config is None:
        parser.error("--config is required for Valhalla")
    measurement = {
        "reference": lambda: _reference(args.iterations),
        "valhalla": lambda: _valhalla(args.config, args.iterations),
        "bridge-reference": lambda: _bridge_reference(args.iterations),
        "bridge-valhalla": lambda: _bridge_valhalla(args.config, args.iterations),
    }[args.mode]()
    common_source = args.mode.startswith("bridge-")
    payload = {
        "schema_version": "routing-benchmark.v1",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "same_sample_comparison": common_source,
        "same_compiled_graph": False,
        "production_decision_eligible": False,
        "measurement": measurement,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
