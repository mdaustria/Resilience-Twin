"""Typed terminal quantities used by paired comparisons."""

from packages.contracts.outcomes import Outcome
from packages.simulation.kernel.population import PopulationLedger, PopulationState
from packages.simulation.kernel.resources import ResourceLedger, TripPhase
from packages.simulation.kernel.water import WaterLedger
from packages.simulation.metrics.population import at_horizon
from packages.simulation.metrics.water import summarize


def terminal_outcome(
    population: PopulationLedger, resources: ResourceLedger,
    water: WaterLedger, horizon_seconds: int,
    vulnerable_cohort_ids: frozenset[str], evidence_event_ids: tuple[str, ...],
) -> Outcome:
    metrics = at_horizon(population, horizon_seconds)
    vulnerable = sum(item.people for item in population.slices
                     if item.id in vulnerable_cohort_ids
                     and item.state is PopulationState.SHELTERED
                     and item.arrival_time_seconds is not None
                     and (item.deadline_seconds is None
                          or item.arrival_time_seconds <= item.deadline_seconds))
    stranded_ids = {record.plan.cohort_id for record in resources.trips.values()
                    if record.phase is TripPhase.STRANDED}
    stranded = sum(item.people for item in population.slices if item.id in stranded_ids)
    return Outcome(metrics.on_time_arrivals, vulnerable, summarize(water).unmet_ml,
                   stranded, tuple(sorted(set(evidence_event_ids))))


__all__ = ("Outcome", "terminal_outcome")
