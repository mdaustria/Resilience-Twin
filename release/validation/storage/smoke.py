"""Authorized synthetic Storage/Firestore smoke for revised Task 4.4.

Run from the repository root with RT_STORAGE_SMOKE_APPROVED=1 and the already
authorized nonproduction service-account credential. Only UUID-named synthetic
sessions and their objects are created; cleanup runs even when an assertion fails.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import firestore, storage  # type: ignore[attr-defined]
from pypdf import PdfWriter

from packages.adapters.documents.pdf import PypdfValidator
from packages.adapters.persistence.firestore import AccessDenied, FirestoreRepository
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import FirebaseObjectStore
from packages.application.documents import (
    ObjectConflict,
    ObjectMissing,
    PrivateDocuments,
)
from services.api.documents import session_owner_resolver

PROJECT = "ai-projects-250716"
DATABASE = "resillience-twin"
BUCKET = "ai-projects-250716-resilliencetwin"
EVIDENCE = Path(__file__).with_name("cloud-smoke.json")


class SyntheticScanner:
    def scan(self, path: Path) -> None:
        if not path.read_bytes().startswith(b"%PDF-"):
            raise AssertionError("Synthetic source is not a PDF")


def _source() -> bytes:
    pdf = PdfWriter()
    pdf.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    pdf.write(output)
    return output.getvalue()


def _anonymous_status(url: str) -> int:
    try:
        with urlopen(url, timeout=15) as response:
            return int(response.status)
    except HTTPError as error:
        return error.code


def main() -> None:
    if os.getenv("RT_STORAGE_SMOKE_APPROVED") != "1":
        raise RuntimeError("Set RT_STORAGE_SMOKE_APPROVED=1 for the authorized test bucket")
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("Service-account credential path is required")

    bucket = storage.Client(project=PROJECT).get_bucket(BUCKET)
    objects = FirebaseObjectStore(bucket)
    client = firestore.Client(project=PROJECT, database=DATABASE)
    sessions = FirestoreTemporarySessions(client, issuance_check=lambda: True)
    repository = FirestoreRepository(client)
    owner_for = session_owner_resolver(sessions, repository)
    documents = PrivateDocuments(repository, objects, SyntheticScanner(),
                                 PypdfValidator(), secret=b"synthetic-storage-smoke-secret-32-bytes!!")
    created: list[tuple[str, str, str]] = []
    artifact_id: str | None = None
    final_generation: int | None = None
    stage_generation: int | None = None
    source = _source()
    result: dict[str, object] = {}
    cleanup_ok = False

    try:
        for _ in range(2):
            handle, view, fresh = sessions.issue()
            assert fresh
            created.append((handle, view.owner_id, view.workspace_id))
        first_handle, _, workspace_id = created[0]
        second_handle = created[1][0]
        actor, expires_at = owner_for(first_handle, workspace_id)
        assert expires_at is not None

        grant = documents.begin(actor, workspace_id,
            sha256=hashlib.sha256(source).hexdigest(), byte_count=len(source),
            temporary_expires_at=expires_at)
        assert grant.expires_at <= expires_at
        stage_key = f"workspaces/{workspace_id}/quarantine/{grant.upload_id}.pdf"
        final_key = f"workspaces/{workspace_id}/documents/{grant.upload_id}.pdf"
        staged = documents.upload(actor, workspace_id, grant.token, source)
        stage_generation = staged.generation
        artifact_id, stored, pages = documents.finalize(actor, workspace_id, grant.token,
            quarantine_generation=staged.generation, expected_revision=0)
        final_generation = stored.generation
        assert pages == 1 and stored.sha256 == hashlib.sha256(source).hexdigest()
        assert objects.read_all(stored.key, stored.generation) == source
        assert objects.read_range(stored.key, stored.generation, 0, 16) == source[:16]
        assert b"".join(documents.stream(
            lambda: owner_for(first_handle, workspace_id)[0], workspace_id, artifact_id,
            chunk_size=128)) == source
        try:
            owner_for(second_handle, workspace_id)
        except AccessDenied:
            wrong_session_denied = True
        else:
            wrong_session_denied = False
        assert wrong_session_denied
        try:
            objects.write_once(final_key, source)
        except ObjectConflict:
            overwrite_denied = True
        else:
            overwrite_denied = False
        assert overwrite_denied
        try:
            objects.read_all(final_key, stored.generation + 1)
        except ObjectMissing:
            wrong_generation_denied = True
        else:
            wrong_generation_denied = False
        assert wrong_generation_denied

        encoded = quote(f"resilience-twin/{final_key}", safe="")
        firebase_status = _anonymous_status(
            f"https://firebasestorage.googleapis.com/v0/b/{BUCKET}/o/{encoded}?alt=media")
        gcs_status = _anonymous_status(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{encoded}?alt=media")
        assert firebase_status in (401, 403), firebase_status
        assert gcs_status in (401, 403), gcs_status

        result = {
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "project": PROJECT, "firestore_database": DATABASE,
            "bucket": BUCKET, "location": bucket.location,
            "versioning_enabled": bucket.versioning_enabled,
            "retention_period_seconds": bucket.retention_period,
            "soft_delete_policy": bucket.soft_delete_policy,
            "iam_configuration": bucket.iam_configuration,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "source_bytes": len(source), "physical_pages": pages,
            "guest_owner_denial": wrong_session_denied,
            "create_precondition_denial": overwrite_denied,
            "generation_precondition_denial": wrong_generation_denied,
            "firebase_anonymous_http_status": firebase_status,
            "gcs_anonymous_http_status": gcs_status,
        }
    finally:
        cleanup_errors: list[str] = []

        def cleanup(label: str, action: Callable[[], object]) -> None:
            try:
                action()
            except GoogleAPICallError as error:
                cleanup_errors.append(f"{label}: {type(error).__name__}")

        if created:
            workspace_id = created[0][2]
            if artifact_id is not None:
                cleanup("artifact", client.document(
                    f"workspaces/{workspace_id}/artifacts/{artifact_id}").delete)
            if final_generation is not None:
                cleanup("final object", partial(objects.delete, final_key, final_generation))
            if stage_generation is not None:
                cleanup("quarantine object", partial(objects.delete, stage_key, stage_generation))
        for handle, owner_id, workspace_id in created:
            cleanup("session", client.document(
                f"browser_sessions/{hashlib.sha256(handle.encode()).hexdigest()}").delete)
            cleanup("owner", client.document(f"owners/temporary:{owner_id}").delete)
            cleanup("workspace", client.document(f"workspaces/{workspace_id}").delete)
        cleanup_ok = not cleanup_errors and all(
            not client.document(f"workspaces/{workspace_id}").get().exists
            and not client.document(f"owners/temporary:{owner_id}").get().exists
            and not client.document(
                f"browser_sessions/{hashlib.sha256(handle.encode()).hexdigest()}").get().exists
            and objects.list_workspace_versions(workspace_id) == []
            for handle, owner_id, workspace_id in created
        )
    if not cleanup_ok:
        raise AssertionError(f"Synthetic cleanup incomplete: {cleanup_errors}")
    result["cleanup_verified"] = True
    EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Task 4.4 cloud smoke passed; evidence: {EVIDENCE}")


if __name__ == "__main__":
    main()
