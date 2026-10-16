"""Compare exact paths with a hand-reviewed synthetic directed road sample."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from packages.simulation.routing import (
    RoadEdge,
    RoadGraph,
    TurnRestriction,
    shortest_route,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/roads/reference-small.json"
SAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))


def graph(*, restriction_ids=(), reverse=False):
    edges = tuple(RoadEdge(
        id=edge["id"], source=edge["source"], target=edge["target"],
        travel_seconds=edge["travel_seconds"], distance_mm=edge["distance_mm"],
        profiles=tuple(edge["profiles"]), asset_id=edge.get("asset_id"),
        boundary_cut=edge.get("boundary_cut", False),
    ) for edge in SAMPLE["edges"])
    restrictions = tuple(TurnRestriction(
        id=rule["id"], kind=rule["kind"], from_edge=rule["from_edge"],
        via_node=rule["via_node"], via_edges=tuple(rule["via_edges"]),
        to_edge=rule["to_edge"], review_state=rule["review_state"],
    ) for name in restriction_ids for rule in (SAMPLE["restrictions"][name],))
    if reverse:
        edges, restrictions = edges[::-1], restrictions[::-1]
    return RoadGraph(tuple(SAMPLE["nodes"]), edges, restrictions)


@pytest.mark.parametrize("case", SAMPLE["cases"], ids=lambda case: case["id"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fixture_order", "reversed_input"])
def test_hand_reviewed_exact_edge_paths(case, reverse):
    result = shortest_route(
        graph(restriction_ids=case.get("restriction_ids", ()), reverse=reverse),
        case["source"], case["target"], case["profile"],
        closed_edges=frozenset(case.get("closed_edges", ())),
        closed_assets=frozenset(case.get("closed_assets", ())),
    )
    assert result.status == case["status"]
    assert result.edge_ids == tuple(case["edge_ids"])
    assert result.travel_seconds == case["travel_seconds"]
    assert result.distance_mm == case["distance_mm"]
    assert result.boundary_edges == tuple(case.get("boundary_edges", ()))


def test_exact_edge_closure_preserves_other_bridge_edges():
    sample = graph()
    only_priority_closed = shortest_route(
        sample, "A", "F", "emergency", closed_edges=frozenset({"b-bridge-priority"}),
    )
    assert only_priority_closed.edge_ids == ("a-west", "b-bridge-local", "h-dest")
    assert shortest_route(sample, "E", "B", "car").edge_ids == ("c-bridge-west",)
    assert shortest_route(sample, "E", "B", "car", closed_assets=frozenset({"bridge-1"})).status == "unreachable"


def test_restriction_applies_only_to_its_incoming_edge_sequence():
    node = graph(restriction_ids=("node_no_north",))
    assert shortest_route(node, "B", "C", "car").edge_ids == ("d-north",)
    way = graph(restriction_ids=("way_no_north_exit",))
    result = shortest_route(way, "B", "F", "car", closed_assets=frozenset({"bridge-1"}))
    assert result.edge_ids == ("d-north", "e-north", "h-dest")


def test_zero_length_self_route_and_unknown_inputs():
    sample = graph()
    assert shortest_route(sample, "G", "G", "car").edge_ids == ()
    assert shortest_route(sample, "G", "G", "car").travel_seconds == 0
    with pytest.raises(ValueError, match="endpoint"):
        shortest_route(sample, "outside", "F", "car")
    with pytest.raises(ValueError, match="profile"):
        shortest_route(sample, "A", "F", "walking")
    with pytest.raises(ValueError, match="unknown exact edge or asset"):
        shortest_route(sample, "A", "F", "car", closed_edges=frozenset({"not-an-edge"}))
    with pytest.raises(ValueError, match="unknown exact edge or asset"):
        shortest_route(sample, "A", "F", "car", closed_assets=frozenset({"different-bridge"}))


@pytest.mark.parametrize("field,value,message", [
    ("travel_seconds", 0, "travel seconds"),
    ("travel_seconds", True, "travel seconds"),
    ("travel_seconds", 1.5, "travel seconds"),
    ("distance_mm", -1, "distance"),
    ("profiles", (), "profiles"),
    ("boundary_cut", 1, "explicit boolean"),
])
def test_invalid_edge_inputs_fail_before_routing(field, value, message):
    with pytest.raises(ValueError, match=message):
        replace(graph().edges[0], **{field: value})


def test_duplicate_ids_disconnected_restrictions_and_unknown_nodes_are_rejected():
    sample = graph()
    with pytest.raises(ValueError, match="duplicate edge"):
        RoadGraph(sample.nodes, (*sample.edges, sample.edges[0]))
    with pytest.raises(ValueError, match="unknown graph node"):
        RoadGraph(sample.nodes, (replace(sample.edges[0], target="outside"), *sample.edges[1:]))
    bad = replace(graph(restriction_ids=("way_no_north_exit",)).restrictions[0],
                  via_edges=("f-south", "e-north"))
    with pytest.raises(ValueError, match="not contiguous"):
        RoadGraph(sample.nodes, sample.edges, (bad,))
    bad = replace(graph(restriction_ids=("node_no_north",)).restrictions[0],
                  to_edge="missing")
    with pytest.raises(ValueError, match="unknown exit edge"):
        RoadGraph(sample.nodes, sample.edges, (bad,))


def test_unsupported_node_target_blocks_all_affected_exits():
    sample = graph(restriction_ids=("node_conditional",))
    assert shortest_route(sample, "A", "F", "car").status == "unreachable"
    # Starting at B avoids the affected incoming turn and remains routable.
    assert shortest_route(sample, "B", "F", "car").status == "found"
