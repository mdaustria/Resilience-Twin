"""One pure feasibility gate before committing a trip reservation."""

from dataclasses import dataclass, replace

from packages.simulation.kernel.population import PopulationLedger, PopulationState
from packages.simulation.kernel.resources import (
    ResourceLedger,
    TripPhase,
    TripPlan,
    TripTiming,
)
from packages.simulation.routing.reference import RouteResult


@dataclass(frozen=True)
class TripEvaluation:
    feasible: bool
    reasons: tuple[str, ...]
    timing: TripTiming | None


def _route_values(route: RouteResult | None) -> tuple[int, int] | None:
    if route is None or route.status != "found":
        return None
    if route.travel_seconds is None or route.distance_mm is None:
        return None
    if route.travel_seconds < 0 or route.distance_mm < 0:
        return None
    return route.travel_seconds, route.distance_mm


def check_trip(
    plan: TripPlan, resources: ResourceLedger, population: PopulationLedger,
) -> TripEvaluation:
    """Check routes, seats, needs, windows, occupancy and distance atomically."""
    reasons: list[str] = []
    vehicle = resources.vehicles.get(plan.vehicle_id)
    shelter = resources.shelters.get(plan.shelter_id)
    if vehicle is None:
        reasons.append("unknown_vehicle")
    if shelter is None:
        reasons.append("unknown_shelter")
    try:
        cohort = population.get(plan.cohort_id)
    except KeyError:
        cohort = None
        reasons.append("unknown_cohort")
    if plan.id in resources.trips:
        reasons.append("duplicate_trip")
    if any(
        record.plan.cohort_id == plan.cohort_id
        and record.phase not in (TripPhase.CANCELLED, TripPhase.COMPLETED)
        for record in resources.trips.values()
    ):
        reasons.append("cohort_already_reserved")
    pickup = _route_values(plan.pickup_route)
    passenger = _route_values(plan.passenger_route)
    returning = _route_values(plan.return_route) if plan.return_route is not None else (0, 0)
    if pickup is None:
        reasons.append("pickup_route_unavailable")
    if passenger is None:
        reasons.append("passenger_route_unavailable")
    if plan.return_route is not None and returning is None:
        reasons.append("return_route_unavailable")
    if vehicle is not None and vehicle.resource.return_required and plan.return_route is None:
        reasons.append("return_route_required")
    timing = None
    if pickup is not None and passenger is not None and returning is not None:
        pickup_at = plan.dispatch_seconds + pickup[0]
        loaded_at = pickup_at + plan.loading_seconds
        shelter_at = loaded_at + passenger[0]
        unloaded_at = shelter_at + plan.unloading_seconds
        release_at = unloaded_at + returning[0]
        timing = TripTiming(
            pickup_at, loaded_at, shelter_at, unloaded_at, release_at,
            pickup[1] + passenger[1] + returning[1],
        )
    if cohort is not None and (
        cohort.state is not PopulationState.WAITING or cohort.people != plan.people
        or set(cohort.assistance_needs) != set(plan.assistance_needs)
    ):
        reasons.append("cohort_not_ready_or_count_mismatch")
    if vehicle is not None:
        if vehicle.disabled or vehicle.active_trip_id is not None:
            reasons.append("vehicle_unavailable")
        if plan.people > vehicle.resource.seats:
            reasons.append("vehicle_seats_exceeded")
        if not set(plan.assistance_needs) <= set(vehicle.resource.supported_needs):
            reasons.append("vehicle_assistance_unsupported")
        crew = resources.crews.get(vehicle.resource.crew_id)
        if crew is None or resources.crew_trips[vehicle.resource.crew_id] is not None:
            reasons.append("crew_unavailable")
        if timing is not None:
            if not any(window.covers(plan.dispatch_seconds, timing.release_seconds)
                       for window in vehicle.resource.availability):
                reasons.append("vehicle_window_exceeded")
            if crew is not None and not any(
                window.covers(plan.dispatch_seconds, timing.release_seconds)
                for window in crew.availability
            ):
                reasons.append("crew_window_exceeded")
            if (vehicle.consumed_distance_mm + vehicle.reserved_distance_mm
                    + timing.planned_distance_mm > vehicle.resource.distance_budget_mm):
                reasons.append("distance_budget_exceeded")
    if shelter is not None:
        if not set(plan.assistance_needs) <= set(shelter.resource.permitted_needs):
            reasons.append("shelter_assistance_unsupported")
        if (shelter.occupancy_people + shelter.reserved_people + plan.people
                > shelter.capacity_people):
            reasons.append("shelter_capacity_exceeded")
    return TripEvaluation(not reasons, tuple(reasons), timing)


def dispatch(
    plan: TripPlan, resources: ResourceLedger, population: PopulationLedger,
) -> TripTiming:
    result = check_trip(plan, resources, population)
    if not result.feasible or result.timing is None:
        raise ValueError(f"trip infeasible: {', '.join(result.reasons)}")
    resources._reserve(plan, result.timing)
    return result.timing


def check_reroute(
    trip_id: str, shelter_id: str, passenger_route: RouteResult,
    return_route: RouteResult | None, now_seconds: int,
    resources: ResourceLedger, population: PopulationLedger,
) -> TripEvaluation:
    """Recheck a boarded trip from its current reviewed node after disruption."""
    reasons: list[str] = []
    record = resources.trips.get(trip_id)
    shelter = resources.shelters.get(shelter_id)
    if record is None:
        return TripEvaluation(False, ("unknown_trip",), None)
    vehicle = resources.vehicles[record.plan.vehicle_id]
    cohort = population.get(record.plan.cohort_id)
    if record.phase not in (TripPhase.IN_TRANSIT, TripPhase.STRANDED):
        reasons.append("trip_not_reroutable")
    if cohort.state is not PopulationState.IN_TRANSIT:
        reasons.append("passengers_not_in_transit")
    if vehicle.disabled or vehicle.edge_id is not None:
        reasons.append("vehicle_unavailable_or_on_edge")
    if type(now_seconds) is not int or now_seconds < record.timing.loaded_seconds:
        reasons.append("invalid_reroute_time")
    if shelter is None:
        reasons.append("unknown_shelter")
    route = _route_values(passenger_route)
    returning = _route_values(return_route) if return_route is not None else (0, 0)
    if route is None:
        reasons.append("passenger_route_unavailable")
    if return_route is not None and returning is None:
        reasons.append("return_route_unavailable")
    if vehicle.resource.return_required and return_route is None:
        reasons.append("return_route_required")
    timing = None
    if route is not None and returning is not None and type(now_seconds) is int:
        shelter_at = now_seconds + route[0]
        unloaded_at = shelter_at + record.plan.unloading_seconds
        release_at = unloaded_at + returning[0]
        remaining_distance = route[1] + returning[1]
        timing = replace(
            record.timing, shelter_arrival_seconds=shelter_at,
            unloaded_seconds=unloaded_at, release_seconds=release_at,
            planned_distance_mm=record.actual_distance_mm + remaining_distance,
        )
        if not any(window.covers(record.plan.dispatch_seconds, release_at)
                   for window in vehicle.resource.availability):
            reasons.append("vehicle_window_exceeded")
        crew = resources.crews[vehicle.resource.crew_id]
        if not any(window.covers(record.plan.dispatch_seconds, release_at)
                   for window in crew.availability):
            reasons.append("crew_window_exceeded")
        if vehicle.consumed_distance_mm + remaining_distance > vehicle.resource.distance_budget_mm:
            reasons.append("distance_budget_exceeded")
    if shelter is not None:
        own_reservation = (
            record.reserved_shelter_people if record.plan.shelter_id == shelter_id else 0
        )
        if (shelter.occupancy_people + shelter.reserved_people - own_reservation
                + record.plan.people > shelter.capacity_people):
            reasons.append("shelter_capacity_exceeded")
        if not set(record.plan.assistance_needs) <= set(shelter.resource.permitted_needs):
            reasons.append("shelter_assistance_unsupported")
    return TripEvaluation(not reasons, tuple(reasons), timing)


def reroute(
    trip_id: str, shelter_id: str, passenger_route: RouteResult,
    return_route: RouteResult | None, now_seconds: int,
    resources: ResourceLedger, population: PopulationLedger,
) -> TripTiming:
    result = check_reroute(
        trip_id, shelter_id, passenger_route, return_route, now_seconds,
        resources, population,
    )
    if not result.feasible or result.timing is None:
        raise ValueError(f"reroute infeasible: {', '.join(result.reasons)}")
    record = resources.trips[trip_id]
    plan = replace(
        record.plan, shelter_id=shelter_id, passenger_route=passenger_route,
        return_route=return_route,
    )
    resources._replace_route(
        trip_id, plan, result.timing,
        result.timing.planned_distance_mm - record.actual_distance_mm,
    )
    return result.timing


__all__ = ("TripEvaluation", "check_reroute", "check_trip", "dispatch", "reroute")
