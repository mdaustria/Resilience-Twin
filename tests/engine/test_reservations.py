"""Concurrent reservations, disruptions, reroutes and stranded people."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from test_trip_feasibility import setup

from packages.contracts.operational import OperationalInputs

OPERATIONAL = Path(__file__).parents[1] / "fixtures/inputs/operational.json"

from packages.simulation.kernel.population import (
    PopulationLedger,
    PopulationSlice,
    PopulationState,
)
from packages.simulation.kernel.resources import (
    CrewResource,
    ResourceLedger,
    ShelterResource,
    TripPhase,
    Window,
)
from packages.simulation.kernel.water import WaterCohort, WaterLedger, WaterStore
from packages.simulation.policies.feasibility import (
    check_reroute,
    check_trip,
    dispatch,
    reroute,
)
from packages.simulation.routing.reference import RouteResult


def test_concurrent_trips_cannot_double_book_vehicle_crew_or_shelter() -> None:
    plan, original, _ = setup()
    vehicle = original.vehicles["vehicle"].resource
    shared_crew_vehicle = replace(vehicle, id="vehicle-2")
    separate_vehicle = replace(vehicle, id="vehicle-3", crew_id="crew-3")
    resources = ResourceLedger(
        (vehicle, shared_crew_vehicle, separate_vehicle),
        (original.crews["crew"], CrewResource("crew-3", (Window(0, 30),))),
        (original.shelters["shelter"].resource,
         ShelterResource("alternate", 4, 0, ("wheelchair",))),
    )
    population = PopulationLedger(PopulationSlice(
        group, group, 4, PopulationState.WAITING,
        assistance_needs=("wheelchair",), location_id="pickup",
    ) for group in ("group", "group-2", "group-3"))
    dispatch(plan, resources, population)
    busy_vehicle = replace(plan, id="trip-2", cohort_id="group-2", shelter_id="alternate")
    assert "vehicle_unavailable" in check_trip(busy_vehicle, resources, population).reasons
    shared_crew = replace(busy_vehicle, vehicle_id="vehicle-2")
    assert "crew_unavailable" in check_trip(shared_crew, resources, population).reasons
    full_shelter = replace(shared_crew, id="trip-3", cohort_id="group-3",
                           vehicle_id="vehicle-3", shelter_id="shelter")
    assert "shelter_capacity_exceeded" in check_trip(full_shelter, resources, population).reasons
    assert resources.shelters["shelter"].reserved_people == 4
    assert resources.crew_trips["crew"] == "trip"


def test_cancellation_releases_unused_reservations_but_not_spent_distance() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.travel_edge("trip", 50, edge_id="depot-pickup", progress_mm=50,
                          location_id="depot")
    resources.cancel("trip")
    vehicle = resources.vehicles["vehicle"]
    assert vehicle.consumed_distance_mm == 50
    assert vehicle.reserved_distance_mm == 0
    assert vehicle.active_trip_id is None
    assert resources.shelters["shelter"].reserved_people == 0
    assert population.get("group").state is PopulationState.WAITING
    assert resources.trips["trip"].phase is TripPhase.CANCELLED


def test_vehicle_outage_keeps_onboard_passengers_and_progress_stranded() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    resources.travel_edge("trip", 120, edge_id="pickup-shelter", progress_mm=120,
                          location_id="road-node")
    resources.outage("vehicle")
    assert resources.trips["trip"].phase is TripPhase.STRANDED
    assert resources.vehicles["vehicle"].active_trip_id == "trip"
    assert resources.vehicles["vehicle"].edge_id == "pickup-shelter"
    assert resources.shelters["shelter"].reserved_people == 0
    assert population.get("group").state is PopulationState.IN_TRANSIT
    assert population.get("group").people == 4
    assert population.get("group").reservation_id == "trip"
    with pytest.raises(ValueError, match="reroute infeasible"):
        reroute("trip", "shelter", plan.passenger_route, plan.return_route,
                9, resources, population)
    population.assert_conserved()


def test_shelter_disruption_strands_inbound_then_valid_reroute_reserves_again() -> None:
    plan, resources, population = setup()
    resources.shelters["alternate"] = replace(
        resources.shelters["shelter"],
        resource=ShelterResource("alternate", 4, 0, ("wheelchair",)),
        capacity_people=4, occupancy_people=0, reserved_people=0,
    )
    dispatch(plan, resources, population)
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    resources.set_shelter_capacity("shelter", 2)
    assert resources.trips["trip"].phase is TripPhase.STRANDED
    assert population.get("group").state is PopulationState.IN_TRANSIT
    assert resources.shelters["shelter"].reserved_people == 0
    new_route = RouteResult("found", ("node-alternate",), 8, 300)
    result = check_reroute("trip", "alternate", new_route, plan.return_route,
                           9, resources, population)
    assert result.feasible
    timing = reroute("trip", "alternate", new_route, plan.return_route,
                     9, resources, population)
    assert (timing.shelter_arrival_seconds, timing.unloaded_seconds,
            timing.release_seconds) == (17, 19, 27)
    assert resources.shelters["alternate"].reserved_people == 4
    resources.begin_unload("trip", 17, population)
    water = WaterLedger(
        (WaterStore("pickup", 0), WaterStore("alternate", 0)),
        (WaterCohort("group", 4, 86_400, "pickup"),),
    )
    assert resources.admit("trip", 19, population, water)
    assert water.cohort("group").supply_id == "alternate"
    assert population.get("group").state is PopulationState.SHELTERED
    assert resources.shelters["alternate"].occupancy_people == 4
    population.assert_conserved()


def test_capacity_drop_preserves_initial_occupants_and_cancels_unboarded_trip() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.set_shelter_capacity("shelter", 1)
    shelter = resources.shelters["shelter"]
    assert shelter.occupancy_people == 2
    assert shelter.forced_overload_people == 1
    assert shelter.relocation_demand_people == 1
    assert shelter.reserved_people == 0
    assert resources.trips["trip"].phase is TripPhase.CANCELLED
    assert population.get("group").state is PopulationState.WAITING
    population.assert_conserved()


def test_reroute_cannot_extend_crew_window_or_distance_budget() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    slow = RouteResult("found", ("slow",), 20, 400)
    assert "crew_window_exceeded" in check_reroute(
        "trip", "shelter", slow, plan.return_route, 9, resources, population,
    ).reasons
    long = RouteResult("found", ("long",), 5, 600)
    assert "distance_budget_exceeded" in check_reroute(
        "trip", "shelter", long, plan.return_route, 9, resources, population,
    ).reasons
    assert resources.trips["trip"].remaining_distance_mm == 800
    assert resources.shelters["shelter"].reserved_people == 4


def test_reroute_waits_until_vehicle_finishes_its_current_edge() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    resources.travel_edge("trip", 50, edge_id="pickup-shelter", progress_mm=50,
                          location_id="pickup")
    result = check_reroute("trip", "shelter", plan.passenger_route,
                           plan.return_route, 9, resources, population)
    assert "vehicle_unavailable_or_on_edge" in result.reasons
    assert population.get("group").state is PopulationState.IN_TRANSIT


def test_initial_shelter_occupants_derive_from_distinct_operational_cohorts() -> None:
    inputs = OperationalInputs.model_validate_json(OPERATIONAL.read_text(encoding="utf-8"))
    resources = ResourceLedger.from_operational_inputs(inputs)
    expected = {str(item.id): sum(
        cohort.people for cohort in inputs.cohorts
        if cohort.initial_state == "sheltered" and cohort.shelter_id == item.id
    ) for item in inputs.shelters}
    assert {key: shelter.occupancy_people for key, shelter in resources.shelters.items()} == expected
    resources.assert_invariants()


def test_unknown_initial_shelter_never_discards_occupants() -> None:
    inputs = OperationalInputs.model_validate_json(OPERATIONAL.read_text(encoding="utf-8"))
    initial = next(cohort for cohort in inputs.cohorts if cohort.initial_state == "sheltered")
    altered = inputs.model_copy(update={
        "cohorts": tuple(
            cohort.model_copy(update={"shelter_id": UUID(int=999)})
            if cohort.id == initial.id else cohort for cohort in inputs.cohorts
        ),
    })
    with pytest.raises(ValueError, match="unknown shelter"):
        ResourceLedger.from_operational_inputs(altered)


def test_missing_arrival_water_source_leaves_passengers_unloading() -> None:
    plan, resources, population = setup()
    dispatch(plan, resources, population)
    resources.pickup("trip", 5, population)
    resources.depart("trip", 8, population)
    resources.begin_unload("trip", 18, population)
    water = WaterLedger((WaterStore("pickup", 0),), (
        WaterCohort("group", 4, 86_400, "pickup"),
    ))
    with pytest.raises(KeyError):
        resources.admit("trip", 20, population, water)
    assert population.get("group").state is PopulationState.UNLOADING
    assert resources.shelters["shelter"].occupancy_people == 2
    assert resources.shelters["shelter"].reserved_people == 4
