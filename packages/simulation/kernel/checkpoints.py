"""Explicit type-whitelisted engine state encoding for JSON checkpoints."""

import heapq
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from packages.simulation.kernel import (
    events,
    observations,
    population,
    resources,
    water,
)

_TYPES = {item.__name__: item for module in (
    events, observations, population, resources, water,
) for item in vars(module).values() if isinstance(item, type) and (
    is_dataclass(item) or issubclass(item, Enum)
)}


def encode(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {"$type": type(value).__name__,
                "$fields": {field.name: encode(getattr(value, field.name))
                            for field in fields(value)}}
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "value": value.value}
    if isinstance(value, tuple):
        return {"$tuple": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, set):
        return {"$set": [encode(item) for item in sorted(value)]}
    if isinstance(value, dict):
        return {"$dict": [[encode(key), encode(item)] for key, item in
                          sorted(value.items(), key=lambda pair: str(pair[0]))]}
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"unsupported checkpoint value: {type(value).__name__}")


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        if value is None or type(value) in (str, int, bool):
            return value
        raise ValueError("unsupported checkpoint primitive")
    if "$type" in value:
        if set(value) != {"$type", "$fields"} or value["$type"] not in _TYPES:
            raise ValueError("unknown checkpoint record type")
        record = _TYPES[value["$type"]]
        if not is_dataclass(record) or set(value["$fields"]) != {
            field.name for field in fields(record)
        }:
            raise ValueError("invalid checkpoint record fields")
        return record(**{key: decode(item) for key, item in value["$fields"].items()})
    if "$enum" in value:
        if set(value) != {"$enum", "value"} or value["$enum"] not in _TYPES:
            raise ValueError("unknown checkpoint enum")
        enum_type = _TYPES[value["$enum"]]
        if not issubclass(enum_type, Enum):
            raise ValueError("invalid checkpoint enum")
        return enum_type(value["value"])
    if set(value) == {"$tuple"}:
        return tuple(decode(item) for item in value["$tuple"])
    if set(value) == {"$set"}:
        return {decode(item) for item in value["$set"]}
    if set(value) == {"$dict"}:
        entries = [(decode(key), decode(item)) for key, item in value["$dict"]]
        if len({key for key, _ in entries}) != len(entries):
            raise ValueError("duplicate checkpoint map key")
        return dict(entries)
    raise ValueError("unrecognized checkpoint shape")


def capture_state(
    queue: events.EventQueue, cohorts: population.PopulationLedger,
    assets: resources.ResourceLedger, supplies: water.WaterLedger,
    known: observations.ObservationLedger,
) -> dict[str, Any]:
    return {"queue": encode(queue.__dict__), "population": encode(cohorts.__dict__),
            "resources": encode(assets.__dict__), "water": encode(supplies.__dict__),
            "observations": encode(known.__dict__)}


def restore_state(state: dict[str, Any]) -> tuple[
    events.EventQueue, population.PopulationLedger, resources.ResourceLedger,
    water.WaterLedger, observations.ObservationLedger,
]:
    if set(state) != {"queue", "population", "resources", "water", "observations"}:
        raise ValueError("checkpoint state sections are incomplete")
    queue = object.__new__(events.EventQueue)
    cohorts = object.__new__(population.PopulationLedger)
    assets = object.__new__(resources.ResourceLedger)
    supplies = object.__new__(water.WaterLedger)
    known = object.__new__(observations.ObservationLedger)
    for name, target in (("queue", queue), ("population", cohorts),
                         ("resources", assets), ("water", supplies),
                         ("observations", known)):
        target.__dict__.update(decode(state[name]))
    heapq.heapify(queue._heap)
    queue._current = None  # Captures occur after the event's handler has committed.
    cohorts.assert_conserved()
    assets.assert_invariants()
    supplies.assert_balanced()
    if queue._finished or queue._next_sequence <= max(
        (item.stable_sequence for item in queue._heap), default=-1
    ):
        raise ValueError("invalid queue continuation state")
    return queue, cohorts, assets, supplies, known


__all__ = ("capture_state", "decode", "encode", "restore_state")
