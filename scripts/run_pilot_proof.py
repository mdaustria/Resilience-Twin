"""Rebuild both public-source local pilot reports from pinned geography and PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.adapters.geo.compiler import CompilePolicy, compile_small_import
from packages.application.reports import render_verified_html
from packages.application.reports.pilot import PilotProof, run_pilot_proof
from packages.application.review import (
    DEFAULTS_VERSION,
    ReviewService,
    default_assumptions,
    pilot_review,
)
from packages.domain.readiness import evaluate
from packages.reports import ReportEvidence, ReportMetric, ReportSpec
from services.api.geography import pilot_geography

OUTPUT = ROOT / "release/validation/reports"
SETTINGS = {
    "qc": ("talayan", "13137612581", "39649824", "osm:107948780:13:forward", 216,
           "QCDRRMP-2021-2027_Volume-1.pdf"),
    "guiguinto": ("guiguinto", "5733371091", "9357839617",
                  "osm:1341516497:0:forward", 70, "Guiguinto-MDRRM-PLAN-2023-2025.pdf"),
}


PilotCase = Literal["qc", "guiguinto"]


def _spec(case: PilotCase, kind: str, proof: PilotProof | None) -> ReportSpec:
    draft = pilot_review("report-proof", case)  # source claims never inherit assumed run values
    readiness = evaluate(draft)
    geography = pilot_geography(case)
    source = draft.sources[0]
    evidence = tuple(ReportEvidence(
        item.field, item.value, item.unit, f"Original PDF physical page {item.physical_page}",
        item.statement_type + ("; 2023-2025 plan period" if case == "guiguinto" else ""),
        item.status + (f"; unresolved conflict {item.conflict_group}" if item.conflict_group else "")
    ) for item in draft.claims)
    adjudication = json.loads((ROOT / "release/validation/extraction/adjudication.json").read_text())
    evidence += tuple(ReportEvidence(
        item["id"], item["source_fact"],
        "FAMILY" if item["id"] == "guiguinto_shelter_units_range" else "source text",
        "Original PDF physical page " + ", ".join(map(str, item["physical_pages"])),
        "2023-2025 plan period; historical for 2026 scenario" if case == "guiguinto"
        else "2021-2027 plan period",
        item["disposition"] + "; documentary context, not scoped operational inventory",
    ) for item in adjudication["sources"][case]["items"])
    if kind == "evaluated":
        evidence += (ReportEvidence(
            "reviewed road graph", geography.graph_sha256, "SHA-256",
            f"release/validation/geography/{'talayan' if case == 'qc' else 'guiguinto'}-small.json; "
            "https://download.openstreetmap.fr/extracts/asia/philippines/",
            "2026-10-13 OSM snapshot, car route within local model cell",
            "Supplemental road geometry only; connector access and travel conditions assumed",
        ),)
    gaps = tuple(f"{gap.field}: {gap.reason}. {gap.remedy}. Depends: "
                 + ", ".join(gap.dependent_conclusions) for gap in readiness.source_only_gaps)
    gaps += readiness.documentation_gaps
    scope = (f"{geography.area.label}; exact model-cell polygon {geography.area.boundary_lon_lat}; "
             "one hypothetical 100-person cohort; no full jurisdiction estimate")
    exclusions = tuple(member.label + ": " + member.reason for member in geography.area.members
                       if not member.included) + geography.area.cross_boundary_assumptions
    attribution = ("Independent exploratory analysis; hypothetical assumptions are not plan facts",
                   "Road geometry © OpenStreetMap contributors, ODbL 1.0; regional snapshot 2026-10-13",
                   "No field predictive validation or government approval is claimed")
    if kind == "gap_only":
        return ReportSpec("gap_only", source.title, source.sha256, scope, exclusions,
                          evidence, gaps, ("No operational assumptions accepted in this source-only view",),
                          attribution=attribution)
    assert proof is not None
    metrics = tuple(metric for member in proof.baseline + proof.variant for metric in (
        ReportMetric(f"{member.member_id} {'baseline' if member in proof.baseline else 'added-water'} "
                     "on-time arrival", member.outcome.on_time_people, "people"),
        ReportMetric(f"{member.member_id} {'baseline' if member in proof.baseline else 'added-water'} "
                     "unmet water", member.outcome.water_unmet_ml, "mL"),
        ReportMetric(f"{member.member_id} car route travel", member.route_seconds, "seconds"),
    ))
    assumptions = (
        "Personally reviewed local model cell and OSM connectors; physical access and facility operation assumed",
        ("One hypothetical 100-person cohort, 20-seat prepositioned vehicle, one dedicated crew, "
         "150-person shelter with zero initial occupants; 80 people remain at pickup"),
        ("Opening water: pickup 100,000 mL and shelter 400,000 mL; "
         "2,000 mL/person/day over 259,200 seconds. Hypothetical change adds 500,000 mL at pickup"),
        f"Passenger deadline {proof.deadline_seconds} seconds; one second positioning, loading and unloading each",
        f"Road closure at time zero on exact edge {proof.closed_edge_id}; known to policy at time zero",
        ("Car-road routing uses a declared 30 km/h fallback where OSM speed is unknown; "
         "the selected anchors and route do not establish field travel or accessibility"),
        "No FAMILY-to-PERSON conversion; city/municipal historic totals and proposed resources are context only",
        "Variant is hypothetical and untested in the field; no resupply during the three-day horizon",
    )
    regressions = tuple(f"{item['member_id']}: {', '.join(cast(tuple[str, ...], item['regression_keys']))}"
                        for item in proof.comparison_deltas if item["regression_keys"])
    if not regressions:
        regressions = ("No regression under the recorded four-metric paired comparison",)
    return ReportSpec("evaluated", source.title, source.sha256, scope, exclusions, evidence,
                      gaps, assumptions, metrics, regressions, attribution)


def build(case: PilotCase, pdf: Path, *, render_pdf: bool = True) -> dict[str, Any]:
    name, start, end, closed, deadline, _ = SETTINGS[case]
    geography = pilot_geography(case)
    if geography.blockers:
        raise ValueError(f"{case} geography has blockers")
    sample = json.loads((ROOT / f"release/validation/geography/{name}-small.json").read_text())
    graph, _ = compile_small_import(sample, CompilePolicy(30))
    source_hash = pilot_review("report-proof", case).sources[0].sha256
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != source_hash:
        raise ValueError(f"{case} supplied PDF differs from reviewed source")
    proof = run_pilot_proof(graph, case=case, start=start, end=end, closed_edge=closed,
                            deadline=deadline, scope_hash=geography.scope_digest,
                            graph_hash=geography.graph_sha256, source_hash=source_hash)
    service = ReviewService(lambda selected: pilot_geography(selected).scope_id)
    owner = "local-pilot-operator"
    draft, _ = service.get(owner, case)
    draft, _ = service.confirm_geography(owner, draft.revision, geography.scope_id, case)
    draft, _ = service.declare_bundle(owner, draft.revision, default_assumptions(draft),
                                      DEFAULTS_VERSION, case)
    draft, _ = service.seal(owner, draft.revision, case)
    draft, readiness = service.acknowledge(owner, draft.revision, case)
    if not readiness.ready_to_run or draft.sealed_hash != draft.acknowledged_hash:
        raise AssertionError("reviewed pilot inputs are not sealed and acknowledged")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for kind in ("gap_only", "evaluated"):
        html = OUTPUT / f"{case}-{kind}.html"
        html.write_bytes(render_verified_html(_spec(case, kind, proof), pdf))
        paths[kind + "_html"] = str(html.relative_to(ROOT))
        if render_pdf:
            output = html.with_suffix(".pdf")
            subprocess.run(["node", str(ROOT / "packages/reports/render_pdf.mjs"),
                            str(html), str(output)], cwd=ROOT, check=True, timeout=45)
            paths[kind + "_pdf"] = str(output.relative_to(ROOT))
    record: dict[str, Any] = {
        "case": case, "source_sha256": source_hash, "scope_digest": proof.scope_hash,
        "graph_sha256": proof.graph_hash, "closed_edge_id": closed,
        "deadline_seconds": deadline, "horizon_seconds": 259_200,
        "assumption_bundle": "pilot-trip-water-v1", "status": "hypothetical_local_engineering_proof",
        "reviewed_input_hash": draft.sealed_hash,
        "reviewed_defaults": {item.field: {"value": item.value, "unit": item.unit,
                                          "scope_id": item.scope_id,
                                          "applicable_from": item.applicable_from.isoformat(),
                                          "applicable_through": item.applicable_through.isoformat()}
                              for item in draft.assumptions},
        "review_ready_to_run": readiness.ready_to_run,
        "baseline": [{"member_id": item.member_id, "route_seconds": item.route_seconds,
                      "route_distance_mm": item.route_distance_mm,
                      "route_edge_ids": item.route_edge_ids,
                      "event_hash": item.result.event_hash, "metric_hash": item.result.metric_hash,
                      "events": item.result.events, "metrics": item.result.metrics,
                      "outcome": asdict(item.outcome)} for item in proof.baseline],
        "variant": [{"member_id": item.member_id, "route_seconds": item.route_seconds,
                     "route_distance_mm": item.route_distance_mm,
                     "route_edge_ids": item.route_edge_ids,
                     "event_hash": item.result.event_hash, "metric_hash": item.result.metric_hash,
                     "events": item.result.events, "metrics": item.result.metrics,
                     "outcome": asdict(item.outcome)} for item in proof.variant],
        "comparison_status": proof.comparison_status,
        "comparison_deltas": proof.comparison_deltas, "exports": paths,
    }
    (OUTPUT / f"{case}-pilot-proof.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--no-pdf", action="store_true")
    arguments = parser.parse_args()
    for case, settings in SETTINGS.items():
        record = build(cast(PilotCase, case), arguments.pdf_directory / settings[-1],
                       render_pdf=not arguments.no_pdf)
        print(case, [(item["member_id"], item["outcome"]["on_time_people"],
                      item["outcome"]["water_unmet_ml"]) for item in record["baseline"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
