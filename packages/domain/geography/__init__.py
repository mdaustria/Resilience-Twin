"""Review state for a declared local study area and access connectors."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class AreaMember:
    id: str
    label: str
    included: bool
    population: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class Connector:
    id: str
    point_id: str
    road_node_id: str | None
    distance_m: int | None
    accessible: bool | None
    reviewed: bool
    source: str
    longitude: float | None = None
    latitude: float | None = None

    @property
    def ready(self) -> bool:
        return (self.reviewed and self.road_node_id is not None
                and self.distance_m is not None and 0 <= self.distance_m <= 500
                and self.longitude is not None and self.latitude is not None
                and isfinite(self.longitude) and isfinite(self.latitude)
                and -180 <= self.longitude <= 180 and -90 <= self.latitude <= 90
                and self.accessible is True)


@dataclass(frozen=True, slots=True)
class StudyArea:
    id: str
    label: str
    source: Literal["manual", "geoapify-suggestion"]
    boundary_lon_lat: tuple[tuple[float, float], ...]
    members: tuple[AreaMember, ...]
    connectors: tuple[Connector, ...]
    routing_buffer_m: int
    cross_boundary_assumptions: tuple[str, ...]
    reviewer: str | None = None
    revision: int = 0

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def blockers(self) -> tuple[str, ...]:
        result: list[str] = []
        if len(self.boundary_lon_lat) < 4 or self.boundary_lon_lat[0] != self.boundary_lon_lat[-1]:
            result.append("closed reviewed boundary required")
        if any(not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90)
               for lon, lat in self.boundary_lon_lat):
            result.append("boundary coordinates invalid")
        if not 0 <= self.routing_buffer_m <= 10_000:
            result.append("routing buffer outside supported bound")
        if not any(member.included for member in self.members):
            result.append("select included area membership")
        if len({member.id for member in self.members}) != len(self.members):
            result.append("duplicate area member")
        if len(self.connectors) < 2:
            result.append("pickup and facility connectors required")
        if len({connector.id for connector in self.connectors}) != len(self.connectors):
            result.append("duplicate connector")
        for member in self.members:
            if member.included and (member.population is None or member.population < 0):
                result.append(f"included population unknown: {member.id}")
            if not member.included and not member.reason:
                result.append(f"exclusion reason missing: {member.id}")
        for connector in self.connectors:
            if not connector.ready:
                result.append(f"connector unresolved: {connector.id}")
            elif self.boundary_lon_lat:
                assert connector.longitude is not None and connector.latitude is not None
                west = min(point[0] for point in self.boundary_lon_lat)
                east = max(point[0] for point in self.boundary_lon_lat)
                south = min(point[1] for point in self.boundary_lon_lat)
                north = max(point[1] for point in self.boundary_lon_lat)
                if not (west <= connector.longitude <= east
                        and south <= connector.latitude <= north):
                    result.append(f"connector outside study area: {connector.id}")
        if self.reviewer is None:
            result.append("study area requires review")
        return tuple(result)

    def revise_membership(self, members: tuple[AreaMember, ...]) -> StudyArea:
        return replace(self, members=members, reviewer=None, revision=self.revision + 1)


__all__ = ("AreaMember", "Connector", "StudyArea")
