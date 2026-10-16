"""Deterministic observations with an explicit knowledge boundary."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Observation:
    id: str
    kind: Literal["edge_closed", "asset_closed", "vehicle_outage", "shelter_capacity"]
    target_id: str
    effective_seconds: int
    known_seconds: int
    value: int | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.target_id:
            raise ValueError("observation IDs are required")
        if (type(self.effective_seconds) is not int or self.effective_seconds < 0
                or type(self.known_seconds) is not int or self.known_seconds < 0):
            raise ValueError("observation times must be nonnegative integer seconds")
        if self.kind == "shelter_capacity":
            if type(self.value) is not int or self.value < 0:
                raise ValueError("shelter capacity observation needs an integer value")
        elif self.value is not None:
            raise ValueError("closure/outage observations cannot carry a capacity")


class ObservationLedger:
    def __init__(self, observations: tuple[Observation, ...] = ()) -> None:
        if len({item.id for item in observations}) != len(observations):
            raise ValueError("duplicate observation ID")
        self._items = {item.id: item for item in observations}

    def record(self, observation: Observation) -> None:
        if observation.id in self._items:
            raise ValueError("duplicate observation ID")
        self._items[observation.id] = observation

    def visible(self, now_seconds: int) -> tuple[Observation, ...]:
        if type(now_seconds) is not int or now_seconds < 0:
            raise ValueError("observation time must be nonnegative integer seconds")
        return tuple(sorted(
            (item for item in self._items.values() if item.known_seconds <= now_seconds
             and item.effective_seconds <= now_seconds),
            key=lambda item: (item.effective_seconds, item.known_seconds, item.id),
        ))

    def snapshot(self) -> tuple[Observation, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


__all__ = ("Observation", "ObservationLedger")
