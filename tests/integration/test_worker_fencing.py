"""Lease fencing and signed worker identity checks."""

import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.transport.requests import Request as GoogleRequest
from google.cloud.firestore_v1 import Client
from google.oauth2 import service_account

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.jobs import FirestoreJobs
from services.worker.dispatch import worker_router
from services.worker.leases import (
    FirestoreLeases,
    LeaseBusy,
    StaleFence,
    verify_worker_token,
)


def test_fenced_publication_and_completed_duplicate(firestore_client: Client) -> None:
    actor = Actor("temporary", "fence-owner")
    workspace_id = "fence-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    now = datetime.now(UTC)
    job_id = FirestoreJobs(firestore_client).submit(
        actor, workspace_id, route="runs", idempotency_key="one", stage="simulation",
        input_hash="b" * 64, estimated_units=1, required_seconds=100)["job_id"]
    first = FirestoreLeases(firestore_client, clock=lambda: now, lease_seconds=10)
    assert first.claim(workspace_id, job_id) == 1
    with pytest.raises(LeaseBusy):
        first.claim(workspace_id, job_id)
    second = FirestoreLeases(firestore_client,
                             clock=lambda: now + timedelta(seconds=11))
    assert second.claim(workspace_id, job_id) == 2
    with pytest.raises(StaleFence):
        first.publish(workspace_id, job_id, 1, artifact_key="attempt/old", result_hash="x")
    second.publish(workspace_id, job_id, 2, artifact_key="attempt/new", result_hash="y")
    assert second.claim(workspace_id, job_id) is None
    run = firestore_client.collection("workspaces").document(workspace_id).collection(
        "runs").document(job_id).get().to_dict()
    assert run["artifact_key"] == "attempt/new"


def test_task_headers_do_not_authenticate_worker() -> None:
    audience = "https://worker.example/stage"
    email = "worker@example.iam.gserviceaccount.com"
    claims = {"aud": audience, "email": email, "email_verified": True,
              "iss": "https://accounts.google.com"}
    with pytest.raises(AccessDenied):
        verify_worker_token(None, audience=audience, service_account_email=email,
                            verifier=lambda _token, _audience: claims)
    with pytest.raises(AccessDenied):
        verify_worker_token("Bearer forged", audience=audience,
                            service_account_email=email,
                            verifier=lambda _token, _audience: {**claims, "email": "attacker@example.com"})
    verify_worker_token("Bearer signed", audience=audience,
                        service_account_email=email,
                        verifier=lambda token, _audience: claims if token == "signed" else {})
    app = FastAPI()
    app.include_router(worker_router(audience=audience, service_account_email=email,
                                     process=lambda _workspace, _job: None))
    response = TestClient(app).post("/internal/tasks/workspace/job", headers={
        "X-CloudTasks-TaskName": "forged", "X-CloudTasks-QueueName": "simulation"})
    assert response.status_code == 401


def test_signed_oidc_reaches_local_http_worker(firestore_client: Client) -> None:
    """Exercise the real HTTP entry with Google-issued identity, not task headers."""
    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path or not os.path.isfile(credential_path):
        pytest.fail("GOOGLE_APPLICATION_CREDENTIALS required for signed worker smoke")
    actor = Actor("temporary", "http-worker-owner")
    workspace_id = "http-worker-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    job_id = FirestoreJobs(firestore_client).submit(
        actor, workspace_id, route="runs", idempotency_key="signed-http",
        stage="simulation", input_hash="c" * 64, estimated_units=1,
        required_seconds=100)["job_id"]
    audience = "https://resilience-twin-worker.example/internal"
    identity = service_account.IDTokenCredentials.from_service_account_file(
        credential_path, target_audience=audience)
    identity.refresh(GoogleRequest())
    email = identity.service_account_email
    delivered: list[str] = []
    leases = FirestoreLeases(firestore_client)

    def process(received_workspace: str, received_job: str) -> None:
        assert (received_workspace, received_job) == (workspace_id, job_id)
        fence = leases.claim(received_workspace, received_job)
        if fence is not None:
            leases.publish(received_workspace, received_job, fence,
                           artifact_key="attempt/signed-http", result_hash="d" * 64)
        delivered.append(received_job)

    app = FastAPI()
    app.include_router(worker_router(audience=audience,
                                     service_account_email=email, process=process))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "local worker did not start"
        url = f"http://127.0.0.1:{port}/internal/tasks/{workspace_id}/{job_id}"
        unsigned = Request(url, data=b"{}", headers={"X-CloudTasks-TaskName": "forged"})
        with pytest.raises(HTTPError) as denied:
            urlopen(unsigned, timeout=10)
        assert denied.value.code == 401
        wrong_audience = service_account.IDTokenCredentials.from_service_account_file(
            credential_path, target_audience="https://resilience-twin-worker.example/wrong")
        wrong_audience.refresh(GoogleRequest())
        mismatched = Request(url, data=b"{}", headers={
            "Authorization": f"Bearer {wrong_audience.token}"})
        with pytest.raises(HTTPError) as denied_audience:
            urlopen(mismatched, timeout=10)
        assert denied_audience.value.code == 401
        signed = Request(url, data=b"{}", headers={
            "Authorization": f"Bearer {identity.token}",
            "Content-Type": "application/json"})
        for _ in range(2):
            with urlopen(signed, timeout=15) as response:
                assert response.status == 200
        assert delivered == [job_id, job_id]
        root = firestore_client.collection("workspaces").document(workspace_id)
        assert root.collection("jobs").document(job_id).get().to_dict()["status"] == "complete"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "local worker did not stop"
