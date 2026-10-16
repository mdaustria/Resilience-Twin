"""Small pinned OSM compilation and conservative routing checks."""

import json
from pathlib import Path

from packages.adapters.geo.compiler import CompilePolicy, compile_small_import
from packages.simulation.routing.reference import shortest_route

ROOT = Path(__file__).resolve().parents[2]


def _sample() -> dict:
    return json.loads((ROOT / "release/validation/geography/utrecht-small.json").read_text())


def _talayan_sample() -> dict:
    return json.loads((ROOT / "release/validation/geography/talayan-small.json").read_text())


def test_compilation_is_deterministic_and_keeps_exact_bridge_directions() -> None:
    sample = _sample()
    graph, record = compile_small_import(sample, CompilePolicy(30))
    again, again_record = compile_small_import(sample, CompilePolicy(30))
    assert (graph, record) == (again, again_record)
    assert record.source_sha256 == sample["source_sha256"]
    bridge = [edge for edge in graph.edges if edge.id.startswith("osm:7010992:")]
    assert {edge.id for edge in bridge} == {
        "osm:7010992:0:forward", "osm:7010992:0:reverse"}
    assert {edge.asset_id for edge in bridge} == {"osm:bridge-way:7010992"}
    assert record.boundary_edge_ids


def test_reviewed_bridge_pair_and_closure() -> None:
    graph, _ = compile_small_import(_sample(), CompilePolicy(30))
    bridge = next(edge for edge in graph.edges if edge.id == "osm:7010992:0:forward")
    reverse = next(edge for edge in graph.edges if edge.id == "osm:7010992:0:reverse")
    far = next(edge for edge in graph.edges if edge.id == "osm:7010987:0:forward")
    benchmark = json.loads((ROOT / "release/routing/bridge-reference-benchmark.json").read_text())
    cases = {case["id"]: case for case in benchmark["measurement"]["cases"]}
    for case_id, source, target, closed in (
        ("forward_open", bridge.source, far.target, False),
        ("forward_closed", bridge.source, far.target, True),
        ("reverse_open", far.target, bridge.source, False),
    ):
        result = shortest_route(graph, source, target, "car",
                                closed_assets=frozenset({bridge.asset_id}) if closed else frozenset())
        assert result.edge_ids == tuple(cases[case_id]["edge_ids"])
        assert (result.travel_seconds, result.distance_mm) == (
            cases[case_id]["travel_seconds"], cases[case_id]["distance_mm"])
    assert shortest_route(graph, bridge.source, bridge.target, "car").edge_ids == (bridge.id,)
    assert shortest_route(graph, reverse.source, reverse.target, "car").edge_ids == (reverse.id,)
    for edge in (bridge, reverse):
        closed = shortest_route(graph, edge.source, edge.target, "car",
                                closed_assets=frozenset({"osm:bridge-way:7010992"}))
        assert edge.id not in closed.edge_ids


def test_corrected_car_reference_excludes_psv_only_shortcut() -> None:
    sample = _sample()
    assert sample["ways"]["7011033"]["tags"]["access"] == "no"
    assert sample["ways"]["7011033"]["tags"]["psv"] == "yes"
    graph, _ = compile_small_import(sample, CompilePolicy(30))
    assert not any(edge.id.startswith("osm:7011033:") for edge in graph.edges)
    reviewed = json.loads((ROOT / "release/validation/geography/utrecht-compiled-review.json").read_text())
    for case in reviewed["cases"].values():
        route = shortest_route(
            graph, case["source"], case["target"], "car",
            closed_assets=frozenset({case["closed_asset"]}) if case["closed_asset"] else frozenset(),
        )
        assert (route.status, route.travel_seconds, route.distance_mm, route.edge_ids) == (
            case["status"], case["travel_seconds"], case["distance_mm"], tuple(case["edge_ids"]))
    assert reviewed["cases"]["reverse_closed"]["travel_seconds"] == 135


def test_philippine_graph_compiles_deterministically_with_exact_bridge_assets() -> None:
    sample = _talayan_sample()
    graph, record = compile_small_import(sample, CompilePolicy(30))
    again, again_record = compile_small_import(sample, CompilePolicy(30))
    reviewed = json.loads((ROOT / "release/validation/geography/talayan-compiled-review.json").read_text())
    assert (graph, record) == (again, again_record)
    assert (len(graph.nodes), len(graph.edges), len(graph.restrictions), len(record.boundary_edge_ids)) == (
        reviewed["nodes"], reviewed["edges"], reviewed["restrictions"], reviewed["boundary_edges"])
    assert record.source_sha256 == sample["source_sha256"]
    assert any(issue.reason.startswith("unknown speed") for issue in record.issues)
    assert any(issue.reason.startswith("unsupported relation") for issue in record.issues)
    assert any("layer tags" in issue.reason for issue in record.issues)
    for edge in graph.edges:
        way = sample["ways"][edge.id.split(":")[1]]
        if way["tags"].get("bridge") not in (None, "no"):
            assert edge.asset_id == f"osm:bridge-way:{edge.id.split(':')[1]}"
    assert all(edge.id in record.boundary_edge_ids for edge in graph.edges if edge.boundary_cut)
    bridge = next(edge for edge in graph.edges if edge.asset_id is not None
                  and not edge.boundary_cut)
    closed = shortest_route(graph, bridge.source, bridge.target, "car",
                            closed_assets=frozenset({bridge.asset_id}))
    assert not any(edge_id in closed.edge_ids for edge_id in
                   (candidate.id for candidate in graph.edges
                    if candidate.asset_id == bridge.asset_id))


def test_ambiguous_relation_blocks_entry_exits() -> None:
    sample = _sample()
    sample["restriction_relations"] = [{
        "id": 990001,
        "members": [
            {"id": 7010992, "role": "from", "type": "way"},
            {"id": 7010987, "role": "via", "type": "way"},
            {"id": 7010981, "role": "to", "type": "way"},
        ],
        "tags": {"type": "restriction", "restriction": "no_right_turn"},
    }]
    graph, record = compile_small_import(sample, CompilePolicy(30))
    assert any(issue.source_id == "relation:990001" for issue in record.issues)
    assert any(rule.id.startswith("osm:relation:990001:")
               and rule.review_state == "ambiguous" for rule in graph.restrictions)


def test_conditional_turn_is_never_treated_as_unconditional_reviewed_access() -> None:
    sample = _sample()
    relation = next(value for value in sample["restriction_relations"]
                    if value["tags"].get("restriction", "").startswith(("no_", "only_")))
    relation["tags"]["restriction:conditional"] = "no_left_turn @ (Mo-Fr 07:00-09:00)"
    graph, record = compile_small_import(sample, CompilePolicy(30))
    assert any(issue.source_id == f"relation:{relation['id']}" and "ambiguous" in issue.reason
               for issue in record.issues)
    assert any(rule.id.startswith(f"osm:relation:{relation['id']}:")
               and rule.review_state == "ambiguous" for rule in graph.restrictions)
