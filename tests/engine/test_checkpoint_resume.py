# Purpose: Verify checkpoint resume behavior for: Add serializable checkpoints and deterministic replay.
# Task: docs/plan.md 2.9.
# Uses: packages/contracts/checkpoints.py, packages/simulation/kernel/checkpoints.py, packages/simulation/runner.py.
# TODO(agent): implement

__all__ = ()
"""Resume after a movement boundary and before final water exhaustion."""

import pytest

from packages.contracts.checkpoints import RunCheckpoint
from packages.simulation.kernel.checkpoints import restore_state
from packages.simulation.runner import run_simulation
from tests.engine.test_replay import MANIFEST, handler, resumed


@pytest.mark.parametrize("count", [2, 5])
def test_resume_matches_uninterrupted_event_and_metric_hashes(count: int) -> None:
    full, continued = resumed(count)
    assert (continued.event_hash, continued.metric_hash) == (
        full.event_hash, full.metric_hash,
    )
    assert continued.events == full.events
    assert continued.metrics == full.metrics
    if count == 5:
        assert full.checkpoint is not None
        _, _, _, water, _ = restore_state(full.checkpoint.state)
        assert water.store("dry").exhaustion_time_seconds == 5
        assert water.cohort("a").unmet_ml == 12
        duplicate = run_simulation(MANIFEST, handler, checkpoint=full.checkpoint)
        assert duplicate == continued


def test_checkpoint_rejects_tampering_and_wrong_manifest() -> None:
    full, _ = resumed(2)
    assert full.checkpoint is not None
    raw = full.checkpoint.model_dump()
    raw["events"][0]["kind"] = "changed"
    with pytest.raises(ValueError, match="checksum"):
        RunCheckpoint.model_validate(raw)
    with pytest.raises(ValueError, match="manifest"):
        run_simulation("b" * 64, handler, checkpoint=full.checkpoint)
