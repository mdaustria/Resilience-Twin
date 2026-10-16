"""Exact integer water accounting, source tracking and final interval."""

import json
from pathlib import Path

import pytest

from packages.contracts.operational import OperationalInputs
from packages.simulation.kernel import EventQueue, Phase
from packages.simulation.kernel.water import (
    WaterCohort,
    WaterLedger,
    WaterStore,
    run_with_water,
)
from packages.simulation.metrics.water import summarize

FIXTURE = Path(__file__).parents[1] / "fixtures/engine/water/final-interval.json"
OPERATIONAL = Path(__file__).parents[1] / "fixtures/inputs/operational.json"


def sample() -> tuple[dict, WaterLedger]:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    water = WaterLedger(
        (WaterStore(**row) for row in case["stores"]),
        (WaterCohort(**row) for row in case["cohorts"]),
    )
    return case, water


def test_empty_queue_still_integrates_terminal_final_interval() -> None:
    case, water = sample()
    queue = EventQueue(case["horizon_seconds"])
    seen: list[str] = []
    run_with_water(queue, water, lambda event, _: seen.append(event.kind))
    result = summarize(water)
    expected = case["expected"]
    assert seen == ["terminal"]
    assert water.time_seconds == case["horizon_seconds"]
    for key in ("initial_ml", "consumed_ml", "remaining_ml", "unmet_ml",
                "exhaustion_by_store", "unmet_by_cohort"):
        assert getattr(result, key) == expected[key]
    assert water.cohort("waiting").remainder_numerator == expected[
        "waiting_remainder_numerator"]
    assert not result.sufficient_for("initial")
    assert result.sufficient_for("waiting")


def test_intermediate_event_does_not_skip_last_interval() -> None:
    _, water = sample()
    queue = EventQueue(5)
    queue.schedule(2, Phase.DEMAND, "observation")
    states: list[tuple[int, int]] = []
    run_with_water(queue, water, lambda event, _: states.append(
        (event.time_seconds, summarize(water).consumed_ml),
    ))
    assert states == [(2, 5), (5, 9)]
    assert summarize(water).unmet_ml == 8


def test_fractional_remainder_survives_intervals_and_supply_move() -> None:
    water = WaterLedger([WaterStore("pickup", 1), WaterStore("shelter", 0)], [
        WaterCohort("arrived", 1, 1, "pickup"),
    ])
    water.advance(43_200)
    assert water.cohort("arrived").remainder_numerator == 43_200
    assert water.store("pickup").remaining_ml == 1
    water.rebind("arrived", "shelter")
    water.advance(86_400)
    assert water.cohort("arrived").demand_ml == 1
    assert water.cohort("arrived").unmet_ml == 1
    assert water.cohort("arrived").remainder_numerator == 0
    assert water.store("pickup").remaining_ml == 1
    assert water.store("shelter").exhaustion_time_seconds == 43_200


def test_safe_arrival_does_not_imply_water_sufficiency() -> None:
    water = WaterLedger([WaterStore("pickup", 2), WaterStore("shelter", 0)], [
        WaterCohort("safe_arrival", 1, 86_400, "pickup"),
    ])
    queue = EventQueue(3)
    queue.schedule(2, Phase.COMPLETION, "shelter_arrival")
    arrived = False

    def on_event(event, _: EventQueue) -> None:
        nonlocal arrived
        if event.kind == "shelter_arrival":
            arrived = True
            water.rebind("safe_arrival", "shelter")

    run_with_water(queue, water, on_event)
    assert arrived
    assert summarize(water).consumed_ml == 2
    assert summarize(water).unmet_ml == 1
    assert not summarize(water).sufficient_for("safe_arrival")


def test_exhaustion_crossing_is_first_integer_second_for_irregular_rate() -> None:
    water = WaterLedger([WaterStore("s", 3)], [WaterCohort("c", 1, 43_200, "s")])
    water.advance(10)
    assert water.store("s").exhaustion_time_seconds == 6
    assert water.store("s").remaining_ml == 0
    assert water.store("s").unmet_ml == 2


def test_shared_store_shortage_uses_stable_cohort_order() -> None:
    water = WaterLedger([WaterStore("s", 1)], [
        WaterCohort("z", 1, 86_400, "s"), WaterCohort("a", 1, 86_400, "s"),
    ])
    water.advance(1)
    assert water.cohort("a").consumed_ml == 1
    assert water.cohort("z").unmet_ml == 1
    assert water.store("s").exhaustion_time_seconds == 1


def test_empty_supply_is_exhausted_before_fractional_demand_rounds_up() -> None:
    water = WaterLedger([WaterStore("s", 0)], [WaterCohort("c", 1, 1, "s")])
    water.advance(1)
    assert water.store("s").exhaustion_time_seconds == 0
    assert water.cohort("c").remainder_numerator == 1
    assert water.store("s").remaining_ml == 0


def test_reject_unknown_or_invalid_water_inputs() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        WaterStore("s", -1)
    with pytest.raises(ValueError, match="positive"):
        WaterCohort("c", 0, 1, "s")
    with pytest.raises(ValueError, match="unknown water supply"):
        WaterLedger([WaterStore("s", 1)], [WaterCohort("c", 1, 1, "unknown")])
    with pytest.raises(ValueError, match="duplicate"):
        WaterLedger([WaterStore("s", 1), WaterStore("s", 2)], [])


def test_provisional_operational_inputs_bind_every_cohort_to_a_real_store() -> None:
    inputs = OperationalInputs.model_validate_json(OPERATIONAL.read_text(encoding="utf-8"))
    water = WaterLedger.from_operational_inputs(inputs)
    assert len(water.cohorts) == len(inputs.cohorts)
    assert sum(item.people for item in water.cohorts) == sum(item.people for item in inputs.cohorts)
    water.assert_balanced()
