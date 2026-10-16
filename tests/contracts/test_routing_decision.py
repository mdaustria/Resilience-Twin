"""Verify the selected router has source-pinned, substantive comparison evidence."""

import hashlib
import json
from pathlib import Path

from packages.simulation.routing.reference import RoadEdge, RoadGraph, shortest_route
from scripts.benchmark_routing import _reference

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "release/routing"


def _load(name: str) -> dict[str, object]:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_reference_measurement_covers_fixed_reviewed_cases() -> None:
    artifact = _load("reference-benchmark.json")
    fixture = ROOT / "tests/fixtures/roads/reference-small.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    measurement = artifact["measurement"]
    assert isinstance(measurement, dict)
    assert measurement["fixture_sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert [case["id"] for case in measurement["cases"]] == [
        case["id"] for case in expected["cases"]
    ]
    fresh = _reference(2)
    assert [(case["id"], tuple(case["edge_ids"]), case["status"])
            for case in fresh["cases"]] == [
        (case["id"], tuple(case["edge_ids"]), case["status"])
        for case in measurement["cases"]
    ]


def test_candidate_measurement_is_pinned_and_not_a_decision() -> None:
    artifact = _load("valhalla-benchmark.json")
    measurement = artifact["measurement"]
    assert isinstance(measurement, dict)
    pbf = ROOT / measurement["fixture"]
    assert measurement["fixture_sha256"] == hashlib.sha256(pbf.read_bytes()).hexdigest()
    assert measurement["implementation"] == "pyvalhalla-3.9.1"
    assert measurement["route_reproducible"] is True
    assert measurement["iterations"] >= 20
    assert measurement["trace_edge_ids"]
    assert artifact["same_sample_comparison"] is False
    assert artifact["production_decision_eligible"] is False


def test_shared_osm_bridge_and_turn_comparison() -> None:
    graph_artifact = _load("utrecht-bridge-graph.json")
    pbf = REPORT / "utrecht_netherlands.osm.pbf"
    digest = hashlib.sha256(pbf.read_bytes()).hexdigest()
    assert graph_artifact["pbf_sha256"] == digest
    assert graph_artifact["reviewed_way_tags"]["7010992"]["bridge"] == "yes"
    assert graph_artifact["reviewed_way_tags"]["7010992"]["layer"] == "1"
    assert any(relation["id"] == 153969 and
               relation["tags"]["restriction"] == "only_straight_on"
               for relation in graph_artifact["restriction_relations_touching_ways"])

    reference = _load("bridge-reference-benchmark.json")
    candidate = _load("bridge-valhalla-benchmark.json")
    graph_hash = hashlib.sha256((REPORT / "utrecht-bridge-graph.json").read_bytes()).hexdigest()
    for artifact in (reference, candidate):
        assert artifact["same_sample_comparison"] is True
        assert artifact["measurement"]["pbf_sha256"] == digest
        assert artifact["measurement"]["graph_sha256"] == graph_hash
        assert all(case["iterations"] >= 20 for case in artifact["measurement"]["cases"])
    assert reference["measurement"]["node_count"] == 328
    assert reference["measurement"]["edge_count"] == 527
    for artifact in (reference, candidate):
        cases = {case["id"]: case for case in artifact["measurement"]["cases"]}
        assert set(cases) >= {
            "forward_open", "forward_closed", "reverse_open", "reverse_closed",
            "node_via_only",
        }
        assert 7010992 in cases["forward_open"]["way_ids"]
        assert 7010992 in cases["reverse_open"]["way_ids"]
        assert 7010992 not in cases["forward_closed"]["way_ids"]
        assert 7010992 not in cases["reverse_closed"]["way_ids"]
        assert cases["node_via_only"]["way_ids"][:2] == [310833905, 51978656]
        assert all(case["median_ns"] > 0 and case["p95_ns"] >= case["median_ns"]
                   for case in cases.values())
        assert artifact["measurement"]["peak_process_working_set_bytes"] > 0
    assert candidate["measurement"]["unsupported_cases"] == [
        "forward_edge_only_forward", "forward_edge_only_reverse",
    ]

    graph = RoadGraph(
        nodes=tuple(graph_artifact["nodes"]),
        edges=tuple(RoadEdge(**{**edge, "profiles": tuple(edge["profiles"])})
                    for edge in graph_artifact["edges"]),
    )
    closed = frozenset({"osm:7010992:0:forward"})
    forward = shortest_route(graph, "45150992", "45153531", "car", closed_edges=closed)
    reverse = shortest_route(graph, "45153531", "45150992", "car", closed_edges=closed)
    assert "osm:7010992:0:forward" not in forward.edge_ids
    assert "osm:7010992:0:reverse" in reverse.edge_ids


def test_adr_selects_exactly_one_runtime_router_and_links_measurements() -> None:
    decision = (REPORT / "ADR-028.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    essentials = (ROOT / "docs/architecture-essentials.md").read_text(encoding="utf-8")
    dependencies = (ROOT / "release/dependencies.md").read_text(encoding="utf-8")
    assert "Status: accepted" in decision
    assert "selects **one** production routing" in decision
    assert "standard-library exact-edge" in decision
    assert "Valhalla is an evaluation-only" in decision
    assert "ADR-028" in architecture and "ADR-028" in essentials
    assert "pyvalhalla==3.9.1" in dependencies
    for artifact in (
        "utrecht-bridge-graph.json", "bridge-reference-benchmark.json",
        "bridge-valhalla-benchmark.json",
    ):
        assert f"]({artifact})" in decision
        assert (REPORT / artifact).is_file()
