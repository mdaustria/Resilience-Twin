# Purpose: Verify allocation behavior for: Implement deterministic allocation and observed-condition replanning.
# Task: docs/plan.md 2.8.
# Uses: packages/simulation/kernel/disruptions.py, packages/simulation/kernel/observations.py, packages/simulation/policies/deadline_greedy.py.
# TODO(agent): implement

__all__ = ()
"""Hand-calculated deadline, resource and water decisions."""

from dataclasses import replace

from packages.simulation.kernel.observations import ObservationLedger
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
from packages.simulation.kernel.water import WaterCohort, WaterLedger, WaterStore
from packages.simulation.policies.deadline_greedy import Candidate, allocate
from packages.simulation.policies.feasibility import check_trip, dispatch
from packages.simulation.routing.reference import RouteResult


def fixture() -> tuple[tuple[Candidate, ...], PopulationLedger, ResourceLedger, WaterLedger]:
    vehicles = tuple(VehicleResource(
        f"v{index}", f"c{index}", 4, (), (Window(0, 100),), 1000, "depot", False,
    ) for index in (1, 2))
    resources = ResourceLedger(
        vehicles,
        tuple(CrewResource(f"c{index}", (Window(0, 100),)) for index in (1, 2)),
        (ShelterResource("dry", 8, 0, ()), ShelterResource("wet", 8, 0, ())),
    )
    population = PopulationLedger((
        PopulationSlice("a", "a", 4, PopulationState.WAITING,
                        deadline_seconds=6, location_id="pickup"),
        PopulationSlice("b", "b", 4, PopulationState.WAITING,
                        deadline_seconds=20, location_id="pickup"),
    ))
    water = WaterLedger(
        (WaterStore("pickup", 100), WaterStore("dry", 0), WaterStore("wet", 100)),
        (WaterCohort("a", 4, 86_400, "pickup"),
         WaterCohort("b", 4, 86_400, "pickup")),
    )
    empty = RouteResult("found", ("depot-pickup",), 1, 100)
    candidates = tuple(Candidate(TripPlan(
        f"{cohort}-{vehicle}-{shelter}", cohort, 4, (), vehicle, shelter, 0,
        empty, 1, RouteResult("found", (f"pickup-{shelter}",),
                              2 if shelter == "dry" else 8, 100), 1,
    ), 1 if cohort == "a" else 0) for cohort in ("a", "b")
        for vehicle in ("v1", "v2") for shelter in ("dry", "wet"))
    return candidates, population, resources, water


def test_deadline_first_deterministic_and_water_shortfall_visible() -> None:
    candidates, population, resources, water = fixture()
    result = allocate(0, 20, candidates, population, resources, water, ObservationLedger(),
                      max_improvement_moves=4)
    assert tuple(choice.plan.cohort_id for choice in result.choices) == ("a", "b")
    assert result.choices[0].plan.shelter_id == "dry"
    assert result.choices[0].timing.unloaded_seconds == 5
    assert result.choices[0].on_time_people == 4
    assert result.choices[0].projected_shelter_shortfall_ml == 60
    assert result.improvement_moves_evaluated <= 4
    assert resources.shelters["dry"].reserved_people == 4
    other, pop2, res2, water2 = fixture()
    replay = allocate(0, 20, tuple(reversed(other)), pop2, res2, water2,
                      ObservationLedger(), max_improvement_moves=4)
    assert result == replay


def test_pending_pickup_reserves_cohort_exclusively() -> None:
    candidates, population, resources, _ = fixture()
    first = next(item.plan for item in candidates if item.plan.id == "a-v1-dry")
    second = replace(first, id="a-v2-dry", vehicle_id="v2")
    dispatch(first, resources, population)
    assert "cohort_already_reserved" in check_trip(second, resources, population).reasons


def test_candidate_budget_is_explicit() -> None:
    candidates, population, resources, water = fixture()
    result = allocate(0, 20, candidates, population, resources, water,
                      ObservationLedger(), max_candidate_evaluations=1,
                      max_improvement_moves=0)
    assert result.candidates_evaluated == 1
    assert result.candidate_budget_exhausted
    assert result.uncovered_cohort_ids == ("b",)


def test_safety_first_admission_preserves_measured_water_deficit() -> None:
    candidates, population, resources, water = fixture()
    chosen = allocate(0, 20, tuple(item for item in candidates
                                   if item.plan.cohort_id == "a"),
                      population, resources, water, ObservationLedger()).choices[0]
    assert chosen.plan.shelter_id == "dry"
    resources.travel_edge(chosen.plan.id, 100, edge_id="depot-pickup", progress_mm=0,
                          location_id="pickup")
    resources.pickup(chosen.plan.id, 1, population)
    resources.depart(chosen.plan.id, 2, population)
    water.advance(4)
    resources.travel_edge(chosen.plan.id, 100, edge_id="pickup-dry", progress_mm=0,
                          location_id="dry")
    resources.begin_unload(chosen.plan.id, 4, population)
    water.advance(5)
    assert resources.admit(chosen.plan.id, 5, population, water)
    water.advance(20)
    assert population.get("a").state is PopulationState.SHELTERED
    assert water.cohort("a").unmet_ml == 60
