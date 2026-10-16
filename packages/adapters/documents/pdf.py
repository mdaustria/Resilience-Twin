"""Strict, bounded structural PDF validation without text extraction."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject, IndirectObject

from packages.application.documents import IntakeError

ACTIVE_KEYS = frozenset({"/AA", "/JS", "/JavaScript", "/Launch", "/OpenAction", "/RichMedia", "/EmbeddedFiles"})
MAX_OBJECT_VISITS = 200_000


def _has_active_content(reader: PdfReader) -> bool:
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
            raise IntakeError("complex_pdf", "The PDF has too many structural objects to validate.")
        if isinstance(value, DictionaryObject):
            if ACTIVE_KEYS.intersection(str(key) for key in value):
                return True
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
    return False


class PypdfValidator:
    def physical_page_count(self, quarantined_path: Path, max_pages: int) -> int:
        try:
            reader = PdfReader(str(quarantined_path), strict=True)
            if reader.is_encrypted:
                raise IntakeError("encrypted_pdf", "Encrypted PDFs are not supported; upload an unlocked copy.")
            count = len(reader.pages)
            if count < 1:
                raise IntakeError("empty_pdf", "The PDF has no physical pages.")
            if count > max_pages:
                raise IntakeError("page_limit", "The PDF exceeds the published physical-page limit.")
            if _has_active_content(reader):
                raise IntakeError("unsafe_pdf", "The PDF contains unsupported active content.")
            return count
        except (PdfReadError, ValueError, TypeError, KeyError, IndexError, RecursionError, OSError) as exc:
            raise IntakeError("malformed_pdf", "The PDF cannot be read safely; upload a repaired copy.") from exc


__all__ = ["PypdfValidator"]
