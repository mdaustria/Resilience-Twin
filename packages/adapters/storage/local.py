"""Workspace-scoped local PDF artifact storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from packages.application.documents import WORKSPACE_ID, IntakeError


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _workspace(self, workspace_id: str) -> Path:
        if not WORKSPACE_ID.fullmatch(workspace_id):
            raise IntakeError("invalid_workspace", "A valid workspace is required.")
        return self.root / workspace_id

    def quarantine(self, workspace_id: str, source: bytes) -> Path:
        directory = self._workspace(workspace_id) / "quarantine"
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="upload-", suffix=".pdf", dir=directory)
        path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as staged:
                staged.write(source)
                staged.flush()
                os.fsync(staged.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def publish(self, workspace_id: str, digest: str, quarantined_path: Path) -> str:
        workspace = self._workspace(workspace_id)
        if quarantined_path.parent.resolve() != (workspace / "quarantine").resolve():
            raise IntakeError("invalid_quarantine", "The upload is outside its workspace quarantine.")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise IntakeError("invalid_digest", "The upload checksum is invalid.")
        data = quarantined_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise IntakeError("source_changed", "The quarantined PDF changed during validation.")
        directory = workspace / "documents"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest}.pdf"
        try:
            with destination.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        except FileExistsError:
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise IntakeError("artifact_conflict", "Stored document identity conflicts with this upload.") from None
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return f"{workspace_id}/documents/{digest}.pdf"

    def discard(self, quarantined_path: Path) -> None:
        quarantined_path.unlink(missing_ok=True)


__all__ = ["LocalArtifactStore"]
