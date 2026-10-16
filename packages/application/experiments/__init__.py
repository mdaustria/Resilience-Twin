"""Pinned bounded sensitivity sweeps and tiny exhaustive policy references."""

import hashlib
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from typing import Literal

from packages.contracts.checkpoints import canonical_json
from packages.contracts.outcomes import Outcome
from packages.simulation.kernel.population import PopulationLedger
from packages.simulation.kernel.resources import ResourceLedger
from packages.simulation.policies.deadline_greedy import Candidate
from packages.simulation.policies.feasibility import check_trip, dispatch

FactorName = Literal["travel_seconds", "loading_seconds", "demand_time_seconds",
                     "water_ml_per_person_day"]
FACTORS: tuple[FactorName, ...] = (
    "travel_seconds", "loading_seconds", "demand_time_seconds",
    "water_ml_per_person_day",
)


@dataclass(frozen=True)
class FactorRange:
    name: FactorName
    low: int
    nominal: int
    high: int
    provenance: str

    def __post_init__(self) -> None:
        if (self.name not in FACTORS or not self.provenance
                or any(type(value) is not int or value < 0 for value in (
                    self.low, self.nominal, self.high,
                )) or not self.low <= self.nominal <= self.high):
            raise ValueError("factor range needs reviewed ordered integer values and provenance")
        if self.name == "water_ml_per_person_day" and self.low == 0:
            raise ValueError("water use must remain positive")


@dataclass(frozen=True)
class Configuration:
    id: str
    values: tuple[tuple[FactorName, int], ...]
    exogenous_hash: str
    range_provenance: tuple[tuple[FactorName, str], ...]

    def value(self, name: FactorName) -> int:
        return dict(self.values)[name]


def expand_configurations(
    ranges: tuple[FactorRange, ...], *, exogenous_hash: str,
) -> tuple[Configuration, ...]:
    if len(exogenous_hash) != 64 or len(ranges) != len(FACTORS) or (
        {item.name for item in ranges} != set(FACTORS)
    ):
        raise ValueError("all four factors and one pinned exogenous hash are required")
    by_name = {item.name: item for item in ranges}
    provenance = tuple((name, by_name[name].provenance) for name in FACTORS)
    nominal = {name: by_name[name].nominal for name in FACTORS}

    def make(case_id: str, values: dict[FactorName, int]) -> Configuration:
        return Configuration(case_id, tuple((name, values[name]) for name in FACTORS),
                             exogenous_hash, provenance)

    configurations = [make("nominal", nominal)]
    for name in FACTORS:
        for level in ("low", "high"):
            values = nominal.copy()
            values[name] = getattr(by_name[name], level)
            configurations.append(make(f"{name}:{level}", values))
    adverse = nominal.copy()
    adverse["travel_seconds"] = by_name["travel_seconds"].high
    adverse["loading_seconds"] = by_name["loading_seconds"].high
    adverse["demand_time_seconds"] = by_name["demand_time_seconds"].low
    adverse["water_ml_per_person_day"] = by_name["water_ml_per_person_day"].high
    configurations.append(make("adverse_declared", adverse))
    return tuple(configurations)


@dataclass(frozen=True)
class PairEvaluation:
    configuration: Configuration
    policy_version: str
    baseline: Outcome
    variant: Outcome

    @property
    def on_time_delta(self) -> int:
        return self.variant.on_time_people - self.baseline.on_time_people


@dataclass(frozen=True)
class SensitivityResult:
    pairs: tuple[PairEvaluation, ...]
    on_time_range: tuple[int, int]
    water_unmet_range_ml: tuple[int, int]
    rank_reversal_case_ids: tuple[str, ...]
    policy_dependent_case_ids: tuple[str, ...]
    label: str = "bounded_sensitivity_not_probability"


Evaluator = Callable[[Configuration, str, bool], Outcome]


def evaluate_sensitivity(
    configurations: tuple[Configuration, ...], policies: tuple[str, str],
    expected_people: int, evaluator: Evaluator,
) -> SensitivityResult:
    if (not configurations or len({item.id for item in configurations}) != len(configurations)
            or not policies[0] or not policies[1] or policies[0] == policies[1]
            or type(expected_people) is not int or expected_people <= 0):
        raise ValueError("sensitivity needs distinct policies, cases and expected people")
    if len({item.exogenous_hash for item in configurations}) != 1:
        raise ValueError("sensitivity cases must pin one exogenous event stream")
    pairs = tuple(PairEvaluation(configuration, policy,
                                 evaluator(configuration, policy, False),
                                 evaluator(configuration, policy, True))
                  for configuration in configurations for policy in policies)
    if any(type(value) is not int or value < 0 for pair in pairs for result in (
        pair.baseline, pair.variant,
    ) for value in (result.on_time_people, result.vulnerable_on_time_people,
                    result.water_unmet_ml, result.stranded_people)):
        raise ValueError("outcomes must contain nonnegative integer quantities")
    all_outcomes = tuple(result for pair in pairs for result in (pair.baseline, pair.variant))
    by_policy = [pair for pair in pairs if pair.policy_version == policies[0]]
    positive = any(pair.on_time_delta > 0 for pair in by_policy)
    negative = any(pair.on_time_delta < 0 for pair in by_policy)
    reversal = tuple(pair.configuration.id for pair in by_policy
                     if pair.on_time_delta != 0) if positive and negative else ()
    by_case = {(pair.configuration.id, pair.policy_version): pair for pair in pairs}
    policy_dependent = tuple(configuration.id for configuration in configurations
                             if by_case[(configuration.id, policies[0])].baseline.on_time_people
                             < expected_people
                             and by_case[(configuration.id, policies[1])].baseline.on_time_people
                             >= expected_people)
    return SensitivityResult(
        pairs,
        (min(item.on_time_people for item in all_outcomes),
         max(item.on_time_people for item in all_outcomes)),
        (min(item.water_unmet_ml for item in all_outcomes),
         max(item.water_unmet_ml for item in all_outcomes)),
        reversal, policy_dependent,
    )


@dataclass(frozen=True)
class ExhaustiveReference:
    candidate_set_hash: str
    combinations_evaluated: int
    maximum_on_time_people: int
    best_trip_ids: tuple[str, ...]
    scope_label: str = "tiny_static_candidate_set_not_global_optimum"


def enumerate_tiny_reference(
    candidates: tuple[Candidate, ...], population: PopulationLedger,
    resources: ResourceLedger, *, max_combinations: int = 10_000,
) -> ExhaustiveReference:
    if type(max_combinations) is not int or max_combinations <= 0:
        raise ValueError("exhaustive bound must be a positive integer")
    options: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        options.setdefault(candidate.plan.cohort_id, []).append(candidate)
    groups = tuple(sorted(options))
    ordered = tuple((None, *sorted(options[group], key=lambda item: item.plan.id))
                    for group in groups)
    count = 1
    for group_options in ordered:
        count *= len(group_options)
    if count > max_combinations:
        raise ValueError("candidate enumeration exceeds the declared tiny bound")
    best_people = -1
    best_ids: tuple[str, ...] = ()
    for selection in product(*ordered):
        trial = deepcopy(resources)
        ids: list[str] = []
        on_time = 0
        for selected_candidate in selection:
            if selected_candidate is None:
                continue
            result = check_trip(selected_candidate.plan, trial, population)
            if not result.feasible or result.timing is None:
                break
            dispatch(selected_candidate.plan, trial, population)
            ids.append(selected_candidate.plan.id)
            deadline = population.get(selected_candidate.plan.cohort_id).deadline_seconds
            if deadline is None or result.timing.unloaded_seconds <= deadline:
                on_time += selected_candidate.plan.people
        else:
            key = tuple(sorted(ids))
            if on_time > best_people or (on_time == best_people and key < best_ids):
                best_people, best_ids = on_time, key
    digest = hashlib.sha256(canonical_json(tuple(sorted(
        (item.plan.id, item.plan.cohort_id, item.plan.people) for item in candidates
    )))).hexdigest()
    return ExhaustiveReference(digest, count, best_people, best_ids)


__all__ = (
    "Configuration", "ExhaustiveReference", "FactorRange", "PairEvaluation",
    "SensitivityResult", "enumerate_tiny_reference", "evaluate_sensitivity",
    "expand_configurations",
)
