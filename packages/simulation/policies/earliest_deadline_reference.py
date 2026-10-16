"""Deterministic absolute-deadline reference using the shared feasibility gate."""

from collections import defaultdict

from packages.simulation.kernel.observations import ObservationLedger
from packages.simulation.kernel.population import PopulationLedger, PopulationState
from packages.simulation.kernel.resources import ResourceLedger
from packages.simulation.kernel.water import WaterLedger
from packages.simulation.policies.deadline_greedy import (
    AllocationChoice,
    AllocationResult,
    Candidate,
    projected_shelter_shortfall,
)
from packages.simulation.policies.feasibility import check_trip, dispatch

REFERENCE_POLICY_VERSION = "earliest_deadline_reference_v1"


def allocate_reference(
    now_seconds: int, horizon_seconds: int, candidates: tuple[Candidate, ...],
    population: PopulationLedger, resources: ResourceLedger, water: WaterLedger,
    observations: ObservationLedger, *, max_candidate_evaluations: int = 10_000,
) -> AllocationResult:
    """Choose earliest absolute deadlines without local improvement moves."""
    if type(now_seconds) is not int or type(horizon_seconds) is not int or not (
        0 <= now_seconds <= horizon_seconds
    ):
        raise ValueError("allocation time must be within a nonnegative horizon")
    if type(max_candidate_evaluations) is not int or max_candidate_evaluations <= 0:
        raise ValueError("candidate evaluation budget must be a positive integer")
    ready = {item.id: item for item in population.slices
             if item.state is PopulationState.WAITING}
    if now_seconds == horizon_seconds:
        return AllocationResult((), tuple(sorted(ready)), 0, 0, False,
                                REFERENCE_POLICY_VERSION)
    visible = observations.visible(now_seconds)
    closed_edges = {item.target_id for item in visible if item.kind == "edge_closed"}
    closed_assets = {item.target_id for item in visible if item.kind == "asset_closed"}
    ordered = sorted(candidates, key=lambda item: (
        item.plan.cohort_id, item.plan.vehicle_id, item.plan.shelter_id, item.plan.id,
    ))
    options: dict[str, list[Candidate]] = defaultdict(list)
    priorities: dict[str, int] = {}
    for candidate in ordered[:max_candidate_evaluations]:
        plan = candidate.plan
        if plan.cohort_id not in ready or plan.dispatch_seconds != now_seconds:
            continue
        legs = (plan.pickup_route, plan.passenger_route, plan.return_route)
        if (any(edge_id in closed_edges for leg in legs if leg is not None
                for edge_id in leg.edge_ids)
                or any(asset_id in closed_assets for asset_id in candidate.route_asset_ids)):
            continue
        if check_trip(plan, resources, population).feasible:
            options[plan.cohort_id].append(candidate)
            priorities[plan.cohort_id] = candidate.assistance_priority
    cohort_order = sorted(ready, key=lambda cohort_id: (
        ready[cohort_id].deadline_seconds
        if ready[cohort_id].deadline_seconds is not None else 10**18,
        -priorities.get(cohort_id, 0), cohort_id,
    ))
    choices: list[AllocationChoice] = []
    uncovered: list[str] = []
    for cohort_id in cohort_order:
        cohort = ready[cohort_id]
        feasible = []
        for candidate in options.get(cohort_id, ()):
            evaluation = check_trip(candidate.plan, resources, population)
            if not evaluation.feasible or evaluation.timing is None:
                continue
            timing = evaluation.timing
            deficit = projected_shelter_shortfall(
                candidate.plan.shelter_id, now_seconds, horizon_seconds, resources,
                water, (candidate.plan, timing),
            )
            on_time = candidate.plan.people if (
                cohort.deadline_seconds is None
                or timing.unloaded_seconds <= cohort.deadline_seconds
            ) else 0
            travel = ((candidate.plan.pickup_route.travel_seconds or 0)
                      + (candidate.plan.passenger_route.travel_seconds or 0))
            rank = (-on_time, deficit, timing.unloaded_seconds, travel,
                    candidate.plan.vehicle_id, candidate.plan.shelter_id,
                    candidate.plan.id)
            feasible.append((rank, candidate, timing, deficit, on_time))
        if not feasible:
            uncovered.append(cohort_id)
            continue
        _, chosen, timing, deficit, on_time = min(feasible, key=lambda item: item[0])
        dispatch(chosen.plan, resources, population)
        choices.append(AllocationChoice(chosen.plan, timing, on_time, deficit))
    return AllocationResult(
        tuple(choices), tuple(uncovered), min(len(ordered), max_candidate_evaluations),
        0, len(ordered) > max_candidate_evaluations, REFERENCE_POLICY_VERSION,
    )


__all__ = ("REFERENCE_POLICY_VERSION", "allocate_reference")
