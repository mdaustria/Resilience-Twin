"""Absolute deadline order and a bounded exhaustive counterexample."""

from packages.application.experiments import enumerate_tiny_reference
from packages.simulation.kernel.observations import Observation, ObservationLedger
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
from packages.simulation.policies.earliest_deadline_reference import allocate_reference
from packages.simulation.routing.reference import RouteResult


def tiny() -> tuple[tuple[Candidate, ...], PopulationLedger, ResourceLedger, WaterLedger]:
    population = PopulationLedger((
        PopulationSlice("a", "a", 2, PopulationState.WAITING,
                        deadline_seconds=10, location_id="pickup"),
        PopulationSlice("b", "b", 4, PopulationState.WAITING,
                        deadline_seconds=8, location_id="pickup"),
    ))
    resources = ResourceLedger(
        (VehicleResource("v", "c", 4, (), (Window(0, 20),), 1000,
                         "depot", False),),
        (CrewResource("c", (Window(0, 20),)),),
        (ShelterResource("s", 4, 0, ()),),
    )
    water = WaterLedger((WaterStore("pickup", 100), WaterStore("s", 100)), (
        WaterCohort("a", 2, 86_400, "pickup"),
        WaterCohort("b", 4, 86_400, "pickup"),
    ))
    pickup = RouteResult("found", (), 0, 0)
    candidates = tuple(Candidate(TripPlan(
        f"trip-{cohort}", cohort, people, (), "v", "s", 0,
        pickup, 1, RouteResult("found", (f"edge-{cohort}",), travel, 100), 1,
    ), 0) for cohort, people, travel in (("a", 2, 7), ("b", 4, 0)))
    return candidates, population, resources, water


def test_reference_uses_absolute_deadline_and_shared_feasibility() -> None:
    candidates, population, resources, water = tiny()
    result = allocate_reference(0, 20, tuple(reversed(candidates)), population,
                                resources, water, ObservationLedger())
    assert result.policy_version == "earliest_deadline_reference_v1"
    assert tuple(choice.plan.cohort_id for choice in result.choices) == ("b",)
    assert result.uncovered_cohort_ids == ("a",)
    assert result.improvement_moves_evaluated == 0
    assert resources.shelters["s"].reserved_people == 4
    other, pop2, res2, water2 = tiny()
    greedy = allocate(0, 20, other, pop2, res2, water2, ObservationLedger())
    assert tuple(choice.plan.cohort_id for choice in greedy.choices) == ("a",)
    assert greedy.choices[0].on_time_people == 2


def test_tiny_enumeration_quantifies_a_policy_limit_not_global_optimality() -> None:
    candidates, population, resources, _ = tiny()
    reference = enumerate_tiny_reference(candidates, population, resources)
    assert reference.combinations_evaluated == 4
    assert reference.maximum_on_time_people == 4
    assert reference.best_trip_ids == ("trip-b",)
    assert reference.scope_label == "tiny_static_candidate_set_not_global_optimum"


def test_observed_closure_and_budget_apply_to_reference() -> None:
    candidates, population, resources, water = tiny()
    known = ObservationLedger((Observation("closed", "edge_closed", "edge-b", 0, 0),))
    result = allocate_reference(0, 20, candidates, population, resources, water, known)
    assert tuple(choice.plan.id for choice in result.choices) == ("trip-a",)
    other, pop2, res2, water2 = tiny()
    limited = allocate_reference(0, 20, other, pop2, res2, water2,
                                 ObservationLedger(), max_candidate_evaluations=1)
    assert limited.candidate_budget_exhausted
    assert limited.candidates_evaluated == 1
