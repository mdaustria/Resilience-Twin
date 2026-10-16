"""Build an independent export from owner-scoped, immutable inputs."""

from __future__ import annotations

from typing import Any, Literal, cast

from packages.domain.evidence import ReviewDraft
from packages.domain.readiness import Readiness
from packages.reports import ReportEvidence, ReportMetric, ReportSpec


def build_report_spec(review: dict[str, Any], *, kind: str,
                      proposal: dict[str, Any] | None = None,
                      comparison: dict[str, Any] | None = None) -> ReportSpec:
    if kind not in {"gap_only", "findings", "revision"}:
        raise ValueError("Unsupported independent report kind")
    draft = ReviewDraft.model_validate(review["content"]["draft"])
    readiness = Readiness.model_validate(review["content"]["readiness"])
    if not draft.sources:
        raise ValueError("Report needs an immutable primary source")
    source = next((item for item in draft.sources if item.role == "primary"), None)
    if source is None:
        raise ValueError("Report needs an immutable primary source")
    if kind == "revision" and (proposal is None or not proposal.get("sealed")):
        raise ValueError("Revision report needs a sealed hypothetical proposal")
    if kind == "findings" and comparison is None:
        raise ValueError("Findings report needs an evaluated comparison")

    evidence = tuple(ReportEvidence(
        field=item.field, source_value=item.value, unit=item.unit,
        citation=(f"{item.source_id} page {item.physical_page}"
                  if item.source_id else "User interpretation; no source page"),
        applicability=f"{item.statement_type}; scope {item.scope_id}",
        review_note=item.resolution_note or item.status,
    ) for item in draft.claims if item.status == "accepted")
    gaps = tuple(f"{item.field}: {item.reason}. Remedy: {item.remedy}"
                 for item in readiness.source_only_gaps)
    assumptions = tuple(f"{item.field}: {item.value} {item.unit}; {item.rationale}; "
                        f"limitation: {item.limitations}" for item in draft.assumptions)
    status = "source_only" if kind == "gap_only" else (
        comparison.get("status", "untested") if comparison else "untested")
    if status not in {"source_only", "untested", "partial", "complete"}:
        raise ValueError("Unsupported comparison status")
    metrics: tuple[ReportMetric, ...] = ()
    regressions: tuple[str, ...] = ()
    modeled_findings: tuple[str, ...] = ()
    revision_changes: tuple[str, ...] = ()
    if proposal is not None:
        before = dict(proposal["content"]["baseline"]["water_stores"])
        after = dict(proposal["content"]["variant"]["water_stores"])
        revision_changes = tuple(
            f"Opening water at {store}: {before.get(store, 0)} to {quantity} mL "
            f"(change {quantity - before.get(store, 0)} mL)"
            for store, quantity in sorted(after.items())) + (
            f"Declared additional water: {proposal['content']['variant']['declared_added_water_ml']} mL",
            f"Operations: {proposal['content']['operations']}",)
    if status == "complete" and comparison is not None:
        metrics = (ReportMetric("Completed baseline members",
                                int(comparison["completed_baseline_members"]), "members"),
                   ReportMetric("Planned suite members", int(comparison["planned_members"]),
                                "members"))
        regressions = tuple(str(key) for delta in comparison.get("deltas", ())
                            for key in delta.get("regression_keys", ()))
        metrics += tuple(ReportMetric(
            f"{delta['member_id']} variant minus baseline water unmet",
            int(delta["water_unmet_ml"]), "mL") for delta in comparison.get("deltas", ()))
    if comparison is not None:
        modeled_findings = tuple(
            f"{item['key']}: {item['distinct_affected_people']} distinct modeled people; "
            f"recurrence {item['recurrence_numerator']}/{item['recurrence_denominator']} "
            f"completed members of {item['planned_members']} planned; "
            f"events {', '.join(item['evidence_event_ids'])}"
            for item in comparison.get("findings", ()))
    attribution = ["Independent exploratory analysis; no official approval or field action.",
                   f"Review hash: {review['content_hash']}",
                   f"Source artifact: {source.source_id}"]
    if proposal is not None:
        attribution.extend(("Hypothetical revision; the source PDF is unchanged.",
                            f"Proposal hash: {proposal['content_hash']}"))
    if comparison is not None:
        attribution.append(f"Paired comparison status: {status}; incomplete pairs do not prove gains.")
    return ReportSpec(kind=cast(Literal["gap_only", "findings", "revision", "evaluated"], kind),
                      source_title=source.title,
                      source_sha256=source.sha256, scope=draft.scope_id,
                      exclusions=tuple(draft.unsupported_procedures) or
                      ("Geographic and operational scope beyond the reviewed study area is excluded.",),
                      evidence=evidence, gaps=gaps, assumptions=assumptions,
                      metrics=metrics, regressions=regressions,
                      attribution=tuple(attribution), findings=modeled_findings,
                      revision_changes=revision_changes,
                      evaluation_status=cast(Literal["source_only", "untested", "partial", "complete"], status))


__all__ = ["build_report_spec"]
