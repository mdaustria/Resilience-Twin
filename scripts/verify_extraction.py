"""Verify complete saved pilot extraction and separate critical-fact reviews."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.application.extraction import validate_response
from scripts.run_pdf_extraction import SOURCES, page_groups

ROOT = Path("release/validation/extraction")


def verify() -> dict[str, object]:
    review = json.loads((ROOT / "adjudication.json").read_text(encoding="utf-8"))["sources"]
    summaries: dict[str, object] = {}
    for label, (digest, count) in SOURCES.items():
        groups = page_groups(label, digest, count)
        reviewed = review[label]
        assert reviewed["document_sha256"] == digest
        assert reviewed["physical_pages"] == count
        assert reviewed["provider_groups"] == len(groups)
        critical = reviewed["items"]
        assert reviewed["critical_items_total"] == reviewed["critical_items_reviewed"] == len(critical)
        assert reviewed["provider_supported"] + reviewed["manual_recovered"] == len(critical)
        assert len({item["id"] for item in critical}) == len(critical)
        assert all(item["disposition"] in ("provider_supported", "manual_recovered") for item in critical)
        assert all(item["source_fact"] and item["physical_pages"] for item in critical)
        assert all(all(1 <= page <= count for page in item["physical_pages"]) for item in critical)
        assert all((ROOT / item["raw_group"]).is_file() for item in critical)
        pages: list[int] = []
        raw_hashes: dict[str, str] = {}
        candidate_count = 0
        coverage_count = 0
        unresolved_count = 0
        failed_count = 0
        issue_codes: dict[str, int] = {}
        estimated_usd = 0.0
        for group in groups:
            stem = f"{label}-p{group.pages[0]:03d}-{group.pages[-1]:03d}-v11"
            raw_path = ROOT / "raw" / f"{stem}.json"
            batch_path = ROOT / "batches" / f"{stem}.json"
            raw = raw_path.read_bytes()
            saved = json.loads(batch_path.read_text(encoding="utf-8"))
            batch = validate_response(group, raw, extractor_version=saved["extractor_version"])
            assert saved["document_sha256"] == digest
            assert saved["group_pages"] == list(group.pages)
            assert saved["raw_sha256"] == batch.raw_sha256 == hashlib.sha256(raw).hexdigest()
            assert saved["candidate_count"] == len(batch.candidates)
            assert saved["coverage"] == [item.model_dump(mode="json") for item in batch.coverage]
            assert saved["issues"] == [item.model_dump(mode="json") for item in batch.issues]
            usage = saved["usage"]
            incoming, total = usage["input_tokens"], usage["total_tokens"]
            assert isinstance(incoming, int) and isinstance(total, int) and total >= incoming
            estimated_usd += (incoming * 0.75 + (total - incoming) * 3.75) / 1_000_000
            raw_hashes[stem] = batch.raw_sha256
            pages.extend(group.pages)
            candidate_count += len(batch.candidates)
            coverage_count += len(batch.coverage)
            unresolved_count += sum(item.status == "unresolved" for item in batch.coverage)
            failed_count += sum(item.status == "failed" for item in batch.coverage)
            for issue in batch.issues:
                issue_codes[issue.code] = issue_codes.get(issue.code, 0) + 1
        assert pages == list(range(1, count + 1))
        summaries[label] = {
            "document_sha256": digest,
            "physical_pages_covered": len(pages),
            "region_coverage_records": coverage_count,
            "unresolved_regions": unresolved_count,
            "failed_regions": failed_count,
            "validated_candidates": candidate_count,
            "issue_codes": issue_codes,
            "critical_items_reviewed": len(critical),
            "provider_supported_critical_items": reviewed["provider_supported"],
            "manual_recovered_critical_items": reviewed["manual_recovered"],
            "estimated_paid_usage_usd": round(estimated_usd, 6),
            "raw_response_sha256": raw_hashes,
        }
    return {"schema_version": "extraction-verification.v1", "sources": summaries}


def main() -> None:
    result = verify()
    output = ROOT / "verification.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sources = result["sources"]
    if not isinstance(sources, dict):
        raise TypeError("Extraction source summaries are missing")
    print(json.dumps({label: {key: value for key, value in summary.items()
                              if key != "raw_response_sha256"}
                      for label, summary in sources.items()}))


if __name__ == "__main__":
    main()
