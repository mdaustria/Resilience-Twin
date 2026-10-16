"""Private PDF upload, finalization and download authorization."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client
from pypdf import PdfWriter

from packages.adapters.documents.pdf import PypdfValidator
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from packages.application.documents import PrivateDocuments
from services.api.documents import session_owner_resolver
from services.api.main import create_app

ORIGIN = "https://resilience.example"
KEY = b"test-only-secret-32-bytes-at-least!!"


class CleanScanner:
    def scan(self, path: Path) -> None:
        assert path.read_bytes().startswith(b"%PDF-")


def pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def setup(client: Client) -> tuple[TestClient, MemoryObjectStore, FirestoreRepository]:
    now = datetime.now(UTC)
    temporary = FirestoreTemporarySessions(client, clock=lambda: now,
                                           issuance_check=lambda: True)
    repository = FirestoreRepository(client)
    objects = MemoryObjectStore()
    documents = PrivateDocuments(repository, objects, CleanScanner(), PypdfValidator(),
                                 secret=KEY, clock=lambda: now)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_documents=documents,
        private_owner_for=session_owner_resolver(temporary, repository),
        session_origin=ORIGIN, session_csrf_key=KEY)
    return TestClient(app, base_url=ORIGIN), objects, repository


def test_guest_upload_finalization_and_cross_owner_denial(firestore_client: Client) -> None:
    alice, objects, repository = setup(firestore_client)
    guest = alice.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN}).json()
    csrf = guest["csrf_token"]
    workspace = guest["workspace_id"]
    source = pdf()
    base = f"/api/v1/workspaces/{workspace}/documents/uploads"
    begin = alice.post(base, json={"sha256": hashlib.sha256(source).hexdigest(),
                                   "byte_count": len(source)}, headers={
        "Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert begin.status_code == 201, begin.text
    grant = begin.json()
    assert alice.post(f"{base}/{grant['upload_id']}/content", content=source,
                      headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code == 422
    uploaded = alice.post(f"{base}/{grant['upload_id']}/content", content=source, headers={
        "Origin": ORIGIN, "X-CSRF-Token": csrf, "X-Upload-Token": grant["token"]})
    assert uploaded.status_code == 200, uploaded.text
    finalized = alice.post(f"{base}/{grant['upload_id']}/finalize", json={
        "token": grant["token"], "quarantine_generation": uploaded.json()["generation"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "If-Match": "0"})
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["sha256"] == hashlib.sha256(source).hexdigest()
    download = alice.get(f"/api/v1/workspaces/{workspace}/artifacts/{grant['upload_id']}/download")
    assert download.status_code == 200 and download.content == source
    assert download.headers["Cache-Control"] == "private, no-store"
    assert len(objects.objects) == 1
    bob, _, _ = setup(firestore_client)
    bob_csrf = bob.post("/api/v1/temporary-sessions",
                        headers={"Origin": ORIGIN}).json()["csrf_token"]
    assert bob.post(base, json={"sha256": hashlib.sha256(source).hexdigest(),
                                "byte_count": len(source)}, headers={
        "Origin": ORIGIN, "X-CSRF-Token": bob_csrf}).status_code == 404
    assert bob.get(f"/api/v1/workspaces/{workspace}/artifacts/{grant['upload_id']}/download").status_code in (403, 404)
    assert bob.post(f"{base}/{grant['upload_id']}/finalize", json={
        "token": grant["token"], "quarantine_generation": uploaded.json()["generation"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": bob_csrf, "If-Match": "1"}).status_code == 404
    owner_id = firestore_client.document(f"workspaces/{workspace}").get().to_dict()["owner_id"]
    assert repository.get_record(Actor("temporary", owner_id), workspace, "artifacts",
                                 grant["upload_id"])["generation"] == uploaded.json()["generation"] + 1


def test_storage_rules_deny_direct_client_access() -> None:
    rules = Path("storage.rules").read_text(encoding="utf-8")
    assert "allow read, write: if false;" in rules
