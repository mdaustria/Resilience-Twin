"""Temporary download checks authorization between chunks."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.cloud.firestore_v1 import Client
from pypdf import PdfWriter

from packages.adapters.documents.pdf import PypdfValidator
from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from packages.application.documents import IntakeError, PrivateDocuments
from packages.application.sessions import SessionUnavailable


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


class CleanScanner:
    def scan(self, path: Path) -> None:
        assert path.is_file()


def test_expiry_ends_stream_and_upload_grant(firestore_client: Client) -> None:
    clock = Clock()
    sessions = FirestoreTemporarySessions(firestore_client, clock=clock,
                                          issuance_check=lambda: True)
    handle, guest, _ = sessions.issue()
    actor = Actor("temporary", guest.owner_id)
    repository = FirestoreRepository(firestore_client)
    objects = MemoryObjectStore()
    service = PrivateDocuments(repository, objects, CleanScanner(), PypdfValidator(),
                               secret=b"test-only-secret-32-bytes-at-least!!", clock=clock)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    source = output.getvalue()
    grant = service.begin(actor, guest.workspace_id, sha256=hashlib.sha256(source).hexdigest(),
                          byte_count=len(source), temporary_expires_at=guest.expires_at)
    assert grant.expires_at <= guest.expires_at
    staged = service.upload(actor, guest.workspace_id, grant.token, source)
    artifact_id, _, _ = service.finalize(actor, guest.workspace_id, grant.token,
                                        quarantine_generation=staged.generation,
                                        expected_revision=0)

    def authorize() -> Actor:
        current = sessions.resolve(handle)
        return Actor("temporary", current.owner_id)

    stream = service.stream(authorize, guest.workspace_id, artifact_id, chunk_size=64)
    assert next(stream) == source[:64]
    clock.now = guest.expires_at
    with pytest.raises((SessionUnavailable, AccessDenied)):
        next(stream)
    with pytest.raises(IntakeError):
        service.upload(actor, guest.workspace_id, grant.token, source)
