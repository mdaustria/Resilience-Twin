"""Owner-scoped use case for the local synthetic case."""

from typing import Protocol

from packages.contracts.skeleton import SkeletonCase, SkeletonResult
from packages.simulation.skeleton import calculate_skeleton


class CaseRepository(Protocol):
    def get(self, owner_id: str, case_id: str) -> SkeletonCase | None: ...


class CaseNotFound(Exception):
    pass


class FixtureMismatch(Exception):
    pass


def get_case(owner_id: str, case_id: str, repository: CaseRepository) -> SkeletonCase:
    case = repository.get(owner_id, case_id)
    if case is None:
        raise CaseNotFound(case_id)
    return case


def run_case(
    owner_id: str, case_id: str, submitted: SkeletonCase, repository: CaseRepository
) -> SkeletonResult:
    expected = get_case(owner_id, case_id, repository)
    if submitted != expected:
        raise FixtureMismatch("Only the exact reviewed synthetic fixture may run")
    return calculate_skeleton(expected)
