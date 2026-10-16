"""Same-time phase order, deadline inclusivity and terminal processing."""

import json
from pathlib import Path

import pytest

from packages.simulation.kernel import (
    Event,
    EventQueue,
    Phase,
    PopulationLedger,
    PopulationSlice,
    PopulationState,
)
from packages.simulation.metrics.population import at_horizon

FIXTURE = Path(__file__).parents[1] / "fixtures/engine/boundaries/disruption-at-horizon.json"


def test_disruption_precedes_same_time_completion_and_deadline() -> None:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    queue = EventQueue(case["horizon_seconds"])
    ledger = PopulationLedger([PopulationSlice(
        "group", "group", case["people"], PopulationState.UNLOADING,
        deadline_seconds=case["deadline_seconds"], location_id="shelter",
    )])
    for row in case["events"]:
        queue.schedule(row["time_seconds"], Phase[row["phase"].upper()], row["kind"])
    seen: list[str] = []
    closed = False

    def handle(event: Event, _: EventQueue) -> None:
        nonlocal closed
        seen.append(event.kind)
        if event.kind == "close_shelter":
            closed = True
        elif event.kind == "arrive" and not closed:
            ledger.transition("group", PopulationState.UNLOADING, PopulationState.SHELTERED,
                              event.time_seconds, location_id="shelter")
        elif event.kind == "deadline":
            assert at_horizon(ledger, case["horizon_seconds"]).on_time_arrivals == 0
        ledger.assert_conserved()

    queue.run(handle)
    assert seen == case["expected_order"]
    assert ledger.get("group").state.value == case["expected_terminal_state"]
    assert at_horizon(ledger, case["horizon_seconds"]).deadline_missed == case[
        "expected_deadline_missed"]


def test_completion_exactly_at_deadline_and_horizon_counts_before_deadline() -> None:
    queue = EventQueue(10)
    queue.schedule(10, Phase.DEADLINE, "deadline", "group")
    queue.schedule(10, Phase.COMPLETION, "arrive", "group")
    arrived = False
    outcome: list[bool] = []

    def handle(event: Event, _: EventQueue) -> None:
        nonlocal arrived
        if event.kind == "arrive":
            arrived = True
        if event.kind == "deadline":
            outcome.append(arrived)

    queue.run(handle)
    assert outcome == [True]


def test_terminal_fires_with_empty_queue_and_future_work_remains() -> None:
    queue = EventQueue(10)
    queue.schedule(12, Phase.COMPLETION, "future_arrival")
    seen: list[str] = []
    queue.run(lambda event, _: seen.append(event.kind))
    assert seen == ["terminal"]
    assert [(event.time_seconds, event.kind) for event in queue.remaining] == [
        (12, "future_arrival")]


def test_stable_sequence_and_later_phase_scheduling() -> None:
    queue = EventQueue(10)
    queue.schedule(3, Phase.DISRUPTION, "b")
    queue.schedule(3, Phase.DISRUPTION, "a")
    seen: list[str] = []

    def handle(event: Event, scheduler: EventQueue) -> None:
        seen.append(event.kind)
        if event.kind == "b":
            scheduler.schedule(3, Phase.COMPLETION, "completion")

    queue.run(handle)
    assert seen == ["b", "a", "completion", "terminal"]


def test_same_phase_loop_past_event_and_horizon_replan_are_rejected() -> None:
    queue = EventQueue(10)
    queue.schedule(2, Phase.DEMAND, "demand")

    def handle(event: Event, scheduler: EventQueue) -> None:
        if event.kind == "demand":
            with pytest.raises(ValueError, match="advance time"):
                scheduler.schedule(2, Phase.DEMAND, "again")
            with pytest.raises(ValueError, match="advance time"):
                scheduler.schedule(1, Phase.REPLAN, "past")
            with pytest.raises(ValueError, match="horizon"):
                scheduler.schedule(10, Phase.REPLAN, "dispatch")

    queue.run(handle)


def test_same_time_event_cap_is_enforced() -> None:
    queue = EventQueue(10, max_events_per_time=2)
    queue.schedule(2, Phase.DISRUPTION, "first")
    queue.schedule(2, Phase.COMPLETION, "second")
    with pytest.raises(ValueError, match="limit"):
        queue.schedule(2, Phase.DEMAND, "third")
