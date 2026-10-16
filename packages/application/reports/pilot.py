"""Reproducible, explicitly hypothetical pilot proof on a pinned road graph."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from packages.contracts.outcomes import Outcome
from packages.domain.comparisons import MemberResult, PairedRun, compare_pairs
from packages.simulation.kernel.disruptions import Disruption, DisruptionLedger
from packages.simulation.kernel.events import Event, EventQueue, Phase
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
from packages.simulation.policies.deadline_greedy import (
    POLICY_VERSION,
    Candidate,
    allocate,
)
from packages.simulation.routing.reference import RoadGraph, RouteResult, shortest_route
from packages.simulation.runner import RunResult, RunState, run_simulation

HORIZON = 3 * 86_400
ENGINE_VERSION = "pilot-runner-v1"


@dataclass(frozen=True)
class PilotMember:
    member_id: str
    route_seconds: int
    route_distance_mm: int
    route_edge_ids: tuple[str, ...]
    result: RunResult
    outcome: Outcome


@dataclass(frozen=True)
class PilotProof:
    case: str
    scope_hash: str
    graph_hash: str
    source_hash: str
    closed_edge_id: str
    deadline_seconds: int
    baseline: tuple[PilotMember, ...]
    variant: tuple[PilotMember, ...]
    comparison_status: str
    comparison_deltas: tuple[dict[str, object], ...]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _member(graph: RoadGraph, start: str, end: str, member_id: str,
            closed_edge: str, deadline: int, extra_water_ml: int) -> PilotMember:
    disruption = DisruptionLedger((Disruption("road-close", "edge_closed", closed_edge, 0, 0),)
                                  if member_id == "road_close" else ())
    route = shortest_route(graph, start, end, "car",
                           closed_edges=frozenset({closed_edge}) if member_id == "road_close"
                           else frozenset())
    if route.status != "found" or route.travel_seconds is None or route.distance_mm is None:
        raise ValueError(f"{member_id} route is unresolved")
    queue = EventQueue(HORIZON)
    population = PopulationLedger((
        PopulationSlice("pilot-trip", "pilot-cohort", 20, PopulationState.WAITING,
                        request_time_seconds=0, deadline_seconds=deadline, location_id="pickup"),
        PopulationSlice("pilot-waiting", "pilot-cohort", 80, PopulationState.WAITING,
                        request_time_seconds=0, deadline_seconds=deadline, location_id="pickup"),
    ))
    resources = ResourceLedger(
        (VehicleResource("vehicle", "crew", 20, (), (Window(0, HORIZON),),
                         5_000_000, "pickup", False),),
        (CrewResource("crew", (Window(0, HORIZON),)),),
        (ShelterResource("shelter", 150, 0, ()),),
    )
    water = WaterLedger((WaterStore("pickup", 100_000 + extra_water_ml),
                         WaterStore("shelter", 400_000)),
                        (WaterCohort("pilot-trip", 20, 2_000, "pickup"),
                         WaterCohort("pilot-waiting", 80, 2_000, "pickup")))
    observations = ObservationLedger()
    state = RunState(queue, population, resources, water, observations)
    if member_id == "road_close":
        queue.schedule(0, Phase.DISRUPTION, "road_close", closed_edge)
    queue.schedule(0, Phase.REPLAN, "allocate")
    selection: dict[str, object] = {}

    def handle(event: Event, current: RunState) -> None:
        if event.kind == "road_close":
            disruption.apply_due(event.time_seconds, current.resources, current.observations)
        elif event.kind == "allocate":
            plan = TripPlan("pilot-trip-plan", "pilot-trip", 20, (), "vehicle", "shelter", 0,
                            RouteResult("found", (), 1, 0), 1, route, 1)
            allocation = allocate(0, HORIZON, (Candidate(plan, 0),), current.population,
                                  current.resources, current.water, current.observations)
            if len(allocation.choices) != 1:
                raise AssertionError("pilot trip was not allocated")
            choice = allocation.choices[0]
            selection["timing"] = choice.timing
            queue.schedule(choice.timing.pickup_seconds, Phase.COMPLETION, "pickup")
            queue.schedule(choice.timing.loaded_seconds, Phase.COMPLETION, "depart")
            queue.schedule(choice.timing.shelter_arrival_seconds, Phase.COMPLETION, "arrive")
            queue.schedule(choice.timing.unloaded_seconds, Phase.COMPLETION, "admit")
        elif event.kind == "pickup":
            current.resources.pickup("pilot-trip-plan", event.time_seconds, current.population)
        elif event.kind == "depart":
            current.resources.depart("pilot-trip-plan", event.time_seconds, current.population)
        elif event.kind == "arrive":
            if any(not disruption.can_enter(edge_id) for edge_id in route.edge_ids):
                raise AssertionError("planned route enters a closed edge")
            current.resources.travel_edge("pilot-trip-plan", route.distance_mm or 0,
                                          edge_id=route.edge_ids[-1], progress_mm=0,
                                          location_id="shelter")
            current.resources.begin_unload("pilot-trip-plan", event.time_seconds,
                                           current.population)
        elif event.kind == "admit" and not current.resources.admit(
            "pilot-trip-plan", event.time_seconds, current.population, current.water,
        ):
            raise AssertionError("pilot shelter refused reserved trip")

    result = run_simulation(_digest(f"{member_id}:{extra_water_ml}:pilot-v1"), handle, state=state)
    metrics = result.metrics
    outcome = Outcome(metrics["population"]["$fields"]["on_time_arrivals"], 0,
                      metrics["water"]["$fields"]["unmet_ml"], 0,
                      tuple(f"{item['sequence']}:{item['kind']}" for item in result.events))
    return PilotMember(member_id, route.travel_seconds, route.distance_mm,
                       route.edge_ids, result, outcome)


def run_pilot_proof(graph: RoadGraph, *, case: str, start: str, end: str,
                    closed_edge: str, deadline: int, scope_hash: str,
                    graph_hash: str, source_hash: str) -> PilotProof:
    """Compare an opening-water change over the same normal/road-closure suite."""
    base_route = shortest_route(graph, start, end, "car")
    if closed_edge not in base_route.edge_ids:
        raise ValueError("closure must affect the baseline path")
    baseline = tuple(_member(graph, start, end, member, closed_edge, deadline, 0)
                     for member in ("normal", "road_close"))
    variant = tuple(_member(graph, start, end, member, closed_edge, deadline, 500_000)
                    for member in ("normal", "road_close"))
    suite_hash = _digest(f"{case}:{scope_hash}:{closed_edge}:normal,road_close")

    def paired(members: tuple[PilotMember, ...], water: int) -> PairedRun:
        return PairedRun(
            _digest(f"{case}:{scope_hash}:{water}"), (source_hash,), suite_hash,
            scope_hash, graph_hash, _digest(ENGINE_VERSION), POLICY_VERSION,
            tuple(MemberResult(item.member_id,
                               _digest(f"{suite_hash}:{item.member_id}"),
                               "completed", item.outcome) for item in members),
        )

    before = paired(baseline, 500_000)
    after = paired(variant, 1_000_000)
    comparison = compare_pairs(before, after, variant_baseline_hash=before.input_hash)
    if comparison.status != "complete":
        raise AssertionError("pilot comparison is incomplete")
    return PilotProof(case, scope_hash, graph_hash, source_hash, closed_edge, deadline,
                      baseline, variant, comparison.status,
                      tuple(asdict(item) for item in comparison.deltas))


__all__ = ("PilotMember", "PilotProof", "run_pilot_proof")
