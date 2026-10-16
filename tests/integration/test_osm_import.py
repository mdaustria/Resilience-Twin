"""Pinned small PBF import, complete geometry and conservative extent evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packages.adapters.geo.catalog import (
    GUIGUINTO_SAMPLE_EXTENT,
    GUIGUINTO_SAMPLE_SOURCE,
    TALAYAN_SAMPLE_EXTENT,
    TALAYAN_SAMPLE_SOURCE,
    UTRECHT_EXTENT,
    UTRECHT_SOURCE,
    SourceCatalog,
)
from packages.adapters.geo.extract import _crosses_box, canonical_bytes, import_sample

ROOT = Path(__file__).parents[2]
PBF = ROOT / "release" / "routing" / "utrecht_netherlands.osm.pbf"
ARTIFACT = ROOT / "release" / "validation" / "geography" / "utrecht-small.json"
TALAYAN_PBF = ROOT / "release" / "validation" / "geography" / "talayan-20261013.osm.pbf"
TALAYAN_ARTIFACT = ROOT / "release" / "validation" / "geography" / "talayan-small.json"
GUIGUINTO_PBF = ROOT / "release" / "validation" / "geography" / "guiguinto-20261013.osm.pbf"
GUIGUINTO_ARTIFACT = ROOT / "release" / "validation" / "geography" / "guiguinto-small.json"


def test_guiguinto_local_sample_repeats_with_recorded_parent() -> None:
    first = import_sample(GUIGUINTO_PBF, GUIGUINTO_SAMPLE_SOURCE, GUIGUINTO_SAMPLE_EXTENT)
    second = import_sample(GUIGUINTO_PBF, GUIGUINTO_SAMPLE_SOURCE, GUIGUINTO_SAMPLE_EXTENT)
    assert canonical_bytes(first) == canonical_bytes(second) == GUIGUINTO_ARTIFACT.read_bytes()
    assert first["parent_source_sha256"] == GUIGUINTO_SAMPLE_SOURCE.parent_sha256
    assert first["source_snapshot_date"] == "2026-10-13T00:59:48Z"
    assert len(first["ways"]) == 295
    assert len(first["nodes"]) == 1436
    assert len(first["boundary_cuts"]) == 62


def test_dated_philippine_sample_repeats_with_complete_restrictions() -> None:
    first = import_sample(TALAYAN_PBF, TALAYAN_SAMPLE_SOURCE, TALAYAN_SAMPLE_EXTENT)
    second = import_sample(TALAYAN_PBF, TALAYAN_SAMPLE_SOURCE, TALAYAN_SAMPLE_EXTENT)
    assert canonical_bytes(first) == canonical_bytes(second) == TALAYAN_ARTIFACT.read_bytes()
    assert first["source_snapshot_date"] == "2026-10-13T00:59:48Z"
    assert first["source_sha256"] == TALAYAN_SAMPLE_SOURCE.expected_sha256
    assert first["parent_source_sha256"] == TALAYAN_SAMPLE_SOURCE.parent_sha256
    assert first["license"] == "ODbL 1.0"
    assert first["warnings"] == []
    assert len(first["ways"]) == 608
    assert len(first["nodes"]) == 2288
    assert len(first["restriction_relations"]) == 8
    assert len(first["boundary_cuts"]) == 101
    for relation in first["restriction_relations"]:
        for member in relation["members"]:
            if member["type"] == "way":
                assert str(member["id"]) in first["ways"]
            if member["type"] == "node":
                assert str(member["id"]) in first["nodes"]
    for way in first["ways"].values():
        assert all(str(node) in first["nodes"] for node in way["node_ids"])


def test_repeated_pinned_import_matches_saved_artifact_and_full_source() -> None:
    first = import_sample(PBF, UTRECHT_SOURCE, UTRECHT_EXTENT)
    second = import_sample(PBF, UTRECHT_SOURCE, UTRECHT_EXTENT)
    encoded = canonical_bytes(first)
    assert encoded == canonical_bytes(second) == ARTIFACT.read_bytes()
    assert first["source_sha256"] == UTRECHT_SOURCE.expected_sha256
    assert first["source_snapshot_date"] is None
    assert first["license"] == "ODbL 1.0"
    assert len(first["ways"]) == 452
    assert len(first["nodes"]) == 1246
    assert len(first["boundary_cuts"]) == 74
    assert hashlib.sha256(encoded).hexdigest() == hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()

    bridge = first["ways"]["7010992"]
    assert bridge["tags"]["bridge"] == "yes"
    assert bridge["tags"]["layer"] == "1"
    assert all(str(node) in first["nodes"] for node in bridge["node_ids"])
    assert any(relation["id"] == 153969 for relation in first["restriction_relations"])
    for way in first["ways"].values():
        assert len(way["node_ids"]) >= 2
        assert all(str(node) in first["nodes"] for node in way["node_ids"])
    for relation in first["restriction_relations"]:
        assert all(str(member["id"]) in first["ways"]
                   for member in relation["members"] if member["type"] == "way")


def test_source_checksum_and_malformed_pbf_fail_closed(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.osm.pbf"
    wrong.write_bytes(b"not the pinned source")
    with pytest.raises(ValueError, match="checksum"):
        import_sample(wrong, UTRECHT_SOURCE, UTRECHT_EXTENT)
    malformed = SourceCatalog(source_url="local synthetic", expected_sha256=hashlib.sha256(b"bad").hexdigest(),
                              license_name="synthetic", attribution="test", snapshot_date=None)
    wrong.write_bytes(b"bad")
    with pytest.raises(ValueError):
        import_sample(wrong, malformed, UTRECHT_EXTENT)


def test_outside_to_outside_segment_crossing_is_not_dropped() -> None:
    bounds = (0.0, 1.0, 0.0, 1.0)
    assert _crosses_box((0.5, -1.0), (0.5, 2.0), bounds)
    assert not _crosses_box((-1.0, -1.0), (-0.5, -0.5), bounds)


def test_catalog_artifact_is_canonical_json() -> None:
    value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert canonical_bytes(value) == ARTIFACT.read_bytes()
    assert value["buffer_m"] == 100
    assert value["warnings"] == ["Original OSM extraction date is unknown; not a production source snapshot"]
