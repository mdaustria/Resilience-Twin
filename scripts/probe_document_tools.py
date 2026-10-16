"""Bounded local PDF validation probe for Task 3.1; never uploads source PDFs.

This checks tool behavior, not production intake. Run with --require-scanner before
claiming that the approved ClamAV runtime has been verified.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader, PdfWriter
from pypdf.actions import JavaScript
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject, IndirectObject

MAX_PROBE_BYTES = 1_000_000
MAX_PROBE_PAGES = 3
MAX_OBJECT_VISITS = 2_000
ACTIVE_KEYS = {
    "/AA",
    "/JS",
    "/JavaScript",
    "/Launch",
    "/OpenAction",
    "/RichMedia",
    "/EmbeddedFiles",
}


@dataclass(frozen=True)
class ProbeResult:
    case: str
    status: str
    page_count: int | None = None
    reason: str | None = None


def fixture_bytes() -> dict[str, bytes]:
    """Create tiny, original PDFs in memory; user documents are never fixtures."""
    clean = PdfWriter()
    clean.add_blank_page(width=612, height=792)
    clean_buffer = io.BytesIO()
    clean.write(clean_buffer)

    encrypted = PdfWriter()
    encrypted.add_blank_page(width=612, height=792)
    encrypted.encrypt("fixture-password")
    encrypted_buffer = io.BytesIO()
    encrypted.write(encrypted_buffer)

    active = PdfWriter()
    active.add_blank_page(width=612, height=792)
    active.add_open_action(JavaScript("app.alert('local fixture only')"))
    active_buffer = io.BytesIO()
    active.write(active_buffer)

    return {
        "clean": clean_buffer.getvalue(),
        "encrypted": encrypted_buffer.getvalue(),
        "javascript": active_buffer.getvalue(),
        "malformed": b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n",
        "oversized": b"%PDF-1.7\n" + b"x" * MAX_PROBE_BYTES,
    }


def _has_active_content(reader: PdfReader) -> bool:
    """Detect known active PDF entries with a bounded parsed-object walk."""
    pending: list[object] = [reader.trailer]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if isinstance(value, IndirectObject):
            value = value.get_object()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        if len(seen) > MAX_OBJECT_VISITS:
            raise ValueError("PDF object walk exceeded probe limit")
        if isinstance(value, DictionaryObject):
            if ACTIVE_KEYS.intersection(str(key) for key in value):
                return True
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
    return False


def inspect_pdf(case: str, data: bytes) -> ProbeResult:
    """Reject malformed, encrypted, active, or unbounded sample PDFs."""
    if len(data) > MAX_PROBE_BYTES:
        return ProbeResult(case, "rejected", reason="probe byte limit")
    if not data.startswith(b"%PDF-"):
        return ProbeResult(case, "rejected", reason="missing PDF signature")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            return ProbeResult(case, "rejected", reason="encrypted PDF")
        page_count = len(reader.pages)
        if not 1 <= page_count <= MAX_PROBE_PAGES:
            return ProbeResult(case, "rejected", reason="probe page limit")
        if _has_active_content(reader):
            return ProbeResult(case, "rejected", reason="active PDF content")
    except (PdfReadError, ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        return ProbeResult(case, "rejected", reason=f"parse error: {type(exc).__name__}")
    return ProbeResult(case, "accepted", page_count=page_count)


def scan_fixture(scanner: Path, database: Path, data: bytes, fixture_path: Path) -> tuple[int, str]:
    """Scan with a fresh signature database; 0 is clean and 1 is detected."""
    fixture_path.write_bytes(data)
    try:
        result = subprocess.run(
            [
                str(scanner),
                "--no-summary",
                f"--database={database}",
                "--fail-if-cvd-older-than=1",
                str(fixture_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode, (result.stdout + "\n" + result.stderr).strip()[:500]
    finally:
        fixture_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", type=Path, help="Path to approved clamscan executable")
    parser.add_argument("--database", type=Path, help="Path to current ClamAV signature database")
    parser.add_argument("--require-scanner", action="store_true")
    args = parser.parse_args()

    cases = fixture_bytes()
    results = [inspect_pdf(case, data) for case, data in cases.items()]
    expected = {
        "clean": "accepted",
        "encrypted": "rejected",
        "javascript": "rejected",
        "malformed": "rejected",
        "oversized": "rejected",
    }
    report: dict[str, object] = {
        "pypdf_version": __import__("pypdf").__version__,
        "cases": [asdict(result) for result in results],
        "scanner_status": "not_run",
    }
    if any(result.status != expected[result.case] for result in results):
        print(json.dumps(report, indent=2))
        return 1

    scanner = args.scanner or (Path(os.environ["CLAMSCAN_PATH"]) if "CLAMSCAN_PATH" in os.environ else None)
    database = args.database or (Path(os.environ["CLAMAV_DB_PATH"]) if "CLAMAV_DB_PATH" in os.environ else None)
    if scanner is not None:
        if not scanner.is_file() or database is None or not database.is_dir():
            report["scanner_status"] = "missing_binary_or_database"
        else:
            version = subprocess.run(
                [str(scanner), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            report["scanner_version"] = version.stdout.strip()
            # The host antivirus may quarantine EICAR before ClamAV can read it.
            # A temporary custom signature tests ClamAV's detection path using
            # an innocuous phrase without weakening host protection.
            probe_phrase = b"ResilienceTwinScannerProbe20261013"
            probe_name = "ResilienceTwin.Scanner.Probe"
            probe_signature = database / f"resilience-twin-probe-{os.getpid()}.ndb"
            local_temp = Path.cwd() / ".runtime" / "tmp"
            probe_signature.write_text(f"{probe_name}:0:*:{probe_phrase.hex()}\n", encoding="ascii")
            try:
                with TemporaryDirectory(dir=local_temp if local_temp.is_dir() else None) as temporary:
                    clean_code, clean_detail = scan_fixture(scanner, database, cases["clean"], Path(temporary) / "clean.pdf")
                    detected_code, detected_detail = scan_fixture(
                        scanner, database, probe_phrase, Path(temporary) / "probe.txt"
                    )
            finally:
                probe_signature.unlink(missing_ok=True)
            report["scanner_clean_exit"] = clean_code
            report["scanner_detection_exit"] = detected_code
            if clean_code != 0:
                report["scanner_clean_detail"] = clean_detail
            if detected_code != 1:
                report["scanner_detection_detail"] = detected_detail
            report["scanner_status"] = (
                "verified"
                if version.returncode == 0
                and version.stdout.startswith("ClamAV 1.5.4")
                and clean_code == 0
                and detected_code == 1
                and probe_name in detected_detail
                else "failed"
            )
    print(json.dumps(report, indent=2))
    if args.require_scanner and report["scanner_status"] != "verified":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
