"""Verify full public pilot PDFs through the production local intake adapters."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from packages.adapters.documents import ClamAvScanner, PypdfValidator
from packages.adapters.storage.local import LocalArtifactStore
from packages.application.documents import LocalPdfIntake
from packages.contracts.documents import OwnershipMode

SOURCES: tuple[tuple[str, str, int, int, OwnershipMode], ...] = (
    ("qc", "95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b", 2_943_608, 112, "temporary"),
    ("guiguinto", "b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95", 9_418_109, 191, "saved"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qc-pdf", type=Path, required=True)
    parser.add_argument("--guiguinto-pdf", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    intake = LocalPdfIntake(
        scanner=ClamAvScanner(args.scanner, args.database),
        validator=PypdfValidator(),
        store=LocalArtifactStore(args.artifact_root),
    )
    records: list[dict[str, str | int | bool]] = []
    for (label, expected_hash, expected_bytes, expected_pages, mode), path in zip(
        SOURCES, (args.qc_pdf, args.guiguinto_pdf), strict=True
    ):
        source = path.read_bytes()
        assert len(source) == expected_bytes, f"{label}: source length changed"
        assert hashlib.sha256(source).hexdigest() == expected_hash, f"{label}: source hash changed"
        artifact = intake.accept(workspace_id=f"pilot-{label}-{mode}", ownership_mode=mode, source=source)
        stored = (args.artifact_root / artifact.storage_key).read_bytes()
        assert stored == source, f"{label}: stored bytes differ"
        assert artifact.sha256 == expected_hash
        assert artifact.byte_size == expected_bytes
        assert artifact.physical_page_count == expected_pages
        assert tuple(page.physical_page for page in artifact.pages) == tuple(range(1, expected_pages + 1))
        assert all(page.coverage_status == "unresolved" and page.extraction_method == "none"
                   for page in artifact.pages)
        quarantine = args.artifact_root / f"pilot-{label}-{mode}" / "quarantine"
        assert not list(quarantine.iterdir()), f"{label}: quarantine not cleared"
        records.append({
            "source": label,
            "ownership_mode": mode,
            "sha256": expected_hash,
            "byte_size": expected_bytes,
            "physical_page_count": expected_pages,
            "mapped_pages": len(artifact.pages),
            "unresolved_pages": len(artifact.pages),
            "original_bytes_preserved": True,
            "quarantine_cleared": True,
        })
    output = {"schema_version": "1", "scanner": "ClamAV 1.5.4", "validator": "pypdf 6.20.1", "sources": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
