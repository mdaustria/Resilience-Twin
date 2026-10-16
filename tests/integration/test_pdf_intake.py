"""Synthetic end-to-end local intake cases; no supplied source is a fixture."""

from __future__ import annotations

import hashlib
import io
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.actions import JavaScript

from packages.adapters.documents import ClamAvScanner, PypdfValidator
from packages.adapters.storage.local import LocalArtifactStore
from packages.application.documents import IntakeError, LocalPdfIntake
from packages.contracts.documents import INTAKE_POLICIES, IntakePolicy, OwnershipMode


class CleanScanner:
    def scan(self, quarantined_path: Path) -> None:
        assert quarantined_path.is_file()


class RejectingScanner:
    def scan(self, quarantined_path: Path) -> None:
        raise IntakeError("scan_failed", "The PDF scan could not complete.")


class ChangingScanner:
    def scan(self, quarantined_path: Path) -> None:
        quarantined_path.write_bytes(quarantined_path.read_bytes() + b"\n% changed")


def pdf_bytes(pages: int = 1, *, encrypted: bool = False, active: bool = False) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if encrypted:
        writer.encrypt("fixture-password")
    if active:
        writer.add_open_action(JavaScript("app.alert('fixture')"))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def intake(root: Path, *, scanner: CleanScanner | RejectingScanner | None = None,
           policy: IntakePolicy | None = None) -> LocalPdfIntake:
    policies = None if policy is None else {"temporary": policy, "saved": policy}
    return LocalPdfIntake(scanner=scanner or CleanScanner(), validator=PypdfValidator(),
                          store=LocalArtifactStore(root), policies=policies)


@pytest.mark.parametrize("mode", ["temporary", "saved"])
def test_original_bytes_checksum_and_all_physical_pages(tmp_path: Path, mode: OwnershipMode) -> None:
    source = pdf_bytes(3)
    artifact = intake(tmp_path).accept(workspace_id="example", ownership_mode=mode, source=source)
    assert (tmp_path / artifact.storage_key).read_bytes() == source
    assert artifact.sha256 == hashlib.sha256(source).hexdigest()
    assert artifact.physical_page_count == 3
    assert [page.physical_page for page in artifact.pages] == [1, 2, 3]
    assert all(page.coverage_status == "unresolved" for page in artifact.pages)
    assert all(page.extraction_method == "none" for page in artifact.pages)
    assert not list((tmp_path / "example" / "quarantine").iterdir())


@pytest.mark.parametrize(("source", "code"), [
    (b"not a pdf", "invalid_signature"),
    (b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n", "malformed_pdf"),
    (pdf_bytes(encrypted=True), "encrypted_pdf"),
    (pdf_bytes(active=True), "unsafe_pdf"),
], ids=["signature", "malformed", "encrypted", "active"])
def test_rejected_files_never_publish(tmp_path: Path, source: bytes, code: str) -> None:
    with pytest.raises(IntakeError) as error:
        intake(tmp_path).accept(workspace_id="example", ownership_mode="temporary", source=source)
    assert error.value.code == code
    assert not list(tmp_path.rglob("documents/*.pdf"))
    assert not list(tmp_path.rglob("quarantine/*.pdf"))


def test_scanner_failure_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(IntakeError, match="scan could not complete"):
        intake(tmp_path, scanner=RejectingScanner()).accept(
            workspace_id="example", ownership_mode="saved", source=pdf_bytes()
        )
    assert not list(tmp_path.rglob("documents/*.pdf"))


def test_quarantine_change_fails_checksum(tmp_path: Path) -> None:
    with pytest.raises(IntakeError) as error:
        intake(tmp_path, scanner=ChangingScanner()).accept(
            workspace_id="example", ownership_mode="saved", source=pdf_bytes()
        )
    assert error.value.code == "source_changed"
    assert not list(tmp_path.rglob("documents/*.pdf"))


def test_published_limits_include_supplied_source_minima() -> None:
    for policy in INTAKE_POLICIES.values():
        assert policy.max_bytes_per_file >= 9_418_109
        assert policy.max_physical_pages_per_file >= 191


def test_byte_and_page_limits_are_inclusive(tmp_path: Path) -> None:
    source = pdf_bytes(2)
    policy = IntakePolicy(max_bytes_per_file=len(source), max_physical_pages_per_file=2)
    assert intake(tmp_path, policy=policy).accept(
        workspace_id="one", ownership_mode="temporary", source=source
    ).physical_page_count == 2
    with pytest.raises(IntakeError) as byte_error:
        intake(tmp_path, policy=IntakePolicy(max_bytes_per_file=len(source) - 1,
                                             max_physical_pages_per_file=2)).accept(
            workspace_id="two", ownership_mode="saved", source=source
        )
    assert byte_error.value.code == "file_too_large"
    with pytest.raises(IntakeError) as page_error:
        intake(tmp_path, policy=IntakePolicy(max_bytes_per_file=len(source),
                                             max_physical_pages_per_file=1)).accept(
            workspace_id="three", ownership_mode="saved", source=source
        )
    assert page_error.value.code == "page_limit"
    assert not list((tmp_path / "three").rglob("documents/*.pdf"))


def test_workspace_isolation_and_immutable_identity(tmp_path: Path) -> None:
    source = pdf_bytes()
    runner = intake(tmp_path)
    first = runner.accept(workspace_id="one", ownership_mode="saved", source=source)
    repeated = runner.accept(workspace_id="one", ownership_mode="saved", source=source)
    second = runner.accept(workspace_id="two", ownership_mode="saved", source=source)
    assert first.storage_key == repeated.storage_key
    assert first.storage_key != second.storage_key
    assert len(list(tmp_path.rglob("documents/*.pdf"))) == 2
    with pytest.raises(IntakeError) as error:
        runner.accept(workspace_id="../escape", ownership_mode="saved", source=source)
    assert error.value.code == "invalid_workspace"


def test_sparse_blank_pages_remain_unresolved(tmp_path: Path) -> None:
    artifact = intake(tmp_path).accept(
        workspace_id="example", ownership_mode="temporary", source=pdf_bytes(2)
    )
    assert len(artifact.pages) == 2
    assert all(page.recovery_reason for page in artifact.pages)


@pytest.mark.parametrize(("returncode", "expected"), [
    (0, None), (1, "unsafe_pdf"), (2, "scan_failed"),
])
def test_scanner_exit_codes_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int, expected: str | None
) -> None:
    executable = tmp_path / "clamscan"
    executable.write_bytes(b"test executable placeholder")
    database = tmp_path / "database"
    database.mkdir()
    quarantined = tmp_path / "sample.pdf"
    quarantined.write_bytes(pdf_bytes())
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(subprocess, "run", run)
    scanner = ClamAvScanner(executable, database)
    if expected is None:
        scanner.scan(quarantined)
    else:
        with pytest.raises(IntakeError) as error:
            scanner.scan(quarantined)
        assert error.value.code == expected
    assert "--fail-if-cvd-older-than=2" in calls[0]


def test_missing_scanner_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(IntakeError) as error:
        ClamAvScanner(tmp_path / "missing", tmp_path / "database").scan(tmp_path / "sample.pdf")
    assert error.value.code == "scanner_unavailable"
