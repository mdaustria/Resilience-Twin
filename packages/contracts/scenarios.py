"""Immutable structured exogenous scenario and suite contracts."""

from dataclasses import dataclass
from typing import Literal

Effect = Literal["edge_closed", "asset_closed", "vehicle_outage", "shelter_capacity"]


@dataclass(frozen=True)
class ScenarioEvent:
    id: str
    effect: Effect
    target_id: str
    effective_seconds: int
    known_seconds: int
    hazard_reference: str
    capacity_people: int | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.target_id or not self.hazard_reference:
            raise ValueError("scenario event identity, target and hazard reference are required")
        if (type(self.effective_seconds) is not int or self.effective_seconds < 0
                or type(self.known_seconds) is not int or self.known_seconds < 0):
            raise ValueError("scenario event times must be nonnegative integers")
        if self.effect == "shelter_capacity":
            if type(self.capacity_people) is not int or self.capacity_people < 0:
                raise ValueError("shelter capacity requires a nonnegative integer")
        elif self.capacity_people is not None:
            raise ValueError("only shelter capacity events carry a count")


@dataclass(frozen=True)
class Scenario:
    id: str
    horizon_seconds: int
    events: tuple[ScenarioEvent, ...]

    def __post_init__(self) -> None:
        if not self.id or type(self.horizon_seconds) is not int or self.horizon_seconds <= 0:
            raise ValueError("scenario needs an ID and positive horizon")
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("duplicate scenario event ID")
        if any(event.effective_seconds > self.horizon_seconds for event in self.events):
            raise ValueError("scenario event exceeds the horizon")


@dataclass(frozen=True)
class SuiteMember:
    id: str
    seed: int
    scenario: Scenario

    def __post_init__(self) -> None:
        if not self.id or type(self.seed) is not int or self.seed < 0:
            raise ValueError("suite member needs an ID and nonnegative integer seed")


@dataclass(frozen=True)
class ScenarioSuite:
    id: str
    generator_version: str
    members: tuple[SuiteMember, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.generator_version or not self.members:
            raise ValueError("suite identity, version and members are required")
        if len({item.id for item in self.members}) != len(self.members):
            raise ValueError("duplicate suite member ID")


__all__ = ("Scenario", "ScenarioEvent", "ScenarioSuite", "SuiteMember")
