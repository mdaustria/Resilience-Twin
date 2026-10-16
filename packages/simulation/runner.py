"""Deterministic local runner with portable checkpoint/resume and canonical hashes."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from packages.contracts.checkpoints import (
    RunCheckpoint,
    canonical_json,
    seal_checkpoint,
)
from packages.simulation.kernel.checkpoints import capture_state, encode, restore_state
from packages.simulation.kernel.events import Event, EventQueue, Phase
from packages.simulation.kernel.observations import ObservationLedger
from packages.simulation.kernel.population import PopulationLedger
from packages.simulation.kernel.resources import ResourceLedger
from packages.simulation.kernel.water import WaterLedger
from packages.simulation.metrics.population import at_horizon
from packages.simulation.metrics.water import summarize


@dataclass
class RunState:
    queue: EventQueue
    population: PopulationLedger
    resources: ResourceLedger
    water: WaterLedger
    observations: ObservationLedger


@dataclass(frozen=True)
class RunResult:
    event_hash: str
    metric_hash: str
    events: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    checkpoint: RunCheckpoint | None


Handler = Callable[[Event, RunState], None]


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def run_simulation(
    manifest_hash: str, handler: Handler, *, state: RunState | None = None,
    checkpoint: RunCheckpoint | None = None, checkpoint_after_events: int | None = None,
    on_checkpoint: Callable[[RunCheckpoint], None] | None = None,
) -> RunResult:
    if (state is None) == (checkpoint is None):
        raise ValueError("provide exactly one initial state or checkpoint")
    if checkpoint_after_events is not None and (
        type(checkpoint_after_events) is not int or checkpoint_after_events <= 0
    ):
        raise ValueError("checkpoint event count must be positive")
    if checkpoint is not None:
        verified = RunCheckpoint.model_validate_json(checkpoint.model_dump_json())
        if verified.manifest_hash != manifest_hash:
            raise ValueError("checkpoint manifest mismatch")
        state = RunState(*restore_state(verified.state))
        event_log = list(verified.events)
        if verified.sequence != len(event_log):
            raise ValueError("checkpoint event sequence mismatch")
    else:
        event_log = []
    assert state is not None
    captured: RunCheckpoint | None = None

    def process(event: Event, _queue: EventQueue) -> None:
        nonlocal captured
        state.water.advance(event.time_seconds)
        handler(event, state)
        state.population.assert_conserved()
        state.resources.assert_invariants()
        state.water.assert_balanced()
        event_log.append({"time_seconds": event.time_seconds, "phase": int(event.phase),
                          "sequence": event.stable_sequence, "kind": event.kind,
                          "target_id": event.target_id})
        if (checkpoint_after_events == len(event_log) and event.phase is not Phase.TERMINAL):
            captured = seal_checkpoint(
                manifest_hash, len(event_log), capture_state(
                    state.queue, state.population, state.resources,
                    state.water, state.observations,
                ), list(event_log),
            )
            if on_checkpoint is not None:
                on_checkpoint(captured)

    state.queue.run(process)
    metrics: dict[str, Any] = {
        "population": encode(at_horizon(state.population, state.queue.horizon_seconds)),
        "water": encode(summarize(state.water)),
    }
    return RunResult(_hash(event_log), _hash(metrics), tuple(event_log), metrics, captured)


__all__ = ("RunResult", "RunState", "run_simulation")
