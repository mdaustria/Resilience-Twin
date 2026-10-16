"""Bounded PBF import for pinned small study extents.

This strict reader preserves complete selected-way node chains and relevant
restriction members. Regional imports still need the approved geo runtime.
"""

from __future__ import annotations

import json
import struct
import zlib
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path
from typing import TypedDict

from packages.adapters.geo.catalog import Extent, SourceCatalog

MAX_BLOCK = 32_000_000
MAX_WAYS = 500_000
MAX_SELECTED = 5_000
FieldValue = int | bytes


class Way(TypedDict):
    node_ids: list[int]
    tags: dict[str, str]


class Member(TypedDict):
    role: str
    id: int
    type: str


class Relation(TypedDict):
    id: int
    tags: dict[str, str]
    members: list[Member]


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    result = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 127) << shift
        if byte < 128:
            return result, offset
        shift += 7
        if shift >= 70:
            raise ValueError("PBF varint exceeds bound")
    raise ValueError("truncated PBF varint")


def _fields(data: bytes) -> list[tuple[int, int, FieldValue]]:
    found: list[tuple[int, int, FieldValue]] = []
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        value: FieldValue
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 2:
            length, offset = _varint(data, offset)
            if length > MAX_BLOCK or offset + length > len(data):
                raise ValueError("truncated or oversized PBF field")
            value = data[offset:offset + length]
            offset += length
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if offset + size > len(data):
                raise ValueError("truncated fixed PBF field")
            offset += size
            continue
        else:
            raise ValueError("unsupported PBF wire type")
        found.append((number, wire, value))
    return found


def _packed(data: bytes) -> list[int]:
    values: list[int] = []
    offset = 0
    while offset < len(data):
        value, offset = _varint(data, offset)
        values.append(value)
    return values


def _numbers(fields: list[tuple[int, int, FieldValue]], number: int) -> list[int]:
    values: list[int] = []
    for field_number, wire, value in fields:
        if field_number == number:
            if wire == 0 and isinstance(value, int):
                values.append(value)
            elif wire == 2 and isinstance(value, bytes):
                values.extend(_packed(value))
    return values


def _first(fields: list[tuple[int, int, FieldValue]], number: int) -> FieldValue:
    return next(value for field_number, _, value in fields if field_number == number)


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _blocks(path: Path) -> Iterator[tuple[str, bytes]]:
    with path.open("rb") as stream:
        while size_bytes := stream.read(4):
            if len(size_bytes) != 4:
                raise ValueError("truncated PBF header length")
            header_size = struct.unpack(">I", size_bytes)[0]
            if not 0 < header_size <= 64_000:
                raise ValueError("PBF header size exceeds bound")
            header = stream.read(header_size)
            if len(header) != header_size:
                raise ValueError("truncated PBF header")
            fields = _fields(header)
            kind = _first(fields, 1)
            blob_size = _first(fields, 3)
            if not isinstance(kind, bytes) or not isinstance(blob_size, int) or blob_size > MAX_BLOCK:
                raise ValueError("invalid PBF block header")
            blob = stream.read(blob_size)
            if len(blob) != blob_size:
                raise ValueError("truncated PBF block")
            content = _fields(blob)
            raw = next((value for number, _, value in content if number == 1), None)
            compressed = next((value for number, _, value in content if number == 3), None)
            if isinstance(raw, bytes):
                payload = raw
            elif isinstance(compressed, bytes):
                decoder = zlib.decompressobj()
                payload = decoder.decompress(compressed, MAX_BLOCK + 1)
                if not decoder.eof or decoder.unconsumed_tail:
                    raise ValueError("truncated or oversized compressed PBF block")
            else:
                raise TypeError("unsupported PBF compression")
            if len(payload) > MAX_BLOCK:
                raise ValueError("PBF decompressed block exceeds bound")
            yield kind.decode("ascii"), payload


def _strings(block_fields: list[tuple[int, int, FieldValue]]) -> list[str]:
    table = _first(block_fields, 1)
    if not isinstance(table, bytes):
        raise TypeError("invalid PBF string table")
    return [value.decode("utf-8") for number, _, value in _fields(table)
            if number == 1 and isinstance(value, bytes)]


def _tags(fields: list[tuple[int, int, FieldValue]], strings: list[str]) -> dict[str, str]:
    keys, values = _numbers(fields, 2), _numbers(fields, 3)
    if len(keys) != len(values):
        raise ValueError("PBF tag keys and values differ")
    return {strings[key]: strings[value] for key, value in zip(keys, values)}


def _delta(values: list[int]) -> list[int]:
    result: list[int] = []
    current = 0
    for value in values:
        current += _zigzag(value)
        result.append(current)
    return result


def _ways_relations(path: Path) -> tuple[dict[int, Way], list[Relation]]:
    ways: dict[int, Way] = {}
    relations: list[Relation] = []
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        fields = _fields(block)
        strings = _strings(fields)
        for number, _, group in fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for member_kind, _, item in _fields(group):
                if not isinstance(item, bytes):
                    continue
                parts = _fields(item)
                if member_kind == 3:
                    tags = _tags(parts, strings)
                    if "highway" in tags:
                        way_id = _numbers(parts, 1)[0]
                        ways[way_id] = {"node_ids": _delta(_numbers(parts, 8)), "tags": tags}
                        if len(ways) > MAX_WAYS:
                            raise ValueError("small-sample road-way limit exceeded")
                elif member_kind == 4:
                    tags = _tags(parts, strings)
                    if tags.get("type") != "restriction":
                        continue
                    roles, ids, types = _numbers(parts, 8), _delta(_numbers(parts, 9)), _numbers(parts, 10)
                    if not len(roles) == len(ids) == len(types):
                        raise ValueError("PBF relation member mismatch")
                    members: list[Member] = [{"role": strings[role], "id": identity,
                                              "type": ("node", "way", "relation")[member_type]}
                               for role, identity, member_type in zip(roles, ids, types)]
                    relations.append({"id": _numbers(parts, 1)[0], "tags": tags, "members": members})
    return ways, relations


def _member_ways(path: Path, wanted: set[int]) -> dict[int, Way]:
    """Recover non-road relation members without retaining every regional building."""
    found: dict[int, Way] = {}
    if not wanted:
        return found
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        fields = _fields(block)
        strings = _strings(fields)
        for number, _, group in fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for member_kind, _, item in _fields(group):
                if member_kind != 3 or not isinstance(item, bytes):
                    continue
                parts = _fields(item)
                way_id = _numbers(parts, 1)[0]
                if way_id in wanted:
                    found[way_id] = {"node_ids": _delta(_numbers(parts, 8)),
                                     "tags": _tags(parts, strings)}
    return found


def _numeric(block_fields: list[tuple[int, int, FieldValue]], number: int, default: int) -> int:
    value = next((value for field_number, _, value in block_fields if field_number == number), default)
    if not isinstance(value, int):
        raise TypeError("invalid PBF coordinate scale")
    return value


def _nodes(path: Path, wanted: set[int]) -> dict[int, tuple[float, float]]:
    nodes: dict[int, tuple[float, float]] = {}
    for kind, block in _blocks(path):
        if kind != "OSMData":
            continue
        fields = _fields(block)
        granularity = _numeric(fields, 17, 100)
        lat_offset = _numeric(fields, 19, 0)
        lon_offset = _numeric(fields, 20, 0)
        for number, _, group in fields:
            if number != 2 or not isinstance(group, bytes):
                continue
            for member_kind, _, item in _fields(group):
                if not isinstance(item, bytes):
                    continue
                parts = _fields(item)
                if member_kind == 1:
                    identity = _numbers(parts, 1)[0]
                    if identity in wanted:
                        lat, lon = _zigzag(_numbers(parts, 8)[0]), _zigzag(_numbers(parts, 9)[0])
                        nodes[identity] = ((lat_offset + granularity * lat) * 1e-9,
                                           (lon_offset + granularity * lon) * 1e-9)
                elif member_kind == 2:
                    ids = _delta(_numbers(parts, 1))
                    lats = _delta(_numbers(parts, 8))
                    lons = _delta(_numbers(parts, 9))
                    if not len(ids) == len(lats) == len(lons):
                        raise ValueError("PBF dense node mismatch")
                    for identity, lat, lon in zip(ids, lats, lons):
                        if identity in wanted:
                            nodes[identity] = ((lat_offset + granularity * lat) * 1e-9,
                                               (lon_offset + granularity * lon) * 1e-9)
    return nodes


def _inside(point: tuple[float, float], bounds: tuple[float, float, float, float]) -> bool:
    south, north, west, east = bounds
    return south <= point[0] <= north and west <= point[1] <= east


def _crosses_box(a: tuple[float, float], b: tuple[float, float],
                 bounds: tuple[float, float, float, float]) -> bool:
    """Closed segment/rectangle intersection, including outside-to-outside crossings."""
    south, north, west, east = bounds
    x, y = a[1], a[0]
    dx, dy = b[1] - x, b[0] - y
    lower, upper = 0.0, 1.0
    for p, q in ((-dx, x - west), (dx, east - x), (-dy, y - south), (dy, north - y)):
        if p == 0:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return True


def import_sample(path: Path, source: SourceCatalog, extent: Extent) -> dict[str, object]:
    digest = source.verify(path)
    ways, relations = _ways_relations(path)
    roads = {identity: way for identity, way in ways.items() if "highway" in way["tags"]}
    wanted = {node for way in roads.values() for node in way["node_ids"]}
    nodes = _nodes(path, wanted)
    bounds = extent.buffered_bounds()
    selected: set[int] = set()
    for identity, way in roads.items():
        refs = way["node_ids"]
        if any(left in nodes and right in nodes and _crosses_box(nodes[left], nodes[right], bounds)
               for left, right in pairwise(refs)):
            selected.add(identity)
    # Include complete members of restrictions touching the selected road ways.
    relevant: list[Relation] = []
    for relation in relations:
        members = relation["members"]
        if any(member["type"] == "way" and member["id"] in selected for member in members):
            relevant.append(relation)
            selected.update(member["id"] for member in members if member["type"] == "way")
    if len(selected) > MAX_SELECTED:
        raise ValueError("small-sample selected-way limit exceeded")
    ways.update(_member_ways(path, selected - ways.keys()))
    missing_ways = sorted(selected - ways.keys())
    if missing_ways:
        raise ValueError("restriction references a way absent from the source")
    missing_nodes = {node for identity in selected for node in ways[identity]["node_ids"]} - nodes.keys()
    if missing_nodes:
        # A restriction may add a non-road member whose nodes were not in the first node pass.
        nodes.update(_nodes(path, missing_nodes))
    if any(node not in nodes for identity in selected for node in ways[identity]["node_ids"]):
        raise ValueError("selected way has incomplete source geometry")
    cuts: list[dict[str, object]] = []
    for identity in sorted(selected):
        refs = ways[identity]["node_ids"]
        for index, (left, right) in enumerate(pairwise(refs)):
            if _crosses_box(nodes[left], nodes[right], bounds) and not (
                _inside(nodes[left], bounds) and _inside(nodes[right], bounds)
            ):
                cuts.append({"way_id": identity, "segment_index": index,
                             "from_inside": _inside(nodes[left], bounds),
                             "to_inside": _inside(nodes[right], bounds)})
    result: dict[str, object] = {
        "schema_version": "osm-small-import.v1", "source_sha256": digest,
        "source_url": source.source_url, "source_snapshot_date": source.snapshot_date,
        "license": source.license_name, "attribution": source.attribution,
        "polygon_lon_lat": [[extent.west, extent.south], [extent.east, extent.south],
                            [extent.east, extent.north], [extent.west, extent.north],
                            [extent.west, extent.south]],
        "buffer_m": extent.buffer_m, "buffered_bounds_lat_lon": list(bounds),
        "ways": {str(identity): {"node_ids": ways[identity]["node_ids"],
                                  "tags": ways[identity]["tags"]} for identity in sorted(selected)},
        "nodes": {str(identity): list(nodes[identity]) for identity in sorted({
            node for way_id in selected for node in ways[way_id]["node_ids"]
        })},
        "restriction_relations": sorted(relevant, key=lambda relation: relation["id"]),
        "boundary_cuts": cuts,
        "warnings": (["Original OSM extraction date is unknown; not a production source snapshot"]
                     if source.snapshot_date is None else []),
    }
    if source.parent_url is not None and source.parent_sha256 is not None:
        result["parent_source_url"] = source.parent_url
        result["parent_source_sha256"] = source.parent_sha256
    return result


def canonical_bytes(result: dict[str, object]) -> bytes:
    return (json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


__all__ = ["canonical_bytes", "import_sample"]
