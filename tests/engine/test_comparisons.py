# Purpose: Verify comparisons behavior for: Derive findings and paired comparison metrics.
# Task: docs/plan.md 2.11.
# Uses: packages/domain/comparisons/__init__.py, packages/domain/findings/__init__.py, packages/simulation/metrics/__init__.py.
# TODO(agent): implement

__all__ = ()
"""Identical-condition pairs expose improvements and newly introduced harm."""

from dataclasses import replace

from packages.contracts.outcomes import Outcome
from packages.domain.comparisons import MemberResult, PairedRun, compare_pairs


def run(*, variant: bool = False) -> PairedRun:
    first = Outcome(0 if not variant else 4, 0 if not variant else 4,
                    20 if not variant else 0, 4 if not variant else 0,
                    ("bridge-close", "trip-a"))
    second = Outcome(4, 0, 0 if not variant else 5, 0, ("trip-b",))
    return PairedRun(
        "b" * 64 if not variant else "v" * 64, ("s" * 64,), "c" * 64,
        "d" * 64, "e" * 64, "f" * 64, "deadline_greedy_v1",
        (MemberResult("disrupted", "1" * 64, "completed", first),
         MemberResult("other", "2" * 64, "completed", second)),
    )


def test_disrupted_pair_exposes_evidence_backed_delta_and_regression() -> None:
    result = compare_pairs(run(), run(variant=True), variant_baseline_hash="b" * 64)
    assert result.status == "complete"
    disrupted, other = result.deltas
    assert disrupted.member_id == "disrupted"
    assert (disrupted.on_time_people, disrupted.vulnerable_on_time_people,
            disrupted.water_unmet_ml, disrupted.stranded_people) == (4, 4, -20, -4)
    assert "bridge-close" in disrupted.evidence_event_ids
    assert other.regression_keys == ("water_unmet_ml",)
    assert not result.measured_improvement
    assert result.priority_label == "provisional"


def test_partial_model_change_and_untested_cannot_claim_improvement() -> None:
    before, after = run(), run(variant=True)
    partial = replace(after, members=(after.members[0],
                                      MemberResult("other", "2" * 64, "failed", None)))
    result = compare_pairs(before, partial, variant_baseline_hash=before.input_hash)
    assert result.status == "partial"
    assert result.excluded_member_ids == ("other",)
    assert not result.measured_improvement
    changed_engine = replace(after, engine_hash="9" * 64)
    assert compare_pairs(before, changed_engine,
                         variant_baseline_hash=before.input_hash).status == "non_comparable"
    assert compare_pairs(before, None).status == "untested"
