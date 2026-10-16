"""Structured target checks and independent frozen suite streams."""

import pytest

from packages.contracts.scenarios import Scenario, ScenarioEvent
from packages.domain.scenarios import (
    freeze_suite,
    independent_draw,
    suite_hash,
    validate_scenario,
)


def event(target: str) -> ScenarioEvent:
    return ScenarioEvent("closure-" + target, "edge_closed", target, 5, 8, "synthetic-hazard")


def test_invalid_target_count_and_event_time_fail() -> None:
    with pytest.raises(ValueError, match="target"):
        validate_scenario(Scenario("s", 20, (event("missing"),)),
                          edge_ids=frozenset({"edge"}), asset_ids=frozenset(),
                          vehicle_ids=frozenset(), shelter_ids=frozenset())
    with pytest.raises(ValueError, match="capacity"):
        ScenarioEvent("bad", "shelter_capacity", "shelter", 5, 5,
                      "synthetic-hazard", -1)
    with pytest.raises(ValueError, match="horizon"):
        Scenario("s", 4, (event("edge"),))


def test_unrelated_entity_does_not_shift_existing_seeded_draws() -> None:
    original = (event("edge-a"), event("edge-b"))
    expanded = original + (event("unrelated"),)
    first = freeze_suite("suite", 42, 20, ("member-a", "member-b"), original, 1, 2)
    second = freeze_suite("suite", 42, 20, ("member-a", "member-b"), expanded, 1, 2)
    assert first == freeze_suite("suite", 42, 20, ("member-a", "member-b"),
                                 tuple(reversed(original)), 1, 2)
    for before, after in zip(first.members, second.members, strict=True):
        assert {item.id for item in before.scenario.events} == (
            {item.id for item in after.scenario.events} & {item.id for item in original}
        )
    assert suite_hash(first) == suite_hash(freeze_suite(
        "suite", 42, 20, ("member-a", "member-b"), original, 1, 2,
    ))
    assert independent_draw(42, "member-a", "edge_closed", "edge-a") != (
        independent_draw(42, "member-a", "edge_closed", "edge-b")
    )
