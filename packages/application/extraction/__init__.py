"""Bounded candidate validation and deterministic cross-page consolidation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from typing import Literal, Protocol, cast

from pydantic import ValidationError

from packages.contracts.evidence import (
    CandidateEvidence,
    ExtractionBatch,
    ExtractionIssue,
    ExtractionResponse,
    PageGroup,
    RegionCoverage,
    SourceCitation,
)

KNOWN_UNITS = frozenset({"PERSON", "FAMILY", "LITER", "LITER_PER_DAY", "LITER_PER_PERSON_PER_DAY",
                         "COUNT", "HECTARE", "SQUARE_KILOMETER", "PERCENT", "PESO"})


class ExtractionPort(Protocol):
    def extract(self, group: PageGroup) -> bytes: ...


def _coverage(group: PageGroup, response: ExtractionResponse | None) -> tuple[RegionCoverage, ...]:
    inspected = set(response.inspected_regions) if response else set()
    visual = set(response.visually_inspected_regions) if response else set()
    unresolved = set(response.unresolved_regions) if response else set()
    items: list[RegionCoverage] = []
    for region in group.regions:
        status: Literal["processed", "unresolved", "failed"]
        method: Literal["text", "visual", "manual", "none"]
        if region.region_id in inspected and region.kind == "text":
            status, method, reason = "processed", "text", None
        elif region.region_id in inspected and region.region_id in visual and region.kind != "text":
            status, method, reason = "processed", "visual", None
        elif region.region_id in inspected and region.kind != "text":
            status, method, reason = "unresolved", "none", "Visual or manual review required"
        elif region.region_id in unresolved:
            status, method, reason = "unresolved", "none", "Provider reported unresolved region"
        else:
            status, method, reason = "unresolved", "none", "Region was not inspected"
        items.append(RegionCoverage(physical_page=region.physical_page, region_id=region.region_id,
                                    status=status, method=method, recovery_reason=reason))
    return tuple(items)


def validate_response(group: PageGroup, raw: bytes, *, extractor_version: str) -> ExtractionBatch:
    """Treat provider text as inert data and preserve its exact response digest."""
    digest = hashlib.sha256(raw).hexdigest()
    issues: list[ExtractionIssue] = []
    try:
        if len(raw) > 1_000_000:
            raise ValueError("response byte limit")
        response = ExtractionResponse.model_validate_json(raw)
    except (ValidationError, ValueError):
        response = None
        issues.append(ExtractionIssue(code="invalid_response", physical_page=None, region_id=None,
                                      detail="The extractor returned an invalid response"))
    region_keys = {(region.physical_page, region.region_id) for region in group.regions}
    candidates: list[CandidateEvidence] = []
    normalized_regions: set[tuple[int, str]] = set()
    if response is not None:
        known_region_ids = {region.region_id for region in group.regions}
        for unknown in sorted((set(response.inspected_regions) | set(response.visually_inspected_regions)
                               | set(response.unresolved_regions)) - known_region_ids):
            issues.append(ExtractionIssue(code="invalid_coverage", physical_page=None,
                                          region_id=unknown, detail="Coverage names an unknown region"))
        for uninspected in sorted(set(response.visually_inspected_regions) - set(response.inspected_regions)):
            issues.append(ExtractionIssue(code="invalid_coverage", physical_page=None,
                                          region_id=uninspected, detail="Visual coverage was not inspected"))
        for candidate in response.candidates:
            citation = candidate.citation
            if citation.physical_page not in group.pages and 1 <= citation.physical_page <= len(group.pages):
                mapped_page = group.pages[citation.physical_page - 1]
                if (mapped_page, citation.region_id) in region_keys:
                    if (mapped_page, citation.region_id) not in normalized_regions:
                        issues.append(ExtractionIssue(code="relative_page_normalized",
                                                      physical_page=mapped_page,
                                                      region_id=citation.region_id,
                                                      detail="Provider cited the slice page; mapped to original physical page"))
                        normalized_regions.add((mapped_page, citation.region_id))
                    citation = citation.model_copy(update={"physical_page": mapped_page})
            if citation.physical_page not in group.pages or (
                citation.physical_page, citation.region_id
            ) not in region_keys or citation.region_id not in response.inspected_regions:
                issues.append(ExtractionIssue(code="invalid_citation", physical_page=citation.physical_page,
                                              region_id=citation.region_id, detail="Citation is outside the inspected region"))
                continue
            if (candidate.unit not in KNOWN_UNITS
                    or ("%" in candidate.source_value and candidate.unit != "PERCENT")
                    or ("cost" in candidate.field_key and candidate.unit != "PESO")):
                issues.append(ExtractionIssue(code="invalid_unit", physical_page=citation.physical_page,
                                              region_id=citation.region_id, detail="Source unit needs manual review"))
                continue
            candidates.append(CandidateEvidence(
                document_sha256=group.document_sha256, field_key=candidate.field_key,
                entity_key=candidate.entity_key, source_value=candidate.source_value,
                unit=candidate.unit, statement_type=candidate.statement_type,
                applicable_date=candidate.applicable_date,
                applicable_period=candidate.applicable_period, citations=(citation,),
            ))
    return ExtractionBatch(document_sha256=group.document_sha256, raw_sha256=digest,
                           extractor_version=extractor_version, group_pages=group.pages,
                           candidates=tuple(candidates), coverage=_coverage(group, response),
                           issues=tuple(issues))


def extract_group(group: PageGroup, provider: ExtractionPort, *, extractor_version: str) -> ExtractionBatch:
    try:
        raw = provider.extract(group)
    except (TimeoutError, ConnectionError) as exc:
        return ExtractionBatch(
            document_sha256=group.document_sha256,
            raw_sha256=None, extractor_version=extractor_version,
            group_pages=group.pages, candidates=(),
            coverage=tuple(RegionCoverage(physical_page=region.physical_page, region_id=region.region_id,
                                          status="failed", method="none", recovery_reason="Provider unavailable")
                           for region in group.regions),
            issues=(ExtractionIssue(code="provider_retryable", physical_page=None, region_id=None,
                                    detail=type(exc).__name__),),
        )
    return validate_response(group, raw, extractor_version=extractor_version)


def merge_candidates(batches: tuple[ExtractionBatch, ...]) -> tuple[CandidateEvidence, ...]:
    """Merge identical source claims only; different values remain competing candidates."""
    collected: dict[tuple[str, ...], list[SourceCitation]] = defaultdict(list)
    for batch in batches:
        for candidate in batch.candidates:
            key: tuple[str, ...] = (candidate.document_sha256, candidate.field_key, candidate.entity_key,
                                    candidate.source_value, candidate.unit, candidate.statement_type,
                                    candidate.applicable_date.isoformat() if candidate.applicable_date else "",
                                    candidate.applicable_period or "")
            collected[key].extend(candidate.citations)
    merged: list[CandidateEvidence] = []
    for key in sorted(collected):
        citations = tuple(sorted(set(collected[key]), key=lambda citation: (
            citation.physical_page, citation.region_id, citation.excerpt
        )))
        merged.append(CandidateEvidence(document_sha256=key[0], field_key=key[1], entity_key=key[2],
                                        source_value=key[3], unit=key[4],
                                        statement_type=cast(Literal["reported_existing", "proposed_target", "historical"], key[5]),
                                        applicable_date=date.fromisoformat(key[6]) if key[6] else None,
                                        applicable_period=key[7] or None,
                                        citations=citations))
    return tuple(merged)


def canonical_response_bytes(response: ExtractionResponse) -> bytes:
    return json.dumps(response.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = ["ExtractionPort", "canonical_response_bytes", "extract_group", "merge_candidates", "validate_response"]
