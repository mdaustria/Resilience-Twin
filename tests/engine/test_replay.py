# Purpose: Verify replay behavior for: Add serializable checkpoints and deterministic replay.
# Task: docs/plan.md 2.9.
# Uses: packages/contracts/checkpoints.py, packages/simulation/kernel/checkpoints.py, packages/simulation/runner.py.
# TODO(agent): implement

__all__ = ()
"""Canonical replay over pinned synthetic inputs."""

from packages.simulation.kernel.events import Event, EventQueue, Phase
from packages.simulation.kernel.observations import ObservationLedger
from packages.simulation.policies.deadline_greedy import allocate
from packages.simulation.runner import RunResult, RunState, run_simulation
from tests.engine.test_allocation import fixture

MANIFEST = "a" * 64


def setup_run() -> RunState:
    candidates, population, resources, water = fixture()
    chosen = allocate(0, 20, tuple(item for item in candidates
                                   if item.plan.cohort_id == "a"),
                      population, resources, water, ObservationLedger()).choices[0]
    assert chosen.plan.shelter_id == "dry"
    queue = EventQueue(20)
    for time_seconds, kind in ((1, "pickup"), (2, "depart"),
                               (4, "arrive"), (5, "admit")):
        queue.schedule(time_seconds, Phase.COMPLETION, kind, chosen.plan.id)
    queue.schedule(8, Phase.WATER, "water_boundary")
    return RunState(queue, population, resources, water, ObservationLedger())


def handler(event: Event, state: RunState) -> None:
    if event.kind in ("terminal", "water_boundary"):
        return
    assert event.target_id is not None
    trip = event.target_id
    if event.kind == "pickup":
        state.resources.travel_edge(trip, 100, edge_id="depot-pickup", progress_mm=0,
                                    location_id="pickup")
        state.resources.pickup(trip, event.time_seconds, state.population)
    elif event.kind == "depart":
        state.resources.depart(trip, event.time_seconds, state.population)
    elif event.kind == "arrive":
        state.resources.travel_edge(trip, 100, edge_id="pickup-dry", progress_mm=0,
                                    location_id="dry")
        state.resources.begin_unload(trip, event.time_seconds, state.population)
    elif event.kind == "admit":
        assert state.resources.admit(trip, event.time_seconds,
                                     state.population, state.water)


def test_identical_pinned_runs_have_identical_event_and_metric_hashes() -> None:
    first = run_simulation(MANIFEST, handler, state=setup_run())
    second = run_simulation(MANIFEST, handler, state=setup_run())
    assert first == second
    assert first.event_hash != first.metric_hash
    assert len(first.events) == 6


def resumed(checkpoint_after_events: int) -> tuple[RunResult, RunResult]:
    uninterrupted = run_simulation(MANIFEST, handler, state=setup_run(),
                                   checkpoint_after_events=checkpoint_after_events)
    assert uninterrupted.checkpoint is not None
    from_json = uninterrupted.checkpoint.model_dump_json()
    from packages.contracts.checkpoints import RunCheckpoint
    restored = RunCheckpoint.model_validate_json(from_json)
    continued = run_simulation(MANIFEST, handler, checkpoint=restored)
    return uninterrupted, continued
