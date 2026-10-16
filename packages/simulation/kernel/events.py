"""Stable, bounded simulation-time event queue."""

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum


class Phase(IntEnum):
    WATER = 0
    DISRUPTION = 1
    COMPLETION = 2
    DEMAND = 3
    DEADLINE = 4
    REPLAN = 5
    TERMINAL = 6


@dataclass(frozen=True, order=True)
class Event:
    time_seconds: int
    phase: Phase
    stable_sequence: int
    kind: str = field(compare=False)
    target_id: str | None = field(default=None, compare=False)


class EventQueue:
    """Run finite events through H, retaining future work for a later checkpoint.

    Handlers can add same-time events only in a later phase. Positive-time
    scheduling is unrestricted, including beyond H, so unfinished work remains
    explicit. A cap also bounds chains that advance only through phases.
    """

    def __init__(self, horizon_seconds: int, *, max_events_per_time: int = 10_000) -> None:
        if type(horizon_seconds) is not int or horizon_seconds <= 0:
            raise ValueError("horizon_seconds must be a positive integer")
        if type(max_events_per_time) is not int or max_events_per_time <= 0:
            raise ValueError("max_events_per_time must be a positive integer")
        self.horizon_seconds = horizon_seconds
        self.max_events_per_time = max_events_per_time
        self._heap: list[Event] = []
        self._next_sequence = 0
        self._current: Event | None = None
        self._finished = False
        self._counts: dict[int, int] = {}
        self.schedule(horizon_seconds, Phase.TERMINAL, "terminal")

    @property
    def remaining(self) -> tuple[Event, ...]:
        return tuple(sorted(self._heap))

    def schedule(
        self, time_seconds: int, phase: Phase, kind: str, target_id: str | None = None,
    ) -> Event:
        if self._finished:
            raise ValueError("terminal event has been processed")
        if type(time_seconds) is not int or time_seconds < 0:
            raise ValueError("event time must be a nonnegative integer")
        if not isinstance(phase, Phase) or not kind:
            raise ValueError("event phase and kind are required")
        if phase is Phase.TERMINAL:
            if kind != "terminal" or target_id is not None or self._next_sequence != 0:
                raise ValueError("terminal event is reserved for the horizon")
        elif time_seconds >= self.horizon_seconds and phase is Phase.REPLAN:
            raise ValueError("new actions cannot be dispatched at or after the horizon")
        if self._current is not None and (
            time_seconds < self._current.time_seconds
            or (time_seconds == self._current.time_seconds and phase <= self._current.phase)
        ):
            raise ValueError("events must advance time or move to a later phase")
        count = self._counts.get(time_seconds, 0) + 1
        if count > self.max_events_per_time:
            raise ValueError("same-time event limit exceeded")
        self._counts[time_seconds] = count
        event = Event(time_seconds, phase, self._next_sequence, kind, target_id)
        self._next_sequence += 1
        heapq.heappush(self._heap, event)
        return event

    def run(self, handler: Callable[[Event, "EventQueue"], None]) -> None:
        if self._finished:
            raise ValueError("terminal event has already been processed")
        while self._heap:
            event = heapq.heappop(self._heap)
            self._current = event
            try:
                handler(event, self)
            except Exception:
                heapq.heappush(self._heap, event)
                raise
            if event.phase is Phase.TERMINAL:
                self._finished = True
                break
            if not self._heap or self._heap[0].time_seconds > event.time_seconds:
                self._counts.pop(event.time_seconds, None)
        self._current = None
