"""Pinned local OSM source and extent identity for the small importer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceCatalog:
    source_url: str
    expected_sha256: str
    license_name: str
    attribution: str
    snapshot_date: str | None
    parent_url: str | None = None
    parent_sha256: str | None = None

    def verify(self, path: Path) -> str:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != self.expected_sha256:
            raise ValueError("OSM source checksum differs from the pinned catalog")
        return digest


@dataclass(frozen=True)
class Extent:
    """Small rectangular study polygon, with a declared metric routing buffer."""

    south: float
    north: float
    west: float
    east: float
    buffer_m: int

    def __post_init__(self) -> None:
        if not (-90 <= self.south < self.north <= 90 and -180 <= self.west < self.east <= 180):
            raise ValueError("invalid extent bounds")
        if not 0 <= self.buffer_m <= 10_000:
            raise ValueError("routing buffer outside small-sample limit")

    def buffered_bounds(self) -> tuple[float, float, float, float]:
        from math import cos, radians

        latitude = (self.south + self.north) / 2
        lat_delta = self.buffer_m / 111_320
        lon_delta = self.buffer_m / (111_320 * cos(radians(latitude)))
        return (self.south - lat_delta, self.north + lat_delta,
                self.west - lon_delta, self.east + lon_delta)


UTRECHT_SOURCE = SourceCatalog(
    source_url="https://github.com/valhalla/valhalla/blob/3.9.1/test/data/utrecht_netherlands.osm.pbf",
    expected_sha256="8522f893d9c9c201d19d8fc0e39a038ad25fb21f6832370d4d257b4b495b9fa7",
    license_name="ODbL 1.0", attribution="© OpenStreetMap contributors",
    snapshot_date=None,
)
UTRECHT_EXTENT = Extent(south=52.0773, north=52.0815, west=5.1195, east=5.1277, buffer_m=100)

METRO_MANILA_SOURCE = SourceCatalog(
    source_url="https://download.openstreetmap.fr/extracts/asia/philippines/metro_manila.osm.pbf",
    expected_sha256="b3ce4246589f163b46673f77f1c0fa29f52f982529fe1e151fa126ec89a8e7a6",
    license_name="ODbL 1.0", attribution="© OpenStreetMap contributors",
    snapshot_date="2026-10-13T00:59:48Z",
)
TALAYAN_SAMPLE_EXTENT = Extent(south=14.629, north=14.638, west=121.005, east=121.018, buffer_m=250)
TALAYAN_SAMPLE_SOURCE = SourceCatalog(
    source_url="release/validation/geography/talayan-20261013.osm.pbf",
    expected_sha256="fbea4907750e0a10be7be6a7b9188ec91d5c74c9790ab600ea02265434f73ae6",
    license_name="ODbL 1.0", attribution="© OpenStreetMap contributors",
    snapshot_date="2026-10-13T00:59:48Z",
    parent_url=METRO_MANILA_SOURCE.source_url,
    parent_sha256=METRO_MANILA_SOURCE.expected_sha256,
)
CENTRAL_LUZON_SOURCE = SourceCatalog(
    source_url="https://download.openstreetmap.fr/extracts/asia/philippines/central_luzon.osm.pbf",
    expected_sha256="d3cbf4f9c0cc26c6d10cf074aa797d9de8b04972cfc9c6b3434cd490807bf1e7",
    license_name="ODbL 1.0", attribution="© OpenStreetMap contributors",
    snapshot_date="2026-10-13T00:59:48Z",
)
GUIGUINTO_SAMPLE_EXTENT = Extent(south=14.823, north=14.832, west=120.874, east=120.884, buffer_m=250)
GUIGUINTO_SAMPLE_SOURCE = SourceCatalog(
    source_url="release/validation/geography/guiguinto-20261013.osm.pbf",
    expected_sha256="4b4ceb0440f06b92ae4edcaf33ca970e8a685c13cc61281d929ecda5d086ae75",
    license_name="ODbL 1.0", attribution="© OpenStreetMap contributors",
    snapshot_date="2026-10-13T00:59:48Z",
    parent_url=CENTRAL_LUZON_SOURCE.source_url,
    parent_sha256=CENTRAL_LUZON_SOURCE.expected_sha256,
)


__all__ = [
    "CENTRAL_LUZON_SOURCE",
    "GUIGUINTO_SAMPLE_EXTENT",
    "GUIGUINTO_SAMPLE_SOURCE",
    "METRO_MANILA_SOURCE",
    "TALAYAN_SAMPLE_EXTENT",
    "TALAYAN_SAMPLE_SOURCE",
    "UTRECHT_EXTENT",
    "UTRECHT_SOURCE",
    "Extent",
    "SourceCatalog",
]
