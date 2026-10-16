"""Temporary expiry denies immediately and sweep tombstones later."""

from datetime import UTC, datetime, timedelta

import pytest
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.deletion import FirestoreDeletion
from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.sessions import SessionUnavailable
from services.worker.leases import FirestoreLeases, StaleFence


def test_expiry_denies_before_sweep_and_fences_late_work(firestore_client: Client) -> None:
    now = datetime.now(UTC)
    clock = [now]
    sessions = FirestoreTemporarySessions(firestore_client, clock=lambda: clock[0],
                                          issuance_check=lambda: True)
    handle, view, _ = sessions.issue()
    actor = Actor("temporary", view.owner_id)
    job_id = FirestoreJobs(firestore_client, clock=lambda: clock[0]).submit(
        actor, view.workspace_id, route="reports", idempotency_key="running",
        stage="report", input_hash="e" * 64,
        estimated_units=1, required_seconds=100)["job_id"]
    leases = FirestoreLeases(firestore_client, clock=lambda: clock[0])
    fence = leases.claim(view.workspace_id, job_id)
    assert fence == 1
    clock[0] = now + timedelta(hours=3)
    with pytest.raises(SessionUnavailable):
        sessions.resolve(handle)
    with pytest.raises(SessionUnavailable):
        sessions.renew(handle)
    deletion = FirestoreDeletion(firestore_client, clock=lambda: clock[0])
    assert view.workspace_id in deletion.expire_page()
    assert deletion.expire_page() == []
    with pytest.raises((StaleFence, AccessDenied)):
        leases.publish(view.workspace_id, job_id, fence,
                       artifact_key="attempt/late", result_hash="f" * 64)
    with pytest.raises(AccessDenied):
        FirestoreRepository(firestore_client).put_artifact(actor, view.workspace_id,
            "late-export", sha256="f" * 64,
            object_key=f"workspaces/{view.workspace_id}/reports/late.pdf",
            generation=1, byte_count=10, kind="report", expected_revision=0)
    assert firestore_client.collection("workspaces").document(
        view.workspace_id).get().to_dict()["tombstoned_at"] is not None


def test_explicit_end_cancels_claimed_guest_job(firestore_client: Client) -> None:
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    handle, view, _ = sessions.issue()
    actor = Actor("temporary", view.owner_id)
    job_id = FirestoreJobs(firestore_client).submit(actor, view.workspace_id,
        route="reports", idempotency_key="end-running", stage="report",
        input_hash="a" * 64, estimated_units=1,
        required_seconds=100)["job_id"]
    leases = FirestoreLeases(firestore_client)
    fence = leases.claim(view.workspace_id, job_id)
    assert fence == 1
    assert sessions.revoke(handle) is None
    with pytest.raises(SessionUnavailable):
        sessions.resolve(handle)
    with pytest.raises((StaleFence, AccessDenied)):
        leases.publish(view.workspace_id, job_id, fence,
                       artifact_key="attempt/late", result_hash="b" * 64)
    root = firestore_client.collection("workspaces").document(view.workspace_id)
    assert root.collection("jobs").document(job_id).get().to_dict()["status"] == "cancelled"
