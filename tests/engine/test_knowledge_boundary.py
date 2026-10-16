# Purpose: Verify knowledge boundary behavior for: Implement deterministic allocation and observed-condition replanning.
# Task: docs/plan.md 2.8.
# Uses: packages/simulation/kernel/disruptions.py, packages/simulation/kernel/observations.py, packages/simulation/policies/deadline_greedy.py.
# TODO(agent): implement

__all__ = ()
"""Future and unreported disruption knowledge cannot leak into decisions."""

from packages.simulation.kernel.disruptions import Disruption, DisruptionLedger
from packages.simulation.kernel.observations import ObservationLedger
from packages.simulation.kernel.population import PopulationState
from packages.simulation.kernel.resources import TripPhase
from packages.simulation.policies.deadline_greedy import allocate
from tests.engine.test_allocation import fixture


def test_future_closure_does_not_change_current_choice() -> None:
    candidates, population, resources, water = fixture()
    observations = ObservationLedger()
    disruptions = DisruptionLedger((
        Disruption("close", "edge_closed", "pickup-dry", 5, 7),
    ))
    assert disruptions.apply_due(0, resources, observations) == ()
    with_future = allocate(0, 20, candidates, population, resources, water, observations)
    baseline_candidates, baseline_population, baseline_resources, baseline_water = fixture()
    baseline = allocate(0, 20, baseline_candidates, baseline_population,
                        baseline_resources, baseline_water, ObservationLedger())
    assert with_future == baseline
    assert disruptions.apply_due(5, resources, observations) == ("close",)
    assert not disruptions.can_enter("pickup-dry")
    assert observations.visible(5) == ()
    assert len(observations.visible(7)) == 1


def test_observed_closure_blocks_candidate_and_existing_edge_travel_survives() -> None:
    candidates, population, resources, water = fixture()
    observations = ObservationLedger()
    disruptions = DisruptionLedger((
        Disruption("close", "edge_closed", "pickup-dry", 0, 0),
    ))
    disruptions.apply_due(0, resources, observations)
    result = allocate(0, 20, candidates, population, resources, water, observations)
    assert all(choice.plan.shelter_id == "wet" for choice in result.choices)
    # A closure prevents a new entry; it does not strand a vehicle already on the edge.
    trip = result.choices[0].plan.id
    resources.travel_edge(trip, 100, edge_id="depot-pickup", progress_mm=0,
                          location_id="pickup")
    assert resources.trips[trip].actual_distance_mm == 100


def test_explicit_vehicle_outage_strands_boarded_passengers() -> None:
    candidates, population, resources, water = fixture()
    chosen = allocate(0, 20, tuple(item for item in candidates
                                   if item.plan.cohort_id == "a"),
                      population, resources, water, ObservationLedger()).choices[0]
    trip = chosen.plan.id
    resources.travel_edge(trip, 100, edge_id="depot-pickup", progress_mm=0,
                          location_id="pickup")
    resources.pickup(trip, 1, population)
    resources.depart(trip, 2, population)
    disruption = DisruptionLedger((Disruption(
        "outage", "vehicle_outage", chosen.plan.vehicle_id, 3, 4,
    ),))
    observations = ObservationLedger()
    assert disruption.apply_due(3, resources, observations) == ("outage",)
    assert resources.trips[trip].phase is TripPhase.STRANDED
    assert population.get("a").state is PopulationState.IN_TRANSIT
    assert observations.visible(3) == ()
