"""Paired, pin-checked hypothetical outcome deltas and regressions."""

from dataclasses import dataclass
from typing import Literal

from packages.contracts.outcomes import Outcome


@dataclass(frozen=True)
class MemberResult:
    member_id: str
    exogenous_hash: str
    status: Literal["completed", "failed", "cancelled"]
    outcome: Outcome | None

    def __post_init__(self) -> None:
        if not self.member_id or len(self.exogenous_hash) != 64:
            raise ValueError("member needs stable ID and exogenous hash")
        if (self.status == "completed") != (self.outcome is not None):
            raise ValueError("only completed members have an outcome")


@dataclass(frozen=True)
class PairedRun:
    input_hash: str
    source_hashes: tuple[str, ...]
    scenario_suite_hash: str
    scope_hash: str
    graph_hash: str
    engine_hash: str
    policy_version: str
    members: tuple[MemberResult, ...]

    def __post_init__(self) -> None:
        if len({item.member_id for item in self.members}) != len(self.members):
            raise ValueError("duplicate suite member result")


@dataclass(frozen=True)
class MemberDelta:
    member_id: str
    on_time_people: int
    vulnerable_on_time_people: int
    water_unmet_ml: int
    stranded_people: int
    regression_keys: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class Comparison:
    status: Literal["complete", "partial", "untested", "non_comparable"]
    paired_member_ids: tuple[str, ...]
    excluded_member_ids: tuple[str, ...]
    deltas: tuple[MemberDelta, ...]
    measured_improvement: bool
    priority_label: str
    reason: str | None


def compare_pairs(
    baseline: PairedRun, variant: PairedRun | None, *,
    variant_baseline_hash: str | None = None,
) -> Comparison:
    if variant is None:
        return Comparison("untested", (), tuple(sorted(item.member_id for item in baseline.members)),
                          (), False, "provisional", "proposal has no measured run")
    pins_match = (
        variant_baseline_hash == baseline.input_hash
        and baseline.source_hashes == variant.source_hashes
        and baseline.scenario_suite_hash == variant.scenario_suite_hash
        and baseline.scope_hash == variant.scope_hash
        and baseline.graph_hash == variant.graph_hash
        and baseline.engine_hash == variant.engine_hash
        and baseline.policy_version == variant.policy_version
    )
    if not pins_match:
        return Comparison("non_comparable", (), (), (), False, "provisional",
                          "lineage, exogenous conditions, scope or model pins differ")
    before = {item.member_id: item for item in baseline.members}
    after = {item.member_id: item for item in variant.members}
    if set(before) != set(after) or any(
        before[key].exogenous_hash != after[key].exogenous_hash for key in before.keys() & after.keys()
    ):
        return Comparison("non_comparable", (), (), (), False, "provisional",
                          "suite members or exogenous event hashes differ")
    deltas = []
    excluded = []
    for member_id in sorted(before):
        first, second = before[member_id], after[member_id]
        if first.outcome is None or second.outcome is None:
            excluded.append(member_id)
            continue
        on_time = second.outcome.on_time_people - first.outcome.on_time_people
        vulnerable = (second.outcome.vulnerable_on_time_people
                      - first.outcome.vulnerable_on_time_people)
        water = second.outcome.water_unmet_ml - first.outcome.water_unmet_ml
        stranded = second.outcome.stranded_people - first.outcome.stranded_people
        regressions = tuple(name for name, bad in (
            ("on_time_people", on_time < 0),
            ("vulnerable_on_time_people", vulnerable < 0),
            ("water_unmet_ml", water > 0),
            ("stranded_people", stranded > 0),
        ) if bad)
        deltas.append(MemberDelta(
            member_id, on_time, vulnerable, water, stranded, regressions,
            tuple(sorted(set(first.outcome.evidence_event_ids)
                         | set(second.outcome.evidence_event_ids))),
        ))
    status: Literal["complete", "partial"] = "partial" if excluded else "complete"
    improved = bool(deltas) and not excluded and all(
        not item.regression_keys for item in deltas
    ) and any(item.on_time_people > 0 or item.vulnerable_on_time_people > 0
              or item.water_unmet_ml < 0 or item.stranded_people < 0 for item in deltas)
    return Comparison(status, tuple(item.member_id for item in deltas), tuple(excluded),
                      tuple(deltas), improved, "provisional",
                      "incomplete paired suite" if excluded else None)


__all__ = ("Comparison", "MemberDelta", "MemberResult", "PairedRun", "compare_pairs")
