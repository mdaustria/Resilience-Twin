"""Evidence-backed findings with distinct cohorts and evaluable recurrence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Occurrence:
    member_id: str
    weakness: str
    asset_id: str
    cohort_id: str
    affected_people: int
    event_id: str

    def __post_init__(self) -> None:
        if not all((self.member_id, self.weakness, self.asset_id,
                    self.cohort_id, self.event_id)):
            raise ValueError("finding occurrence needs stable evidence IDs")
        if type(self.affected_people) is not int or self.affected_people <= 0:
            raise ValueError("affected population must be positive integer people")


@dataclass(frozen=True)
class Finding:
    key: str
    priority_label: str
    affected_cohort_ids: tuple[str, ...]
    distinct_affected_people: int
    maximum_single_event_people: int
    affected_member_ids: tuple[str, ...]
    recurrence_numerator: int
    recurrence_denominator: int
    planned_members: int
    incomplete_member_ids: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    causal_label: str


def derive_findings(
    occurrences: tuple[Occurrence, ...], completed_member_ids: tuple[str, ...],
    planned_member_ids: tuple[str, ...], cohort_people: dict[str, int],
) -> tuple[Finding, ...]:
    planned, completed = set(planned_member_ids), set(completed_member_ids)
    if len(planned) != len(planned_member_ids) or not completed <= planned:
        raise ValueError("invalid planned/completed suite members")
    if any(item.member_id not in completed for item in occurrences):
        raise ValueError("finding cannot use failed or unevaluable member evidence")
    grouped: dict[tuple[str, str], list[Occurrence]] = {}
    for item in occurrences:
        if item.cohort_id not in cohort_people or cohort_people[item.cohort_id] <= 0:
            raise ValueError("finding cohort has no known positive population")
        if item.affected_people > cohort_people[item.cohort_id]:
            raise ValueError("occurrence exceeds cohort population")
        grouped.setdefault((item.weakness, item.asset_id), []).append(item)
    findings = []
    for (weakness, asset_id), items in sorted(grouped.items()):
        cohort_ids = tuple(sorted({item.cohort_id for item in items}))
        member_ids = tuple(sorted({item.member_id for item in items}))
        findings.append(Finding(
            f"{weakness}:{asset_id}", "provisional", cohort_ids,
            sum(cohort_people[item] for item in cohort_ids),
            max(item.affected_people for item in items), member_ids,
            len(member_ids), len(completed), len(planned),
            tuple(sorted(planned - completed)),
            tuple(sorted({item.event_id for item in items})),
            "observed_simulation_association",
        ))
    return tuple(findings)


__all__ = ("Finding", "Occurrence", "derive_findings")
