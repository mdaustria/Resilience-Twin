"""Deletion during work fences attempts and preserves another owner's copy."""

import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client
from pypdf import PdfWriter

from packages.adapters.documents.pdf import PypdfValidator
from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from packages.application.deletion import DeleteWorkspace
from packages.application.documents import PrivateDocuments
from packages.application.sessions import SessionUnavailable
from services.api.documents import session_owner_resolver
from services.api.main import create_app
from services.worker.leases import FirestoreLeases, StaleFence


def test_guest_end_fences_run_upload_and_preserves_same_source_copy(
    firestore_client: Client,
) -> None:
    repository = FirestoreRepository(firestore_client)
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    alice_handle, alice_view, _ = sessions.issue()
    _, bob_view, _ = sessions.issue()
    alice = Actor("temporary", alice_view.owner_id)
    bob = Actor("temporary", bob_view.owner_id)
    alice_workspace, bob_workspace = alice_view.workspace_id, bob_view.workspace_id
    for actor, workspace in ((alice, alice_workspace), (bob, bob_workspace)):
        repository.put_artifact(actor, workspace, "same-source", sha256="a" * 64,
            object_key=f"workspaces/{workspace}/documents/source.pdf", generation=1,
            byte_count=100, kind="source", expected_revision=0)
    job_id = FirestoreJobs(firestore_client).submit(alice, alice_workspace,
        route="runs", idempotency_key="running", stage="simulation",
        input_hash="b" * 64, estimated_units=1, required_seconds=100)["job_id"]
    leases = FirestoreLeases(firestore_client)
    fence = leases.claim(alice_workspace, job_id)
    assert fence == 1
    assert sessions.revoke(alice_handle) is None
    with pytest.raises((AccessDenied, StaleFence)):
        leases.publish(alice_workspace, job_id, fence,
                       artifact_key="attempt/late", result_hash="c" * 64)
    with pytest.raises(AccessDenied):
        repository.put_artifact(alice, alice_workspace, "late-upload",
            sha256="d" * 64, object_key=f"workspaces/{alice_workspace}/documents/late.pdf",
            generation=2, byte_count=100, kind="source", expected_revision=1)
    with pytest.raises(AccessDenied):
        repository.get_workspace(alice, alice_workspace)
    assert repository.get_record(bob, bob_workspace, "artifacts", "same-source")[
        "sha256"] == "a" * 64
    root = firestore_client.collection("workspaces").document(alice_workspace)
    assert root.collection("jobs").document(job_id).get().to_dict()["status"] == "cancelled"
    assert root.collection("runs").document(job_id).get().to_dict()["status"] == "partial"


def test_guest_end_api_preserves_another_session(firestore_client: Client) -> None:
    origin = "https://resilience.example"
    csrf_key = b"test-only-secret-32-bytes-at-least!!"
    temporary = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        workspace_deletion=DeleteWorkspace(temporary),
        private_owner_for=session_owner_resolver(
            temporary, FirestoreRepository(firestore_client)),
        session_origin=origin, session_csrf_key=csrf_key)
    alice = TestClient(app, base_url=origin)
    alice_view = alice.post("/api/v1/temporary-sessions",
                            headers={"Origin": origin}).json()
    bob = TestClient(app, base_url=origin)
    bob_view = bob.post("/api/v1/temporary-sessions",
                        headers={"Origin": origin}).json()
    assert bob_view["workspace_id"] != alice_view["workspace_id"]
    assert alice.delete("/api/v1/temporary-sessions/current", headers={
        "Origin": origin, "X-CSRF-Token": bob_view["csrf_token"]}).status_code == 403
    assert alice.delete("/api/v1/temporary-sessions/current", headers={
        "Origin": origin, "X-CSRF-Token": alice_view["csrf_token"]}).status_code == 204
    assert alice.get("/api/v1/temporary-sessions/current").status_code == 401
    assert bob.get("/api/v1/temporary-sessions/current").json()[
        "workspace_id"] == bob_view["workspace_id"]
    assert bob.delete(f"/api/v1/workspaces/{bob_view['workspace_id']}", headers={
        "Origin": origin, "X-CSRF-Token": bob_view["csrf_token"]}).status_code == 204
    assert bob.get("/api/v1/temporary-sessions/current").status_code == 401


def test_end_cancels_more_than_one_default_page(firestore_client: Client) -> None:
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    handle, guest, _ = sessions.issue()
    root = firestore_client.collection("workspaces").document(guest.workspace_id)
    batch = firestore_client.batch()
    for index in range(103):
        job_id = f"page-job-{index:03d}"
        batch.set(root.collection("jobs").document(job_id), {
            "status": "queued", "fence": 0, "owner_type": "temporary",
            "owner_id": guest.owner_id})
        batch.set(root.collection("runs").document(job_id), {"status": "queued"})
    batch.commit()
    sessions.revoke(handle)
    jobs = list(root.collection("jobs").stream())
    assert len(jobs) == 103
    assert all(row.to_dict()["status"] == "cancelled" for row in jobs)
    assert all(row.to_dict()["fence"] == 1 for row in jobs)
    assert all(row.to_dict()["status"] == "partial"
               for row in root.collection("runs").stream())


def test_end_during_object_read_prevents_next_download_chunk(
    firestore_client: Client,
) -> None:
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    handle, guest, _ = sessions.issue()
    actor = Actor("temporary", guest.owner_id)
    repository = FirestoreRepository(firestore_client)
    objects = MemoryObjectStore()
    payload = b"synthetic private report"
    stored = objects.write_once(
        f"workspaces/{guest.workspace_id}/reports/report.pdf", payload)
    repository.put_artifact(actor, guest.workspace_id, "report",
        sha256=hashlib.sha256(payload).hexdigest(), object_key=stored.key,
        generation=stored.generation, byte_count=stored.byte_count,
        kind="report", expected_revision=0)
    documents = PrivateDocuments(repository, objects, scanner=None, validator=None,
        secret=b"test-only-secret-32-bytes-at-least!!")  # type: ignore[arg-type]
    original_read = objects.read_range

    def end_during_read(key: str, generation: int, start: int, length: int) -> bytes:
        data = original_read(key, generation, start, length)
        sessions.revoke(handle)
        return data

    objects.read_range = end_during_read  # type: ignore[method-assign]

    def authorize() -> Actor:
        return Actor("temporary", sessions.resolve(handle).owner_id)

    with pytest.raises((AccessDenied, SessionUnavailable)):
        next(documents.stream(authorize, guest.workspace_id, "report", chunk_size=8))


def test_end_during_pdf_scan_prevents_upload_finalization(
    firestore_client: Client,
) -> None:
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    handle, guest, _ = sessions.issue()
    actor = Actor("temporary", guest.owner_id)
    repository = FirestoreRepository(firestore_client)
    objects = MemoryObjectStore()

    class EndDuringScan:
        def scan(self, path: Path) -> None:
            assert path.is_file()
            sessions.revoke(handle)

    documents = PrivateDocuments(repository, objects, EndDuringScan(),
        PypdfValidator(), secret=b"test-only-secret-32-bytes-at-least!!")
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    source = output.getvalue()
    grant = documents.begin(actor, guest.workspace_id,
        sha256=hashlib.sha256(source).hexdigest(), byte_count=len(source),
        temporary_expires_at=guest.expires_at)
    staged = documents.upload(actor, guest.workspace_id, grant.token, source)
    with pytest.raises(AccessDenied):
        documents.finalize(actor, guest.workspace_id, grant.token,
                           quarantine_generation=staged.generation,
                           expected_revision=0)
    assert all("/documents/" not in key for key in objects.objects)
    assert not list(firestore_client.collection("workspaces").document(
        guest.workspace_id).collection("artifacts").stream())
