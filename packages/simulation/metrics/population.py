"""Population outcomes derived from exclusive states at a given horizon."""

from dataclasses import dataclass

from packages.simulation.kernel.population import PopulationLedger, PopulationState


@dataclass(frozen=True)
class PopulationMetrics:
    initial_people: int
    by_state: dict[PopulationState, int]
    on_time_arrivals: int
    late_arrivals: int
    deadline_missed: int
    pending_after_horizon: int
    unfinished_movement: int
    unserved_demand: int


def at_horizon(ledger: PopulationLedger, horizon_seconds: int) -> PopulationMetrics:
    if type(horizon_seconds) is not int or horizon_seconds < 0:
        raise ValueError("horizon must be nonnegative integer seconds")
    ledger.assert_conserved()
    counts = {state: 0 for state in PopulationState}
    on_time = late = missed = pending = unfinished = unserved = 0
    for item in ledger.slices:
        counts[item.state] += item.people
        if item.state is PopulationState.SHELTERED:
            if item.arrival_time_seconds is not None:
                if item.arrival_time_seconds > horizon_seconds:
                    raise ValueError("arrival after horizon cannot be counted")
                if item.deadline_seconds is None or item.arrival_time_seconds <= item.deadline_seconds:
                    on_time += item.people
                else:
                    late += item.people
                    missed += item.people
            continue
        if item.state is PopulationState.NOT_REQUESTED:
            if item.request_time_seconds is not None and item.request_time_seconds <= horizon_seconds:
                raise ValueError("due demand was not activated by the horizon")
            continue
        unserved += item.people
        if item.state in (PopulationState.LOADING, PopulationState.IN_TRANSIT, PopulationState.UNLOADING):
            unfinished += item.people
        if item.deadline_seconds is not None:
            if item.deadline_seconds <= horizon_seconds:
                missed += item.people
            else:
                pending += item.people
    if sum(counts.values()) != ledger.initial_people:
        raise AssertionError("population conservation failed")
    return PopulationMetrics(
        ledger.initial_people, counts, on_time, late, missed, pending, unfinished, unserved,
    )


__all__ = ("PopulationMetrics", "at_horizon")
