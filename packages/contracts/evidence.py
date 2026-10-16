"""Typed documentary extraction artifacts; candidates are not operational facts."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCitation(Contract):
    physical_page: int = Field(strict=True, ge=1)
    region_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)


class RawCandidate(Contract):
    field_key: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    source_value: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    statement_type: Literal["reported_existing", "proposed_target", "historical"]
    applicable_date: date | None = None
    applicable_period: str | None = Field(default=None, max_length=40)
    citation: SourceCitation

    @model_validator(mode="before")
    @classmethod
    def preserve_year_or_plan_period(cls, value: object) -> object:
        if isinstance(value, dict):
            date_text = value.get("applicable_date")
            if isinstance(date_text, str) and re.fullmatch(r"\d{4}[0-9/-]{0,36}", date_text):
                try:
                    date.fromisoformat(date_text)
                except ValueError:
                    return {**value, "applicable_date": None, "applicable_period": date_text}
        return value


class ExtractionResponse(Contract):
    candidates: tuple[RawCandidate, ...] = Field(max_length=200)
    inspected_regions: tuple[str, ...] = Field(max_length=80)
    visually_inspected_regions: tuple[str, ...] = Field(default=(), max_length=80)
    unresolved_regions: tuple[str, ...] = Field(default=(), max_length=80)


class PageRegion(Contract):
    physical_page: int = Field(strict=True, ge=1)
    region_id: str = Field(min_length=1)
    kind: Literal["text", "image_table", "graphic_marks", "split_table"]
    linked_region_id: str | None = None


class PageGroup(Contract):
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    physical_page_count: int = Field(strict=True, gt=0)
    pages: tuple[int, ...] = Field(min_length=1, max_length=8)
    regions: tuple[PageRegion, ...] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def bounded_and_complete(self) -> Self:
        if tuple(sorted(set(self.pages))) != self.pages:
            raise ValueError("group pages must be unique and ordered")
        if self.pages[-1] > self.physical_page_count:
            raise ValueError("group page exceeds document")
        if self.pages[-1] - self.pages[0] + 1 != len(self.pages):
            raise ValueError("group pages must be contiguous")
        if len({region.region_id for region in self.regions}) != len(self.regions):
            raise ValueError("region ids must be unique within a group")
        if any(region.physical_page not in self.pages for region in self.regions):
            raise ValueError("region lies outside group")
        if {region.physical_page for region in self.regions} != set(self.pages):
            raise ValueError("each group page needs a coverage region")
        region_ids = {region.region_id for region in self.regions}
        if any(region.linked_region_id is not None and region.linked_region_id not in region_ids
               for region in self.regions):
            raise ValueError("linked region is missing")
        return self


class RegionCoverage(Contract):
    physical_page: int = Field(strict=True, ge=1)
    region_id: str = Field(min_length=1)
    status: Literal["processed", "unresolved", "failed"]
    method: Literal["text", "visual", "manual", "none"]
    recovery_reason: str | None


class CandidateEvidence(Contract):
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_key: str
    entity_key: str
    source_value: str
    unit: str
    statement_type: Literal["reported_existing", "proposed_target", "historical"]
    applicable_date: date | None
    applicable_period: str | None = None
    citations: tuple[SourceCitation, ...] = Field(min_length=1)
    review_status: Literal["unreviewed"] = "unreviewed"


class ExtractionIssue(Contract):
    code: str
    physical_page: int | None
    region_id: str | None
    detail: str


class ExtractionBatch(Contract):
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_version: str = Field(min_length=1)
    group_pages: tuple[int, ...]
    candidates: tuple[CandidateEvidence, ...]
    coverage: tuple[RegionCoverage, ...]
    issues: tuple[ExtractionIssue, ...]


__all__ = [
    "CandidateEvidence", "ExtractionBatch", "ExtractionIssue", "ExtractionResponse",
    "PageGroup", "PageRegion", "RawCandidate", "RegionCoverage", "SourceCitation",
]
