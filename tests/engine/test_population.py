"""Exclusive population states and hand-calculated terminal accounting."""

import json
from pathlib import Path

import pytest

from packages.contracts.operational import OperationalInputs
from packages.simulation.kernel import (
    PopulationLedger,
    PopulationSlice,
    PopulationState,
)
from packages.simulation.metrics.population import at_horizon

FIXTURE = Path(__file__).parents[1] / "fixtures/engine/boundaries/population-horizon.json"
OPERATIONAL = Path(__file__).parents[1] / "fixtures/inputs/operational.json"


def sample() -> tuple[dict, PopulationLedger]:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ledger = PopulationLedger(PopulationSlice(
        id=row["id"], source_cohort_id=row["id"], people=row["people"],
        state=PopulationState(row["state"]),
        request_time_seconds=row.get("request_time_seconds"),
        deadline_seconds=row.get("deadline_seconds"),
        location_id=row.get("location_id"), edge_id=row.get("edge_id"),
        edge_elapsed_seconds=row.get("edge_elapsed_seconds", 0),
        reservation_id=row.get("reservation_id"),
    ) for row in case["slices"])
    return case, ledger


def test_hand_calculated_horizon_accounting() -> None:
    case, ledger = sample()
    ledger.transition("arrival", PopulationState.UNLOADING, PopulationState.SHELTERED,
                      10, location_id="shelter")
    result = at_horizon(ledger, case["horizon_seconds"])
    expected = case["expected"]
    assert result.initial_people == expected["initial_people"]
    assert {state.value: people for state, people in result.by_state.items()} == expected["by_state"]
    for key in ("on_time_arrivals", "late_arrivals", "deadline_missed",
                "pending_after_horizon", "unfinished_movement", "unserved_demand"):
        assert getattr(result, key) == expected[key]
    assert ledger.get("unfinished").edge_id == "edge-1"
    assert ledger.get("unfinished").reservation_id == "seat-1"


def test_split_and_transition_preserve_each_initial_person() -> None:
    ledger = PopulationLedger([PopulationSlice("group", "original", 7, PopulationState.WAITING)])
    ledger.split("group", "vehicle", 3)
    ledger.transition("vehicle", PopulationState.WAITING, PopulationState.LOADING, 1)
    ledger.transition("vehicle", PopulationState.LOADING, PopulationState.IN_TRANSIT,
                      2, edge_id="edge-2", reservation_id="vehicle-1")
    assert [(item.id, item.people, item.state) for item in ledger.slices] == [
        ("group", 4, PopulationState.WAITING),
        ("vehicle", 3, PopulationState.IN_TRANSIT),
    ]
    assert ledger.initial_people == 7
    assert at_horizon(ledger, 3).unfinished_movement == 3


def test_duplicate_or_invalid_population_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PopulationLedger([PopulationSlice("same", "a", 1, PopulationState.WAITING),
                          PopulationSlice("same", "b", 2, PopulationState.WAITING)])
    with pytest.raises(ValueError, match="positive"):
        PopulationSlice("bad", "a", 0, PopulationState.WAITING)
    with pytest.raises(ValueError, match="node or edge"):
        PopulationSlice("bad", "a", 1, PopulationState.IN_TRANSIT)


def test_invalid_transition_and_split_leave_accounting_intact() -> None:
    ledger = PopulationLedger([PopulationSlice("a", "a", 2, PopulationState.WAITING)])
    with pytest.raises(ValueError, match="retain"):
        ledger.split("a", "b", 2)
    with pytest.raises(ValueError, match="stale"):
        ledger.transition("a", PopulationState.LOADING, PopulationState.SHELTERED, 1)
    with pytest.raises(ValueError, match="invalid population transition"):
        ledger.transition("a", PopulationState.WAITING, PopulationState.SHELTERED,
                          1, location_id="shelter")
    assert ledger.initial_people == 2
    ledger.assert_conserved()


def test_operational_initial_cohorts_are_loaded_once() -> None:
    inputs = OperationalInputs.model_validate_json(OPERATIONAL.read_text(encoding="utf-8"))
    ledger = PopulationLedger.from_cohorts(inputs.cohorts)
    assert ledger.initial_people == sum(cohort.people for cohort in inputs.cohorts)
    assert len(ledger.slices) == len(inputs.cohorts)
    for cohort in inputs.cohorts:
        assert ledger.get(str(cohort.id)).state.value == cohort.initial_state


def test_due_but_unactivated_demand_is_not_silently_discarded() -> None:
    ledger = PopulationLedger([PopulationSlice(
        "future", "future", 2, PopulationState.NOT_REQUESTED,
        request_time_seconds=4, deadline_seconds=7,
    )])
    with pytest.raises(ValueError, match="due demand"):
        at_horizon(ledger, 5)
