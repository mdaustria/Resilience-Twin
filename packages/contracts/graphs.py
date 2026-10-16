"""Provenance and review record for a compiled exact-edge road graph."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphIssue:
    source_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class CompiledGraphRecord:
    source_sha256: str
    profile: str
    speed_fallback_kph: int
    weight_method: str
    edge_count: int
    restriction_count: int
    boundary_edge_ids: tuple[str, ...]
    issues: tuple[GraphIssue, ...]


__all__ = ("CompiledGraphRecord", "GraphIssue")
