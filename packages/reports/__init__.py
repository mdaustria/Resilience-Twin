"""Escaped offline proof-report HTML; operational values are explicit inputs."""

from dataclasses import dataclass
from html import escape
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ReportEvidence:
    field: str
    source_value: str
    unit: str
    citation: str
    applicability: str
    review_note: str


@dataclass(frozen=True, slots=True)
class ReportMetric:
    label: str
    value: int
    unit: str


@dataclass(frozen=True, slots=True)
class ReportSpec:
    kind: Literal["gap_only", "findings", "revision", "evaluated"]
    source_title: str
    source_sha256: str
    scope: str
    exclusions: tuple[str, ...]
    evidence: tuple[ReportEvidence, ...]
    gaps: tuple[str, ...]
    assumptions: tuple[str, ...]
    metrics: tuple[ReportMetric, ...] = ()
    regressions: tuple[str, ...] = ()
    attribution: tuple[str, ...] = ()
    evaluation_status: Literal["source_only", "untested", "partial", "complete"] | None = None
    findings: tuple[str, ...] = ()
    revision_changes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.evaluation_status is None:
            object.__setattr__(self, "evaluation_status",
                               "complete" if self.kind == "evaluated" else "source_only")
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.source_sha256):
            raise ValueError("valid source SHA-256 required")
        if self.kind == "gap_only" and (self.metrics or self.regressions):
            raise ValueError("gap-only report cannot contain run outcomes")
        if self.kind == "evaluated" and not self.metrics:
            raise ValueError("evaluated report requires measured metrics")
        if self.evaluation_status != "complete" and (self.metrics or self.regressions):
            raise ValueError("incomplete report cannot contain measured outcomes")


def render_html(spec: ReportSpec) -> str:
    def e(value: str) -> str:
        return escape(value, quote=True)

    def items(values: tuple[str, ...]) -> str:
        return "<ul>" + "".join(f"<li>{e(value)}</li>" for value in values) + "</ul>"

    evidence = "".join(
        "<tr>" + "".join(f"<td>{e(value)}</td>" for value in (
            item.field, item.source_value, item.unit, item.citation,
            item.applicability, item.review_note)) + "</tr>"
        for item in spec.evidence)
    metrics = "" if not spec.metrics else (
        "<h2>Measured outcomes</h2><table><thead><tr><th>Metric</th><th>Value</th><th>Unit</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{e(m.label)}</td><td>{m.value}</td><td>{e(m.unit)}</td></tr>"
                  for m in spec.metrics) + "</tbody></table><h2>Regressions</h2>"
        + items(spec.regressions or ("None in supplied comparison",)))
    findings = "" if not spec.findings else "<h2>Modeled findings</h2>" + items(spec.findings)
    revision = "" if not spec.revision_changes else (
        "<h2>Hypothetical revision changes</h2>" + items(spec.revision_changes))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"referrer\" content=\"no-referrer\"><title>Independent analysis</title>"
            "<style>@page{size:A4;margin:12mm}"
            "body{font:11.5px Arial,sans-serif;max-width:760px;margin:0 auto;color:#182d2b}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #9ba9a6;padding:5px;"
            "vertical-align:top}tr,li{break-inside:avoid}h1,h2{color:#164c43;break-after:avoid}"
            "small{color:#4b5b58}</style></head><body>"
            "<h1>Independent disaster-plan analysis</h1><p>This is an independent analysis, "
            "not government approval or an operational order.</p>"
            f"<p><strong>Report:</strong> {e(spec.kind.replace('_', ' '))}</p>"
            f"<p><strong>Evaluation status:</strong> {e(spec.evaluation_status or 'source_only')}. "
            "Untested or partial changes carry no measured improvement claim.</p>"
            f"<p><strong>Source:</strong> {e(spec.source_title)}<br><small>SHA-256: {spec.source_sha256}</small></p>"
            f"<p><strong>Modeled scope:</strong> {e(spec.scope)}</p>"
            f"<h2>Exclusions</h2>{items(spec.exclusions)}"
            "<h2>Source and supplemental evidence</h2><table><thead><tr><th>Field</th><th>Source value</th>"
            "<th>Unit</th><th>Citation</th><th>Applicability</th><th>Review</th></tr></thead><tbody>"
            f"{evidence}</tbody></table><h2>Readiness gaps</h2>{items(spec.gaps)}"
            f"<h2>Explicit assumptions</h2>{items(spec.assumptions)}{revision}{metrics}{findings}"
            f"<h2>Attribution</h2>{items(spec.attribution)}</body></html>")


def spec_from_record(record: dict[str, Any]) -> ReportSpec:
    return ReportSpec(kind=record["kind"], source_title=record["source_title"],
                      source_sha256=record["source_sha256"], scope=record["scope"],
                      exclusions=tuple(record["exclusions"]),
                      evidence=tuple(ReportEvidence(**item) for item in record["evidence"]),
                      gaps=tuple(record["gaps"]), assumptions=tuple(record["assumptions"]),
                      metrics=tuple(ReportMetric(**item) for item in record["metrics"]),
                      regressions=tuple(record["regressions"]),
                      attribution=tuple(record["attribution"]),
                      evaluation_status=record["evaluation_status"],
                      findings=tuple(record.get("findings", ())),
                      revision_changes=tuple(record.get("revision_changes", ())))


__all__ = ("ReportEvidence", "ReportMetric", "ReportSpec", "render_html", "spec_from_record")
