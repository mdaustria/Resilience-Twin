"""Run or replay source-bound Gemini PDF groups with a local cost ceiling."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from packages.adapters.ai import GeminiPdfAdapter, SavedResponseAdapter
from packages.application.extraction import extract_group
from packages.contracts.evidence import PageGroup, PageRegion

SOURCES = {
    "qc": ("95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b", 112),
    "guiguinto": ("b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95", 191),
}
EXTRACTOR_VERSION = "gemini-3.8-flash-v1.1-20261014"
INPUT_USD_PER_MILLION = 0.75
OUTPUT_USD_PER_MILLION = 3.75
WORST_CALL_USD = (1_048_576 * INPUT_USD_PER_MILLION + 8_192 * OUTPUT_USD_PER_MILLION) / 1_000_000


def page_groups(label: str, digest: str, count: int) -> tuple[PageGroup, ...]:
    cuts = (112,) if label == "qc" else (83, 84, 119, 121, 191)
    groups: list[PageGroup] = []
    start = 1
    for cut in cuts:
        while start <= cut:
            end = min(start + 7, cut)
            pages = tuple(range(start, end + 1))
            regions: list[PageRegion] = []
            for page in pages:
                if page == 84 and label == "guiguinto":
                    regions.append(PageRegion(physical_page=page, region_id="p84_image_table",
                                              kind="image_table"))
                elif page in (120, 121) and label == "guiguinto":
                    other = 121 if page == 120 else 120
                    regions.append(PageRegion(physical_page=page, region_id=f"p{page}_split_table",
                                              kind="split_table", linked_region_id=f"p{other}_split_table"))
                    regions.append(PageRegion(physical_page=page, region_id=f"p{page}_graphic_marks",
                                              kind="graphic_marks"))
                else:
                    regions.append(PageRegion(physical_page=page, region_id=f"p{page}", kind="text"))
            groups.append(PageGroup(document_sha256=digest, physical_page_count=count,
                                    pages=pages, regions=tuple(regions)))
            start = end + 1
    return tuple(groups)


def _cost(usage: dict[str, int | None]) -> float:
    incoming = usage.get("input_tokens")
    total = usage.get("total_tokens")
    if incoming is None or total is None or total < incoming:
        raise ValueError("Provider usage is unavailable; stop before further calls")
    return (incoming * INPUT_USD_PER_MILLION + (total - incoming) * OUTPUT_USD_PER_MILLION) / 1_000_000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("release/validation/extraction"))
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--max-live-calls", type=int, default=1)
    parser.add_argument("--max-estimated-usd", type=float, default=5.0)
    args = parser.parse_args()
    if not 0 <= args.max_live_calls <= 40 or not 0 < args.max_estimated_usd <= 5:
        raise ValueError("Pilot call or cost bound is invalid")
    configuration = json.loads(Path("release/providers.json").read_text(encoding="utf-8"))["gemini"]
    if (not configuration.get("pilot_source_document_upload_allowed")
            or configuration["model_id"] != "gemini-3.8-flash"):
        raise ValueError("Pilot source processing is not configured")
    digest, count = SOURCES[args.source]
    source = args.pdf.read_bytes()
    if hashlib.sha256(source).hexdigest() != digest:
        raise ValueError("The supplied PDF does not match the admitted public source")
    if not 1 <= args.start_page <= (args.end_page or count) <= count:
        raise ValueError("Invalid physical-page range")
    groups = tuple(group for group in page_groups(args.source, digest, count)
                   if group.pages[0] >= args.start_page and group.pages[-1] <= (args.end_page or count))
    if not groups:
        raise ValueError("The range contains no complete page group")
    raw_dir = args.output_dir / "raw"
    batch_dir = args.output_dir / "batches"
    raw_dir.mkdir(parents=True, exist_ok=True)
    batch_dir.mkdir(parents=True, exist_ok=True)
    adapter: GeminiPdfAdapter | None = None
    live_calls = 0
    estimated_usd = 0.0
    records: list[dict[str, object]] = []
    try:
        for group in groups:
            stem = f"{args.source}-p{group.pages[0]:03d}-{group.pages[-1]:03d}-v11"
            raw_path = raw_dir / f"{stem}.json"
            batch_path = batch_dir / f"{stem}.json"
            if raw_path.is_file():
                mode = "replay"
                usage: dict[str, int | None] = {}
                response_id = None
            else:
                if live_calls >= args.max_live_calls:
                    break
                if estimated_usd + WORST_CALL_USD > args.max_estimated_usd:
                    raise ValueError("Pilot cost ceiling reached before the next request")
                if adapter is None:
                    adapter = GeminiPdfAdapter(args.pdf, expected_sha256=digest)
                mode = "live"
                raw_path.write_bytes(adapter.extract(group))
            batch = extract_group(
                group,
                SavedResponseAdapter(raw_path, expected_document_sha256=digest),
                extractor_version=EXTRACTOR_VERSION,
            )
            if mode == "live":
                if batch.raw_sha256 is None:
                    raise ValueError("Live provider call failed; no raw response was received")
                if adapter is None:
                    raise RuntimeError("Live adapter was not initialized")
                usage = adapter.last_usage
                response_id = adapter.last_response_id
                estimated_usd += _cost(usage)
                live_calls += 1
            else:
                previous = json.loads(batch_path.read_text(encoding="utf-8")) if batch_path.is_file() else {}
                usage = previous.get("usage", {})
                response_id = previous.get("response_id")
                if usage:
                    estimated_usd += _cost(usage)
            record = {
                "source": args.source,
                "document_sha256": digest,
                "group_pages": list(group.pages),
                "extractor_version": EXTRACTOR_VERSION,
                "mode": mode,
                "raw_sha256": batch.raw_sha256,
                "candidate_count": len(batch.candidates),
                "coverage": [item.model_dump(mode="json") for item in batch.coverage],
                "issues": [item.model_dump(mode="json") for item in batch.issues],
                "usage": usage,
                "response_id": response_id,
            }
            batch_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            records.append(record)
            print(json.dumps({"group": stem, "mode": mode, "candidates": len(batch.candidates),
                              "issues": len(batch.issues), "estimated_usd": round(estimated_usd, 6)}),
                  flush=True)
    finally:
        if adapter is not None:
            adapter.close()
    print(json.dumps({"source": args.source, "groups_processed": len(records),
                      "live_calls": live_calls, "estimated_usd": round(estimated_usd, 6)}))


if __name__ == "__main__":
    main()
