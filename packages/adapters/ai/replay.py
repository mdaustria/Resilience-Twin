"""Offline saved-response replay; never contacts a provider."""

from __future__ import annotations

from pathlib import Path

from packages.contracts.evidence import PageGroup


class SavedResponseAdapter:
    def __init__(self, response_path: Path, *, expected_document_sha256: str) -> None:
        self.response_path = response_path
        self.expected_document_sha256 = expected_document_sha256

    def extract(self, group: PageGroup) -> bytes:
        if group.document_sha256 != self.expected_document_sha256:
            raise ValueError("Saved extraction response belongs to a different source")
        return self.response_path.read_bytes()


__all__ = ["SavedResponseAdapter"]
