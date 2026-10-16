"""Offline report proof with intentionally fictional source data."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Literal

import pytest
from pypdf import PdfReader

from packages.adapters.geo.compiler import CompilePolicy, compile_small_import
from packages.application.reports import render_verified_html
from packages.application.reports.pilot import run_pilot_proof
from packages.reports import ReportEvidence, ReportMetric, ReportSpec
from services.api.geography import pilot_geography

ROOT = Path(__file__).resolve().parents[2]


def _spec(source: Path, kind: Literal["gap_only", "evaluated"]) -> ReportSpec:
    return ReportSpec(
        kind=kind, source_title="Fictional <training> source",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        scope="Synthetic two-block study area; excludes all other areas",
        exclusions=("Neighboring facility access and permission unknown",),
        evidence=(ReportEvidence("water", "2–3", "L/day", "physical page 2, table <A>",
                                 "historical", "range unresolved; do not infer inventory"),),
        gaps=("Opening water inventory unknown",),
        assumptions=("No operational assumption accepted",),
        metrics=(ReportMetric("On-time arrivals", 4, "people"),) if kind == "evaluated" else (),
        regressions=("Water shortfall increased",) if kind == "evaluated" else (),
        attribution=("Fictional training fixture",),
    )


def test_gap_only_html_has_no_invented_metrics_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fictional immutable source bytes")
    before = source.read_bytes()
    html = render_verified_html(_spec(source, "gap_only"), source).decode()
    assert "&lt;training&gt;" in html and "table &lt;A&gt;" in html
    assert "Opening water inventory unknown" in html
    assert "Measured outcomes" not in html and "On-time arrivals" not in html
    assert source.read_bytes() == before
    (tmp_path / "different.pdf").write_bytes(b"different")
    with pytest.raises(ValueError, match="hash differs"):
        render_verified_html(_spec(source, "gap_only"), tmp_path / "different.pdf")


@pytest.mark.parametrize("kind", ["gap_only", "evaluated"])
def test_offline_pdf_is_readable_and_labeled(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fictional immutable source bytes")
    html = tmp_path / "report.html"
    pdf = tmp_path / "report.pdf"
    html.write_bytes(render_verified_html(_spec(source, kind), source))
    subprocess.run(["node", str(ROOT / "packages/reports/render_pdf.mjs"), str(html), str(pdf)],
                   cwd=ROOT, env=os.environ.copy(), check=True, timeout=30)
    pages = PdfReader(pdf).pages
    text = "\n".join(page.extract_text() for page in pages)
    assert "Independent disaster-plan analysis" in text
    assert "Opening water inventory unknown" in text
    assert ("Measured outcomes" in text) == (kind == "evaluated")
    assert source.read_bytes() == b"fictional immutable source bytes"


def test_gap_only_rejects_metric_payload(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fictional immutable source bytes")
    spec = _spec(source, "evaluated")
    with pytest.raises(ValueError, match="cannot contain run outcomes"):
        ReportSpec("gap_only", spec.source_title, spec.source_sha256, spec.scope,
                   spec.exclusions, spec.evidence, spec.gaps, spec.assumptions, spec.metrics)


@pytest.mark.parametrize("case,name,start,end,closed,deadline", [
    ("qc", "talayan", "13137612581", "39649824", "osm:107948780:13:forward", 216),
    ("guiguinto", "guiguinto", "5733371091", "9357839617",
     "osm:1341516497:0:forward", 70),
])
def test_public_pilot_is_deterministic_and_comparable(
    case: str, name: str, start: str, end: str, closed: str, deadline: int,
) -> None:
    sample = json.loads((ROOT / f"release/validation/geography/{name}-small.json").read_text())
    graph, _ = compile_small_import(sample, CompilePolicy(30))
    geography = pilot_geography(case)  # type: ignore[arg-type]
    args = {"case": case, "start": start, "end": end, "closed_edge": closed,
            "deadline": deadline, "scope_hash": geography.scope_digest,
            "graph_hash": geography.graph_sha256, "source_hash": "a" * 64}
    first = run_pilot_proof(graph, **args)
    second = run_pilot_proof(graph, **args)
    assert first == second
    assert first.comparison_status == "complete"
    assert [member.outcome.on_time_people for member in first.baseline] == [20, 0]
    assert all(member.outcome.water_unmet_ml == 0 for member in first.variant)
    assert first.baseline[1].route_seconds > first.baseline[0].route_seconds
    assert first.baseline[0].result.event_hash != first.baseline[1].result.event_hash
    assert all(not delta["regression_keys"] for delta in first.comparison_deltas)
