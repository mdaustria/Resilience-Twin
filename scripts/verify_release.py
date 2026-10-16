"""Fail-closed evidence manifest check for milestone A."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_A = (
    "frozen_protocol", "boundary_replay", "reference_scores", "sensitivity",
    "routing_review", "dependency_review", "geography_review", "engineering_discrepancies",
    "qc_full_extraction", "qc_source_only_gaps", "qc_supplemented_run",
    "guiguinto_full_extraction", "guiguinto_source_only_gaps",
    "guiguinto_supplemented_run",
)
CASE_PAGES = {"qc": 112, "guiguinto": 191}
REQUIRED_B = ("qc_journey", "guiguinto_journey", "accessibility",
              "isolation_lifecycle", "browser_checks")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON object required: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_issues(records: dict[str, Any], root: Path) -> list[str]:
    """Require distinct, coherent source-gap-run evidence, beyond file existence."""
    issues: list[str] = []
    try:
        intake = _read_json(root / "release/validation/document-intake/full-source-intake.json")
        extraction = _read_json(root / "release/validation/extraction/verification.json")
        adjudication = _read_json(root / "release/validation/extraction/adjudication.json")
        geography = _read_json(root / "release/validation/geography/pilot-areas.json")
        score = _read_json(root / records["reference_scores"]["path"])
        fixture = _read_json(root / "tests/fixtures/validation/cases.json")
        protocol = _read_json(root / records["frozen_protocol"]["path"])
        if score.get("fixture_sha256") != _sha(root / "tests/fixtures/validation/cases.json"):
            issues.append("arithmetic reference fixture hash differs")
        if score.get("tolerances") != protocol["benchmark_classes"][0]["tolerances"]:
            issues.append("arithmetic reference tolerances differ from frozen protocol")
        if any(score.get("scores", {}).get(row["id"]) != row["reference"]
               for row in fixture["cases"]):
            issues.append("arithmetic reference scores differ from frozen references")
        if score.get("discrepancies") != []:
            issues.append("arithmetic reference discrepancies remain")
        boundary = _read_json(root / records["boundary_replay"]["path"])
        if "21 passed" not in boundary.get("result", "") or boundary.get("field_validation_claim") is not False:
            issues.append("boundary/replay evidence lacks passing input-based result")
        sensitivity = _read_json(root / records["sensitivity"]["path"])
        if len(sensitivity.get("pairs", [])) != 20 or not sensitivity.get("rank_reversal_case_ids"):
            issues.append("sensitivity/reference-policy evidence is incomplete")
        routing = _read_json(root / records["routing_review"]["path"])
        for case, pages in CASE_PAGES.items():
            extracted = extraction["sources"][case]
            reviewed = adjudication["sources"][case]
            admitted = next(item for item in intake["sources"] if item["source"] == case)
            area = geography["cases"][case]
            full = _read_json(root / records[f"{case}_full_extraction"]["path"])
            gap = _read_json(root / records[f"{case}_source_only_gaps"]["path"])
            proof = _read_json(root / records[f"{case}_supplemented_run"]["path"])
            digest = admitted["sha256"]
            if not (admitted["original_bytes_preserved"] and admitted["quarantine_cleared"]
                    and admitted["mapped_pages"] == pages == admitted["physical_page_count"]
                    == extracted["physical_pages_covered"] == reviewed["physical_pages"]
                    and extracted["unresolved_regions"] == 0 and extracted["failed_regions"] == 0
                    and reviewed["critical_items_total"] == reviewed["critical_items_reviewed"]
                    and digest == extracted["document_sha256"] == reviewed["document_sha256"]
                    == full.get("source_sha256")):
                issues.append(f"{case} full PDF intake/extraction/adjudication incoherent")
            if full.get("critical_items_reviewed") != reviewed["critical_items_total"]:
                issues.append(f"{case} critical extraction count differs")
            html = root / gap["html_path"]
            pdf = root / gap["pdf_path"]
            if not (html.is_file() and pdf.is_file() and gap.get("source_sha256") == digest
                    and gap.get("source_only") is True and gap.get("metric_count") == 0
                    and gap.get("gap_fields") == ["evacuee_people", "shelter_capacity_people",
                                                  "vehicle_seats", "opening_water_ml"]
                    and gap.get("html_sha256") == _sha(html)
                    and gap.get("pdf_sha256") == _sha(pdf)
                    and "Measured outcomes" not in html.read_text(encoding="utf-8")):
                issues.append(f"{case} source-only gap report missing or contains measured results")
            evaluated_html = root / proof["exports"]["evaluated_html"]
            evaluated_pdf = root / proof["exports"]["evaluated_pdf"]
            if not (proof.get("source_sha256") == digest
                    and proof.get("scope_digest") == area["scope_digest"]
                    and proof.get("graph_sha256") == area["graph_sha256"]
                    == routing["sources"][case]["graph_sha256"]
                    and proof.get("comparison_status") == "complete"
                    and proof.get("review_ready_to_run") is True
                    and isinstance(proof.get("reviewed_input_hash"), str)
                    and len(proof["reviewed_input_hash"]) == 64
                    and len(proof.get("baseline", [])) == len(proof.get("variant", [])) == 2
                    and {item["member_id"] for item in proof["baseline"]}
                    == {"normal", "road_close"}
                    and evaluated_html.is_file() and evaluated_pdf.is_file()
                    and "Measured outcomes" in evaluated_html.read_text(encoding="utf-8")):
                issues.append(f"{case} supplemented run, review seal or export incomplete")
            else:
                for collection in (proof["baseline"], proof["variant"]):
                    for item in collection:
                        if not item.get("event_hash") or not item.get("metric_hash") or not item.get("events"):
                            issues.append(f"{case} run event/metric evidence incomplete")
                if [item["outcome"]["on_time_people"] for item in proof["baseline"]] != [20, 0]:
                    issues.append(f"{case} baseline/disruption outcome differs")
                if any(item["outcome"]["water_unmet_ml"] != 0 for item in proof["variant"]):
                    issues.append(f"{case} hypothetical water variant differs")
    except (KeyError, TypeError, ValueError, OSError) as error:
        issues.append(f"milestone A semantic evidence unreadable: {error}")
    return issues


def verify_a(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    milestone = manifest.get("milestone_a", {})
    if not isinstance(milestone, dict):
        return ["milestone_a must be an object"]
    if milestone.get("status") != "accepted":
        issues.append("milestone_a status is not accepted")
    records = milestone.get("evidence", {})
    if not isinstance(records, dict):
        return ["milestone_a.evidence must be an object"]
    seen_paths: set[Path] = set()
    for key in REQUIRED_A:
        record = records.get(key)
        if not isinstance(record, dict):
            issues.append(f"missing evidence: {key}")
            continue
        path_text = record.get("path")
        digest = record.get("sha256")
        if not isinstance(path_text, str) or not path_text or not isinstance(digest, str):
            issues.append(f"incomplete evidence reference: {key}")
            continue
        path = (root / path_text).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            issues.append(f"missing or outside-workspace evidence file: {key}")
            continue
        if path in seen_paths:
            issues.append(f"evidence file reused across requirements: {key}")
        seen_paths.add(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            issues.append(f"evidence checksum mismatch: {key}")
        if key == "engineering_discrepancies":
            try:
                findings = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                issues.append("engineering discrepancy evidence must be JSON")
                continue
            if not isinstance(findings, dict) or (
                findings.get("scope") != "input_based_engineering"
                or not findings.get("checked_on")
                or findings.get("unresolved_critical") != []
            ):
                issues.append("engineering evidence needs dated scope and no unresolved critical issues")
    if manifest.get("schema_version") == "acceptance.v2" and not issues:
        issues.extend(_case_issues(records, root))
    return issues


def verify_b(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Accept only checked, source-specific complete browser journeys."""
    issues = verify_a(manifest, root)
    milestone = manifest.get("milestone_b")
    if not isinstance(milestone, dict):
        return issues + ["milestone_b evidence is missing"]
    if milestone.get("status") != "accepted":
        issues.append("milestone_b status is not accepted")
    records = milestone.get("evidence")
    if not isinstance(records, dict):
        return issues + ["milestone_b evidence index is missing"]
    data: dict[str, dict[str, Any]] = {}
    seen: set[Path] = set()
    for name in REQUIRED_B:
        record = records.get(name)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            issues.append(f"missing milestone B evidence: {name}")
            continue
        path = (root / record["path"]).resolve()
        if (not path.is_relative_to(root.resolve()) or not path.is_file()
                or path in seen or record.get("sha256") != _sha(path)):
            issues.append(f"missing, reused or changed milestone B evidence: {name}")
            continue
        seen.add(path)
        try:
            data[name] = _read_json(path)
        except (ValueError, TypeError, OSError):
            issues.append(f"invalid milestone B JSON: {name}")
    intake = _read_json(root / "release/validation/document-intake/full-source-intake.json")
    for case, pages in CASE_PAGES.items():
        journey = data.get(f"{case}_journey")
        if journey is None:
            continue
        source = next(item for item in intake["sources"] if item["source"] == case)
        if (journey.get("case") != case or journey.get("source_sha256") != source["sha256"]
                or journey.get("source_byte_size") != source["byte_size"]
                or journey.get("physical_pages") != pages
                or journey.get("original_bytes_preserved") is not True
                or journey.get("guest_without_sign_in") is not True
                or journey.get("source_only_gap_export") is not True
                or journey.get("supplemented_review_ready") is not True
                or journey.get("sealed_baseline") is not True
                or journey.get("sealed_scenario_suite") is not True
                or journey.get("completed_baseline_members", 0) < 2
                or journey.get("completed_variant_members", 0) < 2
                or journey.get("paired_comparison_status") != "complete"
                or journey.get("completed_report_download") is not True
                or journey.get("source_only_report_has_measured_metrics") is not False
                or not journey.get("run_event_hashes")
                or not journey.get("run_metric_hashes")
                or not journey.get("downloaded_report_sha256")):
            issues.append(f"{case} public journey evidence is incomplete or source-mismatched")
        if case == "qc" and journey.get("selected_area_not_whole_city") is not True:
            issues.append("QC selected-area limitation is missing")
    access = data.get("accessibility", {})
    if not all(access.get(key) is True for key in (
        "keyboard_navigation", "text_status_units", "map_table_equivalence",
        "citation_access", "download_access")):
        issues.append("accessibility evidence is incomplete")
    lifecycle = data.get("isolation_lifecycle", {})
    if not all(lifecycle.get(key) is True for key in (
        "independent_sessions", "same_pdf_isolation", "reconnect",
        "retry", "expiry_revokes", "end_deletes")):
        issues.append("isolation/lifecycle evidence is incomplete")
    browser = data.get("browser_checks", {})
    if (browser.get("public_journeys_passed") is not True
            or browser.get("accessibility_passed") is not True
            or browser.get("skipped") != 0):
        issues.append("named milestone B browser checks did not pass")
    return issues


def prepare_a(root: Path = ROOT) -> None:
    """Assemble small case-specific records from already saved, reviewed proof artifacts."""
    output = root / "release/validation/milestone-a"
    intake = _read_json(root / "release/validation/document-intake/full-source-intake.json")
    extraction = _read_json(root / "release/validation/extraction/verification.json")
    adjudication = _read_json(root / "release/validation/extraction/adjudication.json")
    for case in CASE_PAGES:
        admitted = next(item for item in intake["sources"] if item["source"] == case)
        extracted = extraction["sources"][case]
        reviewed = adjudication["sources"][case]
        full = {
            "schema_version": "milestone-a-full-extraction.v1", "case": case,
            "source_sha256": admitted["sha256"], "source_byte_size": admitted["byte_size"],
            "physical_pages": admitted["physical_page_count"],
            "intake_mode": admitted["ownership_mode"],
            "original_bytes_preserved": admitted["original_bytes_preserved"],
            "provider_groups": reviewed["provider_groups"],
            "physical_pages_covered": extracted["physical_pages_covered"],
            "region_coverage_records": extracted["region_coverage_records"],
            "failed_regions": extracted["failed_regions"],
            "unresolved_regions": extracted["unresolved_regions"],
            "critical_items_reviewed": reviewed["critical_items_reviewed"],
            "critical_items": reviewed["items"],
            "review_warnings": reviewed["review_warnings"],
            "intake_path": "release/validation/document-intake/full-source-intake.json",
            "verification_path": "release/validation/extraction/verification.json",
            "adjudication_path": "release/validation/extraction/adjudication.json",
        }
        (output / f"{case}-full-extraction.json").write_text(
            json.dumps(full, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        html = root / f"release/validation/reports/{case}-gap_only.html"
        pdf = root / f"release/validation/reports/{case}-gap_only.pdf"
        gap = {
            "schema_version": "milestone-a-source-only-gaps.v1", "case": case,
            "source_sha256": admitted["sha256"], "source_only": True, "metric_count": 0,
            "gap_fields": ["evacuee_people", "shelter_capacity_people",
                           "vehicle_seats", "opening_water_ml"],
            "html_path": str(html.relative_to(root)).replace("\\", "/"),
            "html_sha256": _sha(html),
            "pdf_path": str(pdf.relative_to(root)).replace("\\", "/"),
            "pdf_sha256": _sha(pdf),
            "readiness": "source_only_document_review; simulation_not_performed",
        }
        (output / f"{case}-source-only-gaps.json").write_text(
            json.dumps(gap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = {
        "frozen_protocol": "release/validation/protocol.json",
        "boundary_replay": "release/validation/milestone-a/boundary-replay.json",
        "reference_scores": "release/validation/milestone-a/reference-scores.json",
        "sensitivity": "release/validation/sensitivity/tiny-expanded.json",
        "routing_review": "release/validation/milestone-a/routing-review.json",
        "dependency_review": "release/dependencies.md",
        "geography_review": "release/validation/geography/pilot-areas.json",
        "engineering_discrepancies": "release/validation/milestone-a/engineering-discrepancies.json",
        **{f"{case}_full_extraction": f"release/validation/milestone-a/{case}-full-extraction.json"
           for case in CASE_PAGES},
        **{f"{case}_source_only_gaps": f"release/validation/milestone-a/{case}-source-only-gaps.json"
           for case in CASE_PAGES},
        **{f"{case}_supplemented_run": f"release/validation/reports/{case}-pilot-proof.json"
           for case in CASE_PAGES},
    }
    manifest = {"schema_version": "acceptance.v2", "milestone_a": {
        "status": "accepted", "claim_scope": "input_based_engineering_only",
        "accepted_on": "2026-10-14",
        "evidence": {key: {"path": path, "sha256": _sha(root / path)}
                     for key, path in paths.items()},
    }}
    issues = verify_a(manifest, root)
    if issues:
        raise ValueError("Cannot prepare milestone A: " + "; ".join(issues))
    (root / "release/acceptance.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", choices=("A", "B", "C"), required=True)
    parser.add_argument("--prepare", action="store_true",
                        help="assemble saved source-specific evidence after checks pass")
    args = parser.parse_args()
    if args.milestone == "C":
        print("Milestone C verifier is not implemented")
        return 2
    if args.prepare and args.milestone != "A":
        print("Milestone B evidence must come from completed browser checks")
        return 2
    if args.prepare:
        prepare_a()
    manifest = json.loads((ROOT / "release/acceptance.json").read_text(encoding="utf-8"))
    issues = verify_a(manifest) if args.milestone == "A" else verify_b(manifest)
    if issues:
        print(f"Milestone {args.milestone} NOT ACCEPTED:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print(f"Milestone {args.milestone} evidence references passed; input-based exploratory scope only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
