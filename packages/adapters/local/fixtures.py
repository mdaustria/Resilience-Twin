"""In-memory, synthetic owner-scoped fixture adapter for development only."""

import json
from pathlib import Path

from packages.contracts.skeleton import SkeletonCase

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests/fixtures/skeleton/cases.json"


class FixtureCaseRepository:
    def __init__(self, path: Path = FIXTURE_PATH) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._cases: dict[tuple[str, str], SkeletonCase] = {}
        for item in raw["cases"]:
            owner_id = item["owner_id"]
            case = SkeletonCase.model_validate(item["case"])
            key = (owner_id, case.case_id)
            if key in self._cases:
                raise ValueError(f"Duplicate fixture owner/case key: {key}")
            self._cases[key] = case

    def get(self, owner_id: str, case_id: str) -> SkeletonCase | None:
        return self._cases.get((owner_id, case_id))
