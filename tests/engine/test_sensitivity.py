"""Pinned one-factor/adverse pairs with hand-calculated rank reversal."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from packages.application.experiments import (
    Configuration,
    FactorRange,
    evaluate_sensitivity,
    expand_configurations,
)
from packages.contracts.outcomes import Outcome

FIXTURE = json.loads((Path(__file__).parents[1]
                      / "fixtures/validation/sensitivity/tiny-cases.json").read_text(
                          encoding="utf-8",
                      ))
POLICIES = ("deadline_greedy_v1", "earliest_deadline_reference_v1")


def configurations() -> tuple[Configuration, ...]:
    return expand_configurations(tuple(FactorRange(
        name, row["low"], row["nominal"], row["high"], row["provenance"],
    ) for name, row in FIXTURE["factors"].items()), exogenous_hash="e" * 64)


def hand_calculated_pair(
    configuration: Configuration, policy: str, variant: bool,
) -> Outcome:
    travel = configuration.value("travel_seconds")
    loading = configuration.value("loading_seconds")
    demand = configuration.value("demand_time_seconds")
    rate_per_second = configuration.value("water_ml_per_person_day") // 86_400
    if variant:
        first_arrival = second_arrival = 2 * travel + loading + demand
    else:
        first_arrival = travel + loading + 4 + demand
        second_arrival = travel + loading + demand
        if policy == "earliest_deadline_reference_v1":
            first_arrival = min(first_arrival, 2 * travel + loading + demand)
    first_on_time = 4 if first_arrival <= 5 else 0
    second_on_time = 4 if second_arrival <= 8 else 0
    water_demand = sum(4 * rate_per_second * (10 - arrival)
                       for arrival in (first_arrival, second_arrival)
                       if arrival <= 10)
    return Outcome(first_on_time + second_on_time, first_on_time,
                   max(0, water_demand - 20), 0,
                   ("synthetic-fixed-exogenous-event",))


def test_one_factor_and_adverse_expansion_are_pinned_and_reviewable() -> None:
    cases = configurations()
    assert len(cases) == 10
    nominal = cases[0]
    assert nominal.id == "nominal"
    assert all(case.exogenous_hash == nominal.exogenous_hash for case in cases)
    assert all(len(case.range_provenance) == 4 for case in cases)
    for case in cases[1:-1]:
        assert sum(case.value(name) != nominal.value(name)
                   for name, _ in nominal.values) <= 1
    adverse = cases[-1]
    assert adverse.id == "adverse_declared"
    for name, level in FIXTURE["adverse_combination"].items():
        assert adverse.value(name) == FIXTURE["factors"][name][level]


def test_paired_outcomes_show_ranges_reversal_and_policy_dependence() -> None:
    result = evaluate_sensitivity(configurations(), POLICIES, 8, hand_calculated_pair)
    assert len(result.pairs) == 20
    assert result.on_time_range[0] < result.on_time_range[1]
    assert result.water_unmet_range_ml[0] < result.water_unmet_range_ml[1]
    by_case = {(pair.configuration.id, pair.policy_version): pair
               for pair in result.pairs}
    assert by_case[("travel_seconds:low", POLICIES[0])].on_time_delta == 4
    assert by_case[("travel_seconds:high", POLICIES[0])].on_time_delta == -4
    assert "travel_seconds:low" in result.rank_reversal_case_ids
    assert "travel_seconds:high" in result.rank_reversal_case_ids
    assert "travel_seconds:low" in result.policy_dependent_case_ids
    assert result.label == "bounded_sensitivity_not_probability"
    assert all(pair.configuration.exogenous_hash == "e" * 64 for pair in result.pairs)


def test_invalid_ranges_and_unpaired_event_streams_fail() -> None:
    with pytest.raises(ValueError, match="factor range"):
        FactorRange("travel_seconds", 5, 3, 1, "synthetic")
    cases = configurations()
    altered = (cases[0], replace(cases[1], exogenous_hash="f" * 64))
    with pytest.raises(ValueError, match="exogenous"):
        evaluate_sensitivity(altered, POLICIES, 8, hand_calculated_pair)


def test_release_artifact_pins_expanded_pairs_and_fixture() -> None:
    root = Path(__file__).parents[2]
    fixture_path = root / "tests/fixtures/validation/sensitivity/tiny-cases.json"
    artifact = json.loads((root / "release/validation/sensitivity/tiny-expanded.json")
                          .read_text(encoding="utf-8"))
    assert artifact["fixture_sha256"] == hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    assert {item["id"] for item in artifact["configurations"]} == {
        item.id for item in configurations()
    }
    assert len(artifact["pairs"]) == 20
    assert {(item["configuration_id"], item["policy_version"])
            for item in artifact["pairs"]} == {
        (case.id, policy) for case in configurations() for policy in POLICIES
    }
    assert artifact["scope_label"] == "bounded_sensitivity_not_probability"
