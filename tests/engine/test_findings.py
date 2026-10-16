# Purpose: Verify findings behavior for: Derive findings and paired comparison metrics.
# Task: docs/plan.md 2.11.
# Uses: packages/domain/comparisons/__init__.py, packages/domain/findings/__init__.py, packages/simulation/metrics/__init__.py.
# TODO(agent): implement

__all__ = ()
"""Occurrences have stable evidence, distinct people and evaluable recurrence."""

import pytest

from packages.domain.findings import Occurrence, derive_findings


def test_repeated_events_do_not_inflate_cohorts_or_recurrence() -> None:
    occurrences = (
        Occurrence("m1", "blocked_route", "bridge", "a", 4, "close-1"),
        Occurrence("m1", "blocked_route", "bridge", "a", 4, "retry-1"),
        Occurrence("m2", "blocked_route", "bridge", "b", 3, "close-2"),
    )
    result = derive_findings(occurrences, ("m1", "m2"), ("m1", "m2", "m3"),
                             {"a": 4, "b": 3})[0]
    assert result.key == "blocked_route:bridge"
    assert result.affected_cohort_ids == ("a", "b")
    assert result.distinct_affected_people == 7
    assert (result.recurrence_numerator, result.recurrence_denominator) == (2, 2)
    assert result.planned_members == 3
    assert result.incomplete_member_ids == ("m3",)
    assert result.evidence_event_ids == ("close-1", "close-2", "retry-1")
    assert result.priority_label == "provisional"


def test_failed_member_and_impossible_count_cannot_supply_finding() -> None:
    with pytest.raises(ValueError, match="unevaluable"):
        derive_findings((Occurrence("failed", "water", "s", "a", 2, "e"),),
                        (), ("failed",), {"a": 2})
    with pytest.raises(ValueError, match="exceeds"):
        derive_findings((Occurrence("m", "water", "s", "a", 3, "e"),),
                        ("m",), ("m",), {"a": 2})
