"""Inspect a pinned OSM PBF for Task 2.4 review; this is not an importer.

Only the small OSM PBF fields used to inspect selected ways and nodes are read.
Unknown fields are skipped. Do not use this probe to compile a production graph.
"""

import argparse
import hashlib
import json
import math
import struct
import zlib
from itertools import pairwise
from pathlib import Path


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            raise ValueError("oversized PBF varint")
    raise ValueError("truncated PBF varint")


def _fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    result: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 2:
            length, offset = _varint(data, offset)
            value = data[offset:offset + length]
            if len(value) != length:
                raise ValueError("truncated PBF field")
            offset += length
        elif wire == 1:
            offset += 8
            continue
        elif wire == 5:
            offset += 4
            continue
        else:
            raise ValueError(f"unsupported PBF wire type {wire}")
        result.append((number, wire, value))
    return result


def _packed(data: bytes) -> list[int]:
    values: list[int] = []
    offset = 0
    while offset < len(data):
        value, offset = _varint(data, offset)
        values.append(value)
    return values


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _field_values(fields: list[tuple[int, int, int | bytes]], number: int) -> list[int]:
    values: list[int] = []
    for field_number, wire, value in fields:
        if field_number == number:
            if wire == 2 and isinstance(value, bytes):
                values.extend(_packed(value))
            elif wire == 0 and isinstance(value, int):
                values.append(value)
    return values


def _blocks(path: Path):  # type: ignore[no-untyped-def]
    with path.open("rb") as stream:
        while size_bytes := stream.read(4):
            if len(size_bytes) != 4:
                raise ValueError("truncated PBF header size")
            header = stream.read(struct.unpack(">I", size_bytes)[0])
            header_fields = _fields(header)
            kind = next(value for number, _, value in header_fields if number == 1)
            size = next(value for number, _, value in header_fields if number == 3)
            if not isinstance(kind, bytes) or not isinstance(size, int):
                raise TypeError("invalid PBF block header")
            blob_fields = _fields(stream.read(size))
            raw = next((value for number, _, value in blob_fields if number == 1), None)
            zipped = next((value for number, _, value in blob_fields if number == 3), None)
            if isinstance(raw, bytes):
                payload = raw
            elif isinstance(zipped, bytes):
                payload = zlib.decompress(zipped)
            else:
                raise TypeError("unsupported PBF blob compression")
            yield kind.decode("ascii"), payload


def selected_ways(path: Path, wanted: set[int] | None) -> dict[int, dict[str, object]]:
    ways: dict[int, dict[str, object]] = {}
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        block_fields = _fields(block)
        strings_bytes = next(value for number, _, value in block_fields if number == 1)
        if not isinstance(strings_bytes, bytes):
            raise TypeError("invalid string table")
        strings = [value.decode("utf-8", "replace") for number, _, value
                   in _fields(strings_bytes) if number == 1 and isinstance(value, bytes)]
        for number, _, group in block_fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for group_number, _, way in _fields(group):
                if group_number != 3 or not isinstance(way, bytes):
                    continue
                fields = _fields(way)
                way_id = _field_values(fields, 1)[0]
                if wanted is not None and way_id not in wanted:
                    continue
                keys = _field_values(fields, 2)
                values = _field_values(fields, 3)
                refs: list[int] = []
                position = 0
                for delta in _field_values(fields, 8):
                    position += _zigzag(delta)
                    refs.append(position)
                ways[way_id] = {
                    "node_ids": refs,
                    "tags": {strings[key]: strings[value] for key, value in zip(keys, values)},
                }
    return ways


def selected_nodes(path: Path, wanted: set[int]) -> dict[int, tuple[float, float]]:
    nodes: dict[int, tuple[float, float]] = {}
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        block_fields = _fields(block)
        granularity = next((value for number, _, value in block_fields if number == 17), 100)
        lat_offset = next((value for number, _, value in block_fields if number == 19), 0)
        lon_offset = next((value for number, _, value in block_fields if number == 20), 0)
        if not all(isinstance(value, int) for value in (granularity, lat_offset, lon_offset)):
            raise ValueError("invalid PBF coordinate scale")
        for number, _, group in block_fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for group_number, _, dense in _fields(group):
                if group_number != 2 or not isinstance(dense, bytes):
                    continue
                fields = _fields(dense)
                ids = _field_values(fields, 1)
                lats = _field_values(fields, 8)
                lons = _field_values(fields, 9)
                if len(ids) != len(lats) or len(ids) != len(lons):
                    raise ValueError("dense-node coordinate mismatch")
                node_id = lat = lon = 0
                for id_delta, lat_delta, lon_delta in zip(ids, lats, lons):
                    node_id += _zigzag(id_delta)
                    lat += _zigzag(lat_delta)
                    lon += _zigzag(lon_delta)
                    if node_id in wanted:
                        nodes[node_id] = (
                            (lat_offset + granularity * lat) * 1e-9,
                            (lon_offset + granularity * lon) * 1e-9,
                        )
    return nodes


def selected_restrictions(path: Path, relevant_ways: set[int]) -> list[dict[str, object]]:
    """List OSM turn relations touching the probe's way set; no semantics compiled."""
    relations: list[dict[str, object]] = []
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        block_fields = _fields(block)
        strings_bytes = next(value for number, _, value in block_fields if number == 1)
        if not isinstance(strings_bytes, bytes):
            raise TypeError("invalid string table")
        strings = [value.decode("utf-8", "replace") for number, _, value
                   in _fields(strings_bytes) if number == 1 and isinstance(value, bytes)]
        for number, _, group in block_fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for group_number, _, relation in _fields(group):
                if group_number != 4 or not isinstance(relation, bytes):
                    continue
                fields = _fields(relation)
                keys = _field_values(fields, 2)
                values = _field_values(fields, 3)
                tags = {strings[key]: strings[value] for key, value in zip(keys, values)}
                if tags.get("type") != "restriction":
                    continue
                members = []
                member_id = 0
                for role, delta, member_type in zip(
                    _field_values(fields, 8), _field_values(fields, 9),
                    _field_values(fields, 10),
                ):
                    member_id += _zigzag(delta)
                    members.append({"role": strings[role], "id": member_id,
                                    "type": ("node", "way", "relation")[member_type]})
                if any(member["type"] == "way" and member["id"] in relevant_ways
                       for member in members):
                    relations.append({
                        "id": _field_values(fields, 1)[0],
                        "tags": tags,
                        "members": members,
                    })
    return relations


BRIDGE_BBOX = (52.0773, 52.0815, 5.1195, 5.1277)
CAR_HIGHWAYS = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road",
})


def _inside(point: tuple[float, float]) -> bool:
    lat, lon = point
    return BRIDGE_BBOX[0] <= lat <= BRIDGE_BBOX[1] and BRIDGE_BBOX[2] <= lon <= BRIDGE_BBOX[3]


def _distance_mm(a: tuple[float, float], b: tuple[float, float]) -> int:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    great_circle = 2 * math.asin(math.sqrt(
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    ))
    return max(1, round(6_371_000 * great_circle * 1000))


def bridge_graph(path: Path) -> dict[str, object]:
    """Create a review-only car graph near bridge 7010992 from OSM way tags."""
    ways = selected_ways(path, None)
    highways = {way_id: way for way_id, way in ways.items()
                if way["tags"].get("highway") in CAR_HIGHWAYS}
    nodes = selected_nodes(path, {
        node_id for way in highways.values() for node_id in way["node_ids"]
    })
    edges: list[dict[str, object]] = []
    included_ways: dict[int, dict[str, object]] = {}
    unresolved_segments = 0
    for way_id, way in sorted(highways.items()):
        refs = way["node_ids"]
        if not any(node_id in nodes and _inside(nodes[node_id]) for node_id in refs):
            continue
        included_ways[way_id] = way
        tags = way["tags"]
        maxspeed = tags.get("maxspeed", "30")
        speed_kmh = int(maxspeed) if str(maxspeed).isdigit() else 30
        directions = ("reverse",) if tags.get("oneway") == "-1" else (
            ("forward",) if tags.get("oneway") in ("yes", "1", "true")
            else ("forward", "reverse")
        )
        for position, (source, target) in enumerate(pairwise(refs)):
            if source not in nodes or target not in nodes:
                unresolved_segments += 1
                continue
            source_inside = _inside(nodes[source])
            target_inside = _inside(nodes[target])
            if not (source_inside or target_inside):
                continue
            length = _distance_mm(nodes[source], nodes[target])
            seconds = max(1, math.ceil(length * 3600 / (speed_kmh * 1_000_000)))
            for direction in directions:
                start, end = ((source, target) if direction == "forward"
                              else (target, source))
                edges.append({
                    "id": f"osm:{way_id}:{position}:{direction}",
                    "source": str(start), "target": str(end),
                    "travel_seconds": seconds, "distance_mm": length,
                    "profiles": ["car"],
                    "asset_id": f"bridge-way:{way_id}" if tags.get("bridge") else None,
                    "boundary_cut": not (source_inside and target_inside),
                })
    included_nodes = sorted({
        node for edge in edges for node in (edge["source"], edge["target"])
    })
    return {
        "schema_version": "routing-osm-probe.v1",
        "pbf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bbox_lat_lon": BRIDGE_BBOX,
        "source_node": "45150992",
        "target_node": "45153531",
        "bridge_asset": "bridge-way:7010992",
        "assumptions": [
            "Only enumerated car highway tags are included; access rules and turn relations are not compiled.",
            "Tagged numeric maxspeed is used; missing/nonnumeric speed assumes 30 km/h.",
            "Each adjacent OSM node pair is a directed edge; distance is spherical and seconds round up.",
            "Edges crossing the fixed bbox are boundary cuts; incomplete PBF segments are omitted.",
        ],
        "unresolved_segments": unresolved_segments,
        "reviewed_way_tags": {
            str(way_id): included_ways[way_id]["tags"]
            for way_id in (7010992, 7010987) if way_id in included_ways
        },
        "restriction_relations_touching_ways": selected_restrictions(path, included_ways.keys()),
        "nodes": included_nodes,
        "coordinates": {node: nodes[int(node)] for node in included_nodes},
        "edges": edges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("way_ids", nargs="*", type=int)
    parser.add_argument("--bridge-graph", type=Path)
    args = parser.parse_args()
    if args.bridge_graph is not None:
        args.bridge_graph.write_text(
            json.dumps(bridge_graph(args.pbf), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return
    if not args.way_ids:
        parser.error("provide way IDs or --bridge-graph OUTPUT")
    ways = selected_ways(args.pbf, set(args.way_ids))
    node_ids = {node_id for way in ways.values() for node_id in way["node_ids"]}
    nodes = selected_nodes(args.pbf, node_ids)
    print(json.dumps({"ways": ways, "nodes": nodes}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
