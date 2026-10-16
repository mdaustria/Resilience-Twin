"""Physical disruptions apply at effect time; policy learns them at knowledge time."""

from dataclasses import dataclass
from typing import Literal

from packages.simulation.kernel.observations import Observation, ObservationLedger
from packages.simulation.kernel.resources import ResourceLedger


@dataclass(frozen=True)
class Disruption:
    id: str
    kind: Literal["edge_closed", "asset_closed", "vehicle_outage", "shelter_capacity"]
    target_id: str
    effective_seconds: int
    known_seconds: int
    value: int | None = None

    def __post_init__(self) -> None:
        Observation(
            self.id, self.kind, self.target_id,
            self.effective_seconds, self.known_seconds, self.value,
        )


class DisruptionLedger:
    def __init__(self, disruptions: tuple[Disruption, ...]) -> None:
        if len({item.id for item in disruptions}) != len(disruptions):
            raise ValueError("duplicate disruption ID")
        self._events = tuple(sorted(disruptions, key=lambda item: (
            item.effective_seconds, item.id,
        )))
        self._applied: set[str] = set()
        self.closed_edges: set[str] = set()
        self.closed_assets: set[str] = set()

    def apply_due(
        self, now_seconds: int, resources: ResourceLedger, observations: ObservationLedger,
    ) -> tuple[str, ...]:
        if type(now_seconds) is not int or now_seconds < 0:
            raise ValueError("disruption time must be nonnegative integer seconds")
        applied: list[str] = []
        for item in self._events:
            if item.effective_seconds > now_seconds:
                break
            if item.id in self._applied:
                continue
            if item.kind == "edge_closed":
                self.closed_edges.add(item.target_id)
            elif item.kind == "asset_closed":
                self.closed_assets.add(item.target_id)
            elif item.kind == "vehicle_outage":
                resources.outage(item.target_id)
            elif item.kind == "shelter_capacity":
                assert item.value is not None
                resources.set_shelter_capacity(item.target_id, item.value)
            observations.record(Observation(
                item.id, item.kind, item.target_id,
                item.effective_seconds, item.known_seconds, item.value,
            ))
            self._applied.add(item.id)
            applied.append(item.id)
        return tuple(applied)

    def can_enter(self, edge_id: str, asset_id: str | None = None) -> bool:
        """Closures block new edge entry, not an already occupied edge."""
        return edge_id not in self.closed_edges and (
            asset_id is None or asset_id not in self.closed_assets
        )

    def snapshot(self) -> tuple[Disruption, ...]:
        return self._events

    @property
    def applied_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._applied))


__all__ = ("Disruption", "DisruptionLedger")
