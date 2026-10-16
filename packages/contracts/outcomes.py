"""Shared integer outcome record for simulation and domain comparisons."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    on_time_people: int
    vulnerable_on_time_people: int
    water_unmet_ml: int
    stranded_people: int
    evidence_event_ids: tuple[str, ...]


__all__ = ("Outcome",)
