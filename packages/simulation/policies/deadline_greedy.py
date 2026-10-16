"""Bounded deterministic greedy allocation using only observed conditions."""

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass

from packages.simulation.kernel.observations import ObservationLedger
from packages.simulation.kernel.population import PopulationLedger, PopulationState
from packages.simulation.kernel.resources import ResourceLedger, TripPlan, TripTiming
from packages.simulation.kernel.water import SECONDS_PER_DAY, WaterLedger
from packages.simulation.policies.feasibility import check_trip, dispatch

POLICY_VERSION = "deadline_greedy_v1"


@dataclass(frozen=True)
class Candidate:
    plan: TripPlan
    assistance_priority: int
    route_asset_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.assistance_priority) is not int or self.assistance_priority < 0:
            raise ValueError("assistance priority must be a nonnegative integer")


@dataclass(frozen=True)
class AllocationChoice:
    plan: TripPlan
    timing: TripTiming
    on_time_people: int
    projected_shelter_shortfall_ml: int


@dataclass(frozen=True)
class AllocationResult:
    choices: tuple[AllocationChoice, ...]
    uncovered_cohort_ids: tuple[str, ...]
    candidates_evaluated: int
    improvement_moves_evaluated: int
    candidate_budget_exhausted: bool
    policy_version: str = POLICY_VERSION


def projected_shelter_shortfall(
    shelter_id: str, now_seconds: int, horizon_seconds: int,
    resources: ResourceLedger, water: WaterLedger,
    extra: tuple[TripPlan, TripTiming] | None = None,
) -> int:
    """Estimate post-arrival demand from current inventory and known inbound trips."""
    if horizon_seconds < now_seconds:
        raise ValueError("horizon precedes current time")
    store = water.store(shelter_id)  # Missing inventory is unknown, never zero.
    demand = 0
    included: set[str] = set()
    for cohort in water.cohorts:
        if cohort.supply_id != shelter_id:
            continue
        included.add(cohort.id)
        numerator = (cohort.remainder_numerator + cohort.people
                     * cohort.ml_per_person_day * (horizon_seconds - now_seconds))
        demand += numerator // SECONDS_PER_DAY
    for record in sorted(resources.trips.values(), key=lambda item: item.plan.id):
        if record.plan.shelter_id != shelter_id or not record.reserved_shelter_people:
            continue
        if record.plan.cohort_id in included:
            continue
        cohort = water.cohort(record.plan.cohort_id)
        remaining = max(0, horizon_seconds - max(now_seconds, record.timing.unloaded_seconds))
        demand += (cohort.remainder_numerator + cohort.people
                   * cohort.ml_per_person_day * remaining) // SECONDS_PER_DAY
        included.add(cohort.id)
    if extra is not None and extra[0].shelter_id == shelter_id:
        plan, timing = extra
        if plan.cohort_id not in included:
            cohort = water.cohort(plan.cohort_id)
            remaining = max(0, horizon_seconds - max(now_seconds, timing.unloaded_seconds))
            demand += (cohort.remainder_numerator + cohort.people
                       * cohort.ml_per_person_day * remaining) // SECONDS_PER_DAY
    return max(0, demand - store.remaining_ml)


def _known_closed(observations: ObservationLedger, now_seconds: int) -> tuple[set[str], set[str]]:
    closed_edges = {item.target_id for item in observations.visible(now_seconds)
                    if item.kind == "edge_closed"}
    closed_assets = {item.target_id for item in observations.visible(now_seconds)
                     if item.kind == "asset_closed"}
    return closed_edges, closed_assets


def _route_blocked(candidate: Candidate, closed_edges: set[str], closed_assets: set[str]) -> bool:
    legs = (candidate.plan.pickup_route, candidate.plan.passenger_route,
            candidate.plan.return_route)
    return any(edge_id in closed_edges for leg in legs if leg is not None
               for edge_id in leg.edge_ids) or any(
        asset_id in closed_assets for asset_id in candidate.route_asset_ids
    )


def _rank(
    candidate: Candidate, timing: TripTiming, deficit: int, deadline: int | None,
) -> tuple[int, int, int, int, str, str, str]:
    on_time = candidate.plan.people if (
        deadline is None or timing.unloaded_seconds <= deadline
    ) else 0
    travel = (candidate.plan.pickup_route.travel_seconds or 0) + (
        candidate.plan.passenger_route.travel_seconds or 0
    )
    return (-on_time, deficit, timing.unloaded_seconds, travel,
            candidate.plan.vehicle_id, candidate.plan.shelter_id, candidate.plan.id)


def allocate(
    now_seconds: int, horizon_seconds: int, candidates: tuple[Candidate, ...],
    population: PopulationLedger, resources: ResourceLedger, water: WaterLedger,
    observations: ObservationLedger, *, max_candidate_evaluations: int = 10_000,
    max_improvement_moves: int = 16,
) -> AllocationResult:
    if type(now_seconds) is not int or not 0 <= now_seconds <= horizon_seconds:
        raise ValueError("allocation time must be within the horizon")
    if max_candidate_evaluations <= 0 or max_improvement_moves < 0:
        raise ValueError("iteration budgets must be bounded nonnegative integers")
    ready = {item.id: item for item in population.slices
             if item.state is PopulationState.WAITING}
    if now_seconds == horizon_seconds:
        return AllocationResult((), tuple(sorted(ready)), 0, 0, False)
    closed_edges, closed_assets = _known_closed(observations, now_seconds)
    ordered = sorted(candidates, key=lambda item: (
        item.plan.cohort_id, item.plan.vehicle_id,
        item.plan.shelter_id, item.plan.id,
    ))
    options: dict[str, list[Candidate]] = defaultdict(list)
    evaluated = 0
    for candidate in ordered[:max_candidate_evaluations]:
        evaluated += 1
        plan = candidate.plan
        if plan.cohort_id not in ready or plan.dispatch_seconds != now_seconds:
            continue
        if _route_blocked(candidate, closed_edges, closed_assets):
            continue
        if check_trip(plan, resources, population).feasible:
            options[plan.cohort_id].append(candidate)
    priorities = {item.plan.cohort_id: item.assistance_priority for item in ordered
                  if item.plan.cohort_id in ready}
    def cohort_rank(cohort_id: str) -> tuple[int, int, int, str]:
        cohort = ready[cohort_id]
        deadline = cohort.deadline_seconds
        best_slack = min((deadline - result.timing.unloaded_seconds
                          for option in options.get(cohort_id, ())
                          if deadline is not None
                          for result in (check_trip(option.plan, resources, population),)
                          if result.timing is not None), default=10**18)
        return (best_slack, -priorities.get(cohort_id, 0),
                deadline if deadline is not None else 10**18, cohort_id)
    order = sorted(ready, key=cohort_rank)

    def simulate(overrides: dict[str, str]) -> tuple[
        tuple[AllocationChoice, ...], tuple[str, ...], tuple[int, int, int, int, int]
    ]:
        trial = deepcopy(resources)
        selected: list[AllocationChoice] = []
        uncovered: list[str] = []
        for cohort_id in order:
            cohort = ready[cohort_id]
            feasible: list[tuple[tuple[int, int, int, int, str, str, str], Candidate,
                                 TripTiming, int]] = []
            for candidate in options.get(cohort_id, ()):
                evaluation = check_trip(candidate.plan, trial, population)
                if not evaluation.feasible or evaluation.timing is None:
                    continue
                deficit = projected_shelter_shortfall(
                    candidate.plan.shelter_id, now_seconds, horizon_seconds,
                    trial, water, (candidate.plan, evaluation.timing),
                )
                feasible.append((
                    _rank(candidate, evaluation.timing, deficit, cohort.deadline_seconds),
                    candidate, evaluation.timing, deficit,
                ))
            feasible.sort(key=lambda item: item[0])
            override = overrides.get(cohort_id)
            if override is not None:
                feasible.sort(key=lambda item: (item[1].plan.id != override, item[0]))
            if not feasible:
                uncovered.append(cohort_id)
                continue
            _, chosen, timing, deficit = feasible[0]
            dispatch(chosen.plan, trial, population)
            on_time = chosen.plan.people if (
                cohort.deadline_seconds is None or timing.unloaded_seconds <= cohort.deadline_seconds
            ) else 0
            selected.append(AllocationChoice(chosen.plan, timing, on_time, deficit))
        missed = sum(
            item.people for item in ready.values()
            if item.deadline_seconds is not None and item.deadline_seconds <= horizon_seconds
            and not any(choice.plan.cohort_id == item.id and choice.on_time_people == item.people
                        for choice in selected)
        )
        vulnerable_missed = sum(
            item.people for item in ready.values()
            if priorities.get(item.id, 0) > 0 and item.deadline_seconds is not None
            and item.deadline_seconds <= horizon_seconds
            and not any(choice.plan.cohort_id == item.id and choice.on_time_people == item.people
                        for choice in selected)
        )
        deficit = sum(projected_shelter_shortfall(
            shelter_id, now_seconds, horizon_seconds, trial, water,
        ) for shelter_id in sorted({choice.plan.shelter_id for choice in selected}))
        travel = sum(choice.timing.planned_distance_mm for choice in selected)
        return tuple(selected), tuple(uncovered), (
            missed, vulnerable_missed, len(uncovered), deficit, travel,
        )

    best_choices, best_uncovered, best_score = simulate({})
    attempts = 0
    improved = True
    while improved and attempts < max_improvement_moves:
        improved = False
        for cohort_id in order:
            if attempts >= max_improvement_moves:
                break
            current = next((choice.plan.id for choice in best_choices
                            if choice.plan.cohort_id == cohort_id), None)
            for option in options.get(cohort_id, ()):
                if option.plan.id == current or attempts >= max_improvement_moves:
                    continue
                attempts += 1
                choices, uncovered, score = simulate({cohort_id: option.plan.id})
                if score < best_score:
                    best_choices, best_uncovered, best_score = choices, uncovered, score
                    improved = True
                    break
            if improved:
                break
    for choice in best_choices:
        dispatch(choice.plan, resources, population)
    return AllocationResult(
        best_choices, best_uncovered, evaluated, attempts,
        len(ordered) > max_candidate_evaluations,
    )


__all__ = (
    "POLICY_VERSION",
    "AllocationChoice",
    "AllocationResult",
    "Candidate",
    "allocate",
    "projected_shelter_shortfall",
)
