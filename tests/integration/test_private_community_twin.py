"""Complete supplied PDFs through guest upload and durable source-only review."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.documents import ClamAvScanner, PypdfValidator
from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from packages.application.documents import PrivateDocuments
from packages.application.versions import DurableVersions
from services.api.documents import session_owner_resolver
from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://resilience.example"
KEY = b"guest-community-test-secret-32-bytes!!"
SOURCES = (
    ("qc", "95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b",
     2_943_608, 112, "Quezon City, Metro Manila"),
    ("guiguinto", "b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95",
     9_418_109, 191, "Guiguinto, Bulacan"),
)


def app_for(client: Client, objects: MemoryObjectStore) -> TestClient:
    sessions = FirestoreTemporarySessions(client, issuance_check=lambda: True)
    repository = FirestoreRepository(client)
    scanner = ClamAvScanner(
        ROOT / ".runtime/clamav-1.5.4/clamav-1.5.4.win.x64/clamscan.exe",
        ROOT / ".runtime/clamav-db",
    )
    documents = PrivateDocuments(repository, objects, scanner,
                                 PypdfValidator(), secret=KEY)
    app = create_app(local_fixture_mode=False, temporary_sessions=sessions,
                     private_documents=documents,
                     private_owner_for=session_owner_resolver(sessions, repository),
                     durable_versions=DurableVersions(FirestoreVersionCommands(client)),
                     session_origin=ORIGIN, session_csrf_key=KEY)
    return TestClient(app, base_url=ORIGIN)


@pytest.mark.parametrize("label,digest,size,pages,location", SOURCES)
def test_complete_pdf_guest_intake_and_reconnect_review(
    firestore_client: Client, label: str, digest: str, size: int, pages: int,
    location: str,
) -> None:
    source_path = ROOT / ".runtime/task32-intake" / (
        "pilot-qc-temporary" if label == "qc" else "pilot-guiguinto-saved"
    ) / "documents" / f"{digest}.pdf"
    assert source_path.is_file(), f"Required full {label} PDF is unavailable"
    source = source_path.read_bytes()
    assert len(source) == size and hashlib.sha256(source).hexdigest() == digest
    objects = MemoryObjectStore()
    client = app_for(firestore_client, objects)
    started = client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert started.status_code == 201
    workspace, csrf = started.json()["workspace_id"], started.json()["csrf_token"]
    base = f"/api/v1/workspaces/{workspace}"
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    grant_response = client.post(f"{base}/documents/uploads",
        json={"sha256": digest, "byte_count": size}, headers=headers)
    assert grant_response.status_code == 201, grant_response.text
    grant = grant_response.json()
    transferred = client.post(f"{base}/documents/uploads/{grant['upload_id']}/content",
        content=source, headers={**headers, "X-Upload-Token": grant["token"]})
    assert transferred.status_code == 200, transferred.text
    finalized = client.post(f"{base}/documents/uploads/{grant['upload_id']}/finalize",
        json={"token": grant["token"],
              "quarantine_generation": transferred.json()["generation"]},
        headers={**headers, "If-Match": "0"})
    assert finalized.status_code == 200, finalized.text
    artifact = finalized.json()
    assert (artifact["sha256"], artifact["byte_count"], artifact["page_count"]) == (
        digest, size, pages)
    coverage = client.get(f"{base}/artifacts/{artifact['artifact_id']}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["sha256"] == digest
    assert [item["physical_page"] for item in coverage.json()["pages"]] == list(range(1, pages + 1))
    assert all(item["coverage_status"] == "processed" for item in coverage.json()["pages"])
    assert "verified full-PDF extraction replay" in coverage.json()["review_basis"]
    initial = client.post(f"{base}/reviews/main/initialize", json={
        "artifact_id": artifact["artifact_id"], "title": f"{label} public plan",
        "publication_reference": "Supplied public PDF", "textual_location": location,
        "scenario_date": "2026-10-16",
    }, headers={**headers, "If-Match": "0", "Idempotency-Key": f"{label}-init"})
    assert initial.status_code == 200, initial.text
    record = initial.json()
    assert record["revision"] == 1
    assert record["content"]["draft"]["sources"][0]["sha256"] == digest
    assert record["content"]["readiness"]["document_review_available"] is True
    assert record["content"]["readiness"]["ready_to_run"] is False
    assert record["content"]["readiness"]["source_only_gaps"]
    assert all(claim["physical_page"] <= pages for claim in record["content"]["draft"]["claims"])
    location_url = f"{base}/geography/pilot/{label}"
    location = client.get(location_url)
    assert location.status_code == 200, location.text
    snapshot = location.json()["snapshot"]
    assert snapshot["blockers"] == []
    confirmed = client.post(f"{location_url}/confirm",
        json={"expected_scope_digest": snapshot["scope_digest"]},
        headers={**headers, "If-Match": "1", "Idempotency-Key": f"{label}-location"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["review"]["revision"] == 2
    assert confirmed.json()["review"]["content"]["draft"]["scenario_reviewed"] is True
    assert confirmed.json()["review"]["content"]["draft"]["scope_id"] == snapshot["scope_id"]
    assert confirmed.json()["review"]["content"]["readiness"]["source_only_gaps"]
    sessions_actor = FirestoreTemporarySessions(
        firestore_client, issuance_check=lambda: True).resolve(client.cookies["__session"])
    graph = FirestoreRepository(firestore_client).get_record(
        Actor("temporary", sessions_actor.owner_id), workspace, "artifacts",
        confirmed.json()["graph_artifact_id"])
    assert graph["kind"] == "compiled_graph"
    assert graph["sha256"] == snapshot["graph_sha256"]
    reviewer = app_for(firestore_client, objects)
    reviewer.cookies.set("__session", client.cookies["__session"])
    reconnected = reviewer.get(f"{base}/reviews/main")
    assert reconnected.status_code == 200
    assert reconnected.json()["content_hash"] == confirmed.json()["review"]["content_hash"]
    sealed = reviewer.post(f"{base}/reviews/main/seal", headers={
        **headers, "If-Match": "2", "Idempotency-Key": f"{label}-seal"})
    assert sealed.status_code == 200, sealed.text
    assert sealed.json()["sealed"] is True
    assert sealed.json()["content"]["readiness"]["ready_to_run"] is False
    assert reviewer.get(f"{base}/artifacts/{artifact['artifact_id']}/download").content == source
    stranger = app_for(firestore_client, objects)
    stranger.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert stranger.get(f"{base}/reviews/main").status_code == 404
    assert stranger.get(f"{base}/artifacts/{artifact['artifact_id']}/coverage").status_code == 404
