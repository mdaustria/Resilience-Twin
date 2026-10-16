"""Independent suite members and visible partial cancellation."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.firestore import Actor, Conflict, FirestoreRepository
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.runs import FirestoreRuns
from services.api.main import create_app
from services.api.sessions import COOKIE
from services.worker.leases import FirestoreLeases


def test_suite_aggregates_failed_and_cancelled_members(firestore_client: Client) -> None:
    actor = Actor("temporary", "suite-owner")
    workspace_id = "suite-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    jobs = FirestoreJobs(firestore_client)
    ids = [jobs.submit(actor, workspace_id, route="suite/members",
                       idempotency_key=f"member-{number}", stage="simulation",
                       input_hash=f"{number + 1:064x}", estimated_units=1,
                       required_seconds=100)["job_id"] for number in range(3)]
    runs = FirestoreRuns(firestore_client)
    assert runs.create_suite_plan(actor, workspace_id, "suite-one", ids)[
        "member_job_ids"] == ids
    assert runs.create_suite_plan(actor, workspace_id, "suite-one", ids)[
        "member_job_ids"] == ids
    with pytest.raises(Conflict):
        runs.create_suite_plan(actor, workspace_id, "suite-one", ids[:2])
    leases = FirestoreLeases(firestore_client)
    fence = leases.claim(workspace_id, ids[0])
    assert fence is not None
    leases.publish(workspace_id, ids[0], fence,
                   artifact_key="attempt/complete", result_hash="a" * 64)
    root = firestore_client.collection("workspaces").document(workspace_id)
    root.collection("jobs").document(ids[1]).update({"status": "failed", "error": "invalid_input"})
    assert runs.cancel(actor, workspace_id, ids[2])["status"] == "cancelled"
    status = runs.read_suite(actor, workspace_id, "suite-one")
    assert (status["planned"], status["completed"], status["failed"],
            status["cancelled"], status["partial"]) == (3, 1, 1, 1, True)
    assert [member["status"] for member in status["members"]] == [
        "complete", "failed", "cancelled"]
    assert root.collection("runs").document(ids[2]).get().to_dict()["status"] == "partial"
    with pytest.raises(Conflict):
        runs.retry_failed(actor, workspace_id, ids[2], idempotency_key="no-cancel-retry")
    assert runs.acknowledge(actor, workspace_id, ids[2])["acknowledged"] is True
    assert runs.acknowledge(actor, workspace_id, ids[2])["acknowledged"] is True
    retry = runs.retry_failed(actor, workspace_id, ids[1], idempotency_key="try-again")
    assert retry == {"job_id": ids[1], "attempt": 2, "status": "queued"}
    assert runs.retry_failed(actor, workspace_id, ids[1],
                             idempotency_key="try-again") == retry
    assert root.collection("outbox").document(f"{ids[1]}-000002").get().exists
    assert root.collection("jobs").document(ids[1]).collection(
        "attempts").document("000002").get().exists
    with pytest.raises(Conflict):
        runs.retry_failed(actor, workspace_id, ids[1], idempotency_key="different")

    csrf_key = b"test-only-suite-csrf-key-32-bytes-long"
    handle = "synthetic-suite-handle"
    client = TestClient(create_app(local_fixture_mode=False, durable_runs=runs,
        private_owner_for=lambda _handle, _workspace: (actor, None),
        session_origin="https://app.example", session_csrf_key=csrf_key))
    headers = {"Origin": "https://app.example", "X-CSRF-Token": hmac.new(
        csrf_key, handle.encode(), hashlib.sha256).hexdigest(),
        "Cookie": f"{COOKIE}={handle}"}
    base = f"/api/v1/workspaces/{workspace_id}/runs"
    assert client.get(f"{base}/suites/suite-one", headers=headers).json()[
        "planned"] == 3
    assert client.put(f"{base}/suites/suite-one", json={"job_ids": ids},
                      headers=headers).status_code == 200
    assert client.post(f"{base}/{ids[2]}/acknowledge", headers=headers).json()[
        "acknowledged"] is True
    assert client.post(f"{base}/{ids[1]}/retry", headers={
        **headers, "Idempotency-Key": "try-again"}).json() == retry
    assert client.post(f"{base}/{ids[1]}/retry", headers={
        **headers, "Idempotency-Key": "different"}).status_code == 409
