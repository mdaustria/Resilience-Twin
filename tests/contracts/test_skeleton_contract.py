"""Contract and hand-calculated checks for the bounded synthetic engine case."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.contracts.skeleton import SkeletonCase
from packages.simulation.skeleton import calculate_skeleton

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/skeleton/cases.json"


def case_data() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"][0]["case"]


def test_hand_calculated_one_trip_water_result() -> None:
    case = SkeletonCase.model_validate(case_data())
    result = calculate_skeleton(case)
    assert result.schema_version == "skeleton.result.v1"
    assert result.initial_people == 10
    assert result.arrived_people == 6
    assert result.unserved_people == 4
    assert result.arrival_time_seconds == 300
    assert result.water_required_ml == 6000
    assert result.water_used_ml == 4000
    assert result.water_shortfall_ml == 2000
    assert result.water_sufficient_people == 4
    assert result.water_remaining_ml == 0
    assert result.source_label == case.source_label
    assert result.assumption_label == case.assumption_label
    assert result == calculate_skeleton(case)


def test_unfinished_trip_does_not_become_an_arrival() -> None:
    case = SkeletonCase.model_validate(case_data()).model_copy(
        update={"horizon_seconds": 299}
    )
    result = calculate_skeleton(case)
    assert result.arrived_people == 0
    assert result.unserved_people == case.cohort_people
    assert result.arrival_time_seconds is None
    assert result.water_shortfall_ml == 0


@pytest.mark.parametrize(
    "change",
    [
        {"cohort_people": None},
        {"cohort_people": -1},
        {"cohort_people": "10"},
        {"arrival_water_need_ml_per_person": 0},
        {"schema_version": "unknown"},
        {"unspecified_resource": 1},
    ],
)
def test_invalid_or_missing_operational_input_is_rejected(change: dict[str, object]) -> None:
    values = case_data()
    values.update(change)
    if change.get("cohort_people") is None and "cohort_people" in change:
        del values["cohort_people"]
    with pytest.raises(ValidationError):
        SkeletonCase.model_validate(values)
