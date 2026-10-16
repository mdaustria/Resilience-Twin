"""Source-only gap review and assumption-aware run readiness."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from packages.domain.evidence import RequiredField, ReviewClaim, ReviewDraft


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    engine_reason: str
    reason: str
    remedy: str
    dependent_conclusions: tuple[str, ...]


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_review_available: bool
    computable: bool
    ready_to_run: bool
    gaps: tuple[Gap, ...]
    source_only_gaps: tuple[Gap, ...]
    documentation_gaps: tuple[str, ...]
    material_hash: str


def _applicable(claim: ReviewClaim, draft: ReviewDraft, requirement: RequiredField) -> bool:
    return (
        claim.field == requirement.field
        and claim.unit == requirement.unit
        and claim.scope_id == draft.scope_id
        and (claim.applicable_from is None or claim.applicable_from <= draft.scenario_date)
        and (claim.applicable_through is None or claim.applicable_through >= draft.scenario_date)
    )


def _gap_for(requirement: RequiredField, draft: ReviewDraft, *, source_only: bool) -> Gap | None:
    sources = {source.source_id: source for source in draft.sources}
    relevant = [claim for claim in draft.claims if claim.field == requirement.field]
    accepted = [claim for claim in relevant if claim.status == "accepted"
                and (claim.statement_type == "reported_existing" or
                     (claim.statement_type == "historical" and claim.applicable_from is not None
                      and claim.applicable_through is not None))
                and claim.value.isascii() and claim.value.isdigit()
                and _applicable(claim, draft, requirement)
                and (not source_only or (claim.source_id is not None
                                         and sources[claim.source_id].role == "primary"))]
    comparable = [claim for claim in relevant if claim.unit == requirement.unit
                  and claim.statement_type == "reported_existing" and _applicable(claim, draft, requirement)
                  and (not source_only or (claim.source_id is not None
                                           and sources[claim.source_id].role == "primary"))]
    competing = len({claim.value for claim in comparable}) > 1
    resolved = any(claim.status == "accepted" and (claim.resolution_note or claim.kind == "correction")
                   for claim in accepted)
    if len({claim.value for claim in accepted}) == 1 and accepted and (not competing or resolved):
        return None
    if not source_only and any(
        assumption.field == requirement.field and assumption.unit == requirement.unit
        and assumption.scope_id == draft.scope_id and assumption.usable
        and assumption.applicable_from <= draft.scenario_date <= assumption.applicable_through
        for assumption in draft.assumptions
    ):
        return None
    if competing or len({claim.value for claim in accepted}) > 1 or any(
        claim.status == "contested" for claim in relevant
    ):
        reason = "Competing source values need a recorded review decision"
    elif any(claim.statement_type == "proposed_target" for claim in relevant):
        reason = "Only proposed or target resources are documented"
    elif any(claim.statement_type == "historical" for claim in relevant):
        reason = "Historical evidence needs scenario-date review"
    elif any(claim.unit != requirement.unit for claim in relevant):
        reason = "Source units need an explicit conversion or allocation"
    elif any("-" in claim.value for claim in relevant):
        reason = "Source range needs an explicit selected value and review"
    elif relevant:
        reason = "The claim is unreviewed, out of scope or outside the scenario date"
    else:
        reason = "The document does not establish this input"
    return Gap(field=requirement.field, engine_reason=requirement.engine_reason, reason=reason,
               remedy=requirement.remedy, dependent_conclusions=requirement.dependent_conclusions)


def evaluate(draft: ReviewDraft) -> Readiness:
    from packages.domain.versions import material_hash

    source_only = tuple(gap for field in draft.required_fields
                        if (gap := _gap_for(field, draft, source_only=True)) is not None)
    gaps = tuple(gap for field in draft.required_fields
                 if (gap := _gap_for(field, draft, source_only=False)) is not None)
    digest = material_hash(draft)
    computable = not gaps
    ready = (computable and draft.scenario_reviewed and draft.sealed_hash == digest
             and draft.acknowledged_hash == digest)
    documentation = tuple(f"Missing annex: {name}" for name in draft.pending_annexes) + tuple(
        f"Procedure not modeled: {name}" for name in draft.unsupported_procedures
    )
    return Readiness(document_review_available=bool(draft.sources), computable=computable,
                     ready_to_run=ready, gaps=gaps, source_only_gaps=source_only,
                     documentation_gaps=documentation, material_hash=digest)


__all__ = ["Gap", "Readiness", "evaluate"]
