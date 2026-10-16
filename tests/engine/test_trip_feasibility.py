"""Full-cycle trip feasibility against hand-calculated resource limits."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from packages.simulation.kernel.population import (
    PopulationLedger,
    PopulationSlice,
    PopulationState,
)
from packages.simulation.kernel.resources import (
    CrewResource,
    ResourceLedger,
    ShelterResource,
    TripPlan,
    VehicleResource,
    Window,
)
from packages.simulation.policies.feasibility import check_trip, dispatch
from packages.simulation.routing.reference import RouteResult

FIXTURE = Path(__file__).parents[1] / "fixtures/engine/resources/trip-small.json"
CASE = json.loads(FIXTURE.read_text(encoding="utf-8"))


def route(row: dict) -> RouteResult:
    return RouteResult("found", tuple(row["edge_ids"]), row["travel_seconds"], row["distance_mm"])


def setup() -> tuple[TripPlan, ResourceLedger, PopulationLedger]:
    v, c, s, t = (CASE[key] for key in ("vehicle", "crew", "shelter", "trip"))
    vehicle = VehicleResource(
        v["id"], v["crew_id"], v["seats"], tuple(v["supported_needs"]),
        tuple(Window(*window) for window in v["availability"]),
        v["distance_budget_mm"], v["initial_location_id"], v["return_required"],
    )
    crew = CrewResource(c["id"], tuple(Window(*window) for window in c["availability"]))
    shelter = ShelterResource(
        s["id"], s["capacity_people"], s["initial_occupancy_people"],
        tuple(s["permitted_needs"]),
    )
    plan = TripPlan(
        t["id"], t["cohort_id"], t["people"], tuple(t["assistance_needs"]),
        t["vehicle_id"], t["shelter_id"], t["dispatch_seconds"],
        route(t["pickup_route"]), t["loading_seconds"],
        route(t["passenger_route"]), t["unloading_seconds"],
        route(t["return_route"]),
    )
    population = PopulationLedger([PopulationSlice(
        "group", "group", 4, PopulationState.WAITING,
        assistance_needs=("wheelchair",), location_id="pickup",
    )])
    return plan, ResourceLedger((vehicle,), (crew,), (shelter,)), population


def test_hand_calculated_empty_loading_passenger_unloading_return_cycle() -> None:
    plan, resources, population = setup()
    evaluation = check_trip(plan, resources, population)
    assert evaluation.feasible
    assert evaluation.timing is not None
    for key, value in CASE["expected"].items():
        assert getattr(evaluation.timing, key) == value
    dispatch(plan, resources, population)
    assert resources.shelters["shelter"].reserved_people == 4
    assert resources.vehicles["vehicle"].reserved_distance_mm == 800
    resources.travel_edge("trip", 100, edge_id="depot-pickup", progress_mm=0,
                          location_id="pickup")
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    resources.travel_edge("trip", 400, edge_id="pickup-shelter", progress_mm=0,
                          location_id="shelter")
    resources.begin_unload("trip", 18, population)
    assert resources.admit("trip", 20, population)
    assert resources.crew_trips["crew"] == "trip"
    assert resources.shelters["shelter"].occupancy_people == 6
    resources.travel_edge("trip", 300, edge_id="shelter-depot", progress_mm=0,
                          location_id="depot")
    resources.finish_return("trip", 28)
    assert resources.vehicles["vehicle"].consumed_distance_mm == 800
    assert resources.vehicles["vehicle"].reserved_distance_mm == 0
    assert resources.crew_trips["crew"] is None
    assert population.get("group").state is PopulationState.SHELTERED
    population.assert_conserved()


@pytest.mark.parametrize("change,reason", [
    ("seats", "vehicle_seats_exceeded"),
    ("needs", "vehicle_assistance_unsupported"),
    ("crew_window", "crew_window_exceeded"),
    ("vehicle_window", "vehicle_window_exceeded"),
    ("budget", "distance_budget_exceeded"),
    ("shelter", "shelter_capacity_exceeded"),
])
def test_limit_is_checked_before_any_reservation(change: str, reason: str) -> None:
    plan, resources, population = setup()
    vehicle = resources.vehicles["vehicle"]
    if change == "seats":
        resources.vehicles["vehicle"] = replace(
            vehicle, resource=replace(vehicle.resource, seats=3),
        )
    elif change == "needs":
        resources.vehicles["vehicle"] = replace(
            vehicle, resource=replace(vehicle.resource, supported_needs=()),
        )
    elif change == "crew_window":
        resources.crews["crew"] = replace(resources.crews["crew"], availability=(Window(0, 27),))
    elif change == "vehicle_window":
        resources.vehicles["vehicle"] = replace(
            vehicle, resource=replace(vehicle.resource, availability=(Window(0, 27),)),
        )
    elif change == "budget":
        resources.vehicles["vehicle"] = replace(
            vehicle, resource=replace(vehicle.resource, distance_budget_mm=799),
        )
    else:
        resources.shelters["shelter"] = replace(resources.shelters["shelter"], capacity_people=5)
    assert reason in check_trip(plan, resources, population).reasons
    with pytest.raises(ValueError, match="infeasible"):
        dispatch(plan, resources, population)
    assert resources.shelters["shelter"].reserved_people == 0
    assert resources.vehicles["vehicle"].active_trip_id is None


def test_unreachable_route_and_missing_return_are_not_feasible() -> None:
    plan, resources, population = setup()
    unreachable = RouteResult("unreachable", (), None, None)
    assert "passenger_route_unavailable" in check_trip(
        replace(plan, passenger_route=unreachable), resources, population,
    ).reasons
    assert "return_route_required" in check_trip(
        replace(plan, return_route=None), resources, population,
    ).reasons


def test_exact_window_end_and_distance_budget_are_inclusive() -> None:
    plan, resources, population = setup()
    vehicle = resources.vehicles["vehicle"]
    resources.vehicles["vehicle"] = replace(
        vehicle, resource=replace(vehicle.resource, availability=(Window(0, 28),)),
    )
    resources.crews["crew"] = replace(
        resources.crews["crew"], availability=(Window(0, 28),),
    )
    assert check_trip(plan, resources, population).feasible
    assert dispatch(plan, resources, population).release_seconds == 28
