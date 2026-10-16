"""Write a deterministic small PBF from a verified regional import artifact.

The input JSON is produced only after checking the full regional source hash.
This writer keeps full selected ways, their referenced nodes, and every touching
restriction member. It is a fixture packer, not a general OSM clipping service.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative protobuf unsigned integer")
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def _field(number: int, value: int | bytes) -> bytes:
    if isinstance(value, int):
        return _varint(number << 3) + _varint(value)
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _packed(values: list[int]) -> bytes:
    return b"".join(_varint(value) for value in values)


def _delta(values: list[int]) -> list[int]:
    previous = 0
    result = []
    for value in values:
        result.append(_zigzag(value - previous))
        previous = value
    return result


def _blob(kind: bytes, payload: bytes, *, compressed: bool) -> bytes:
    body = (_field(2, len(payload)) + _field(3, zlib.compress(payload, level=9))
            if compressed else _field(1, payload))
    header = _field(1, kind) + _field(3, len(body))
    return struct.pack(">I", len(header)) + header + body


def pack_import(artifact: dict[str, object]) -> bytes:
    nodes = artifact["nodes"]
    ways = artifact["ways"]
    relations = artifact["restriction_relations"]
    if not isinstance(nodes, dict) or not isinstance(ways, dict) or not isinstance(relations, list):
        raise TypeError("invalid import artifact")
    strings = {""}
    for way in ways.values():
        strings.update(way["tags"])
        strings.update(way["tags"].values())
    for relation in relations:
        strings.update(relation["tags"])
        strings.update(relation["tags"].values())
        strings.update(member["role"] for member in relation["members"])
    ordered = [""] + sorted(strings - {""})
    index = {value: number for number, value in enumerate(ordered)}
    table = b"".join(_field(1, value.encode("utf-8")) for value in ordered)

    group = bytearray()
    for identity, coords in sorted(nodes.items(), key=lambda pair: int(pair[0])):
        lat, lon = coords
        node = (_field(1, int(identity)) + _field(8, _zigzag(round(lat * 10_000_000)))
                + _field(9, _zigzag(round(lon * 10_000_000))))
        group.extend(_field(1, node))
    for identity, way in sorted(ways.items(), key=lambda pair: int(pair[0])):
        tags = sorted(way["tags"].items())
        body = (_field(1, int(identity))
                + _field(2, _packed([index[key] for key, _ in tags]))
                + _field(3, _packed([index[value] for _, value in tags]))
                + _field(8, _packed(_delta(way["node_ids"]))))
        group.extend(_field(3, body))
    for relation in sorted(relations, key=lambda item: item["id"]):
        tags = sorted(relation["tags"].items())
        members = relation["members"]
        body = (_field(1, relation["id"])
                + _field(2, _packed([index[key] for key, _ in tags]))
                + _field(3, _packed([index[value] for _, value in tags]))
                + _field(8, _packed([index[member["role"]] for member in members]))
                + _field(9, _packed(_delta([member["id"] for member in members])))
                + _field(10, _packed([{"node": 0, "way": 1, "relation": 2}[member["type"]]
                                     for member in members])))
        group.extend(_field(4, body))
    data = _field(1, table) + _field(2, bytes(group)) + _field(17, 100)
    header = _field(4, b"OsmSchema-V0.6")
    return _blob(b"OSMHeader", header, compressed=False) + _blob(b"OSMData", data, compressed=True)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) == 2 else "talayan"
    if name not in {"talayan", "guiguinto"}:
        raise SystemExit("sample must be talayan or guiguinto")
    source = Path(f"release/validation/geography/{name}-small.json")
    target = Path(f"release/validation/geography/{name}-20261013.osm.pbf")
    target.write_bytes(pack_import(json.loads(source.read_text(encoding="utf-8"))))
    print(f"{target}: {target.stat().st_size} bytes")
