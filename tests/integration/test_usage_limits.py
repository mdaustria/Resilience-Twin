"""Emulator-backed global/network budgets and retry accounting."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.firestore import (
    Actor,
    FirestoreRepository,
    InvalidRecord,
)
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.persistence.usage import (
    BudgetExceeded,
    ChallengeRequired,
    FirestoreUsage,
)
from packages.adapters.storage import MemoryObjectStore
from packages.application.documents import PrivateDocuments
from packages.application.jobs import JobSubmission
from packages.application.sessions import IssuanceDenied
from packages.application.usage import UsagePolicy, network_bucket
from services.api.documents import session_owner_resolver
from services.api.limits import load_usage_policy
from services.api.main import create_app
from services.worker.usage import settle_provider_usage


def policy() -> UsagePolicy:
    return UsagePolicy(guest_daily_units=10,
        network_daily_units=3, global_daily_units=3, global_active_jobs=2,
        challenge_after_network_units=3, network_daily_sessions=1,
        global_daily_sessions=2)


def test_published_limits_fit_full_file_and_use_server_stage_costs() -> None:
    published = load_usage_policy(Path("release/limits.json"))
    assert published.guest_daily_units >= 27 + 2 + 3 + 1
    assert published.network_daily_units >= 2 * (27 + 2 + 3 + 1)
    assert published.global_daily_units >= published.network_daily_units


def test_cookie_reset_and_forwarding_headers_cannot_change_network_budget(
    firestore_client: Client,
) -> None:
    now = datetime.now(UTC) + timedelta(days=2)
    limits = UsagePolicy(guest_daily_units=10, network_daily_units=4,
        global_daily_units=10, global_active_jobs=3,
        challenge_after_network_units=4, network_daily_sessions=2,
        global_daily_sessions=3)
    usage = FirestoreUsage(firestore_client, limits)
    sessions = FirestoreTemporarySessions(firestore_client, clock=lambda: now,
        issuance_check=lambda: True, issuance_budgets=usage)
    secret = b"test-only-network-bucket-secret-32bytes"
    origin = "https://resilience.example"
    app = create_app(local_fixture_mode=False, temporary_sessions=sessions,
        private_owner_for=session_owner_resolver(
            sessions, FirestoreRepository(firestore_client)),
        job_submission=JobSubmission(FirestoreJobs(firestore_client,
            clock=lambda: now, budgets=usage)), usage_policy=limits,
        session_origin=origin, session_csrf_key=secret,
        session_network_secret=secret, job_network_secret=secret)
    client = TestClient(app, base_url=origin, client=("198.51.100.44", 50000))
    forged = {"Origin": origin, "X-Forwarded-For": "203.0.113.9",
              "Forwarded": "for=203.0.113.10"}
    first = client.post("/api/v1/temporary-sessions", headers=forged)
    assert first.status_code == 201
    first_body = first.json()
    job_url = f"/api/v1/workspaces/{first_body['workspace_id']}/jobs"
    headers = {**forged, "X-CSRF-Token": first_body["csrf_token"],
               "Idempotency-Key": "one"}
    accepted = client.post(job_url, json={"stage": "simulation",
        "input_hash": "f" * 64}, headers=headers)
    assert accepted.status_code == 202, accepted.text
    assert client.post(job_url, json={"stage": "simulation",
        "input_hash": "f" * 64, "estimated_units": 0}, headers={
        **headers, "Idempotency-Key": "client-cost"}).status_code == 422
    client.cookies.clear()
    second = client.post("/api/v1/temporary-sessions", headers={
        **forged, "X-Forwarded-For": "192.0.2.77"})
    assert second.status_code == 201
    second_body = second.json()
    denied = client.post(f"/api/v1/workspaces/{second_body['workspace_id']}/jobs",
        json={"stage": "simulation", "input_hash": "e" * 64}, headers={
        **forged, "X-CSRF-Token": second_body["csrf_token"],
        "Idempotency-Key": "two", "X-Forwarded-For": "192.0.2.88"})
    assert denied.status_code == 429
    client.cookies.clear()
    assert client.post("/api/v1/temporary-sessions", headers={
        **forged, "X-Forwarded-For": "192.0.2.99"}).status_code == 429
    day = now.strftime("%Y%m%d")
    network = network_bucket("198.51.100.44", secret)
    bucket = firestore_client.collection("usage_days").document(day).collection(
        "buckets").document(f"network-{network}").get().to_dict()
    assert bucket["units"] == 3 and bucket["issued_sessions"] == 2


def test_rotated_guest_and_concurrent_jobs_share_hard_caps(firestore_client: Client) -> None:
    now = datetime.now(UTC)
    usage = FirestoreUsage(firestore_client, policy())
    network = network_bucket("203.0.113.42", b"engineering-only-32-byte-secret-value")
    sessions = FirestoreTemporarySessions(firestore_client, clock=lambda: now,
        issuance_check=lambda: True, issuance_budgets=usage)
    handle, first, _ = sessions.issue(network_key=network)
    assert sessions.issue(handle, network_key=network)[1].workspace_id == first.workspace_id
    with pytest.raises(IssuanceDenied):
        sessions.issue(network_key=network)
    # Distinct credentials already issued before a cap was configured still
    # share the same network and global compute bucket.
    actor_a = Actor("temporary", first.owner_id)
    actor_b = Actor("temporary", "rotated-guest")
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor_b, "rotated-workspace", expires_at=first.expires_at)
    jobs = FirestoreJobs(firestore_client, clock=lambda: now, budgets=usage)

    def submit(actor: Actor, workspace: str, key: str) -> str:
        try:
            jobs.submit(actor, workspace, route="runs", idempotency_key=key,
                stage="simulation", input_hash="a" * 64, estimated_units=2,
                required_seconds=100, network_key=network)
            return "accepted"
        except BudgetExceeded:
            return "limit"
        except ValueError as error:
            if "Failed to commit transaction in 5 attempts" not in str(error):
                raise
            # Emulator lock contention may exhaust retries; the ledger below
            # still must contain only the accepted reservation.
            return "retry_exhausted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: submit(*args), [
            (actor_a, first.workspace_id, "one"),
            (actor_b, "rotated-workspace", "two")]))
    if results.count("accepted") == 0:
        assert "retry_exhausted" in results, results
        # Under emulator lock contention both callbacks can exhaust retries;
        # prove a subsequent single submission still reserves exactly once.
        results.append(submit(actor_a, first.workspace_id, "after-contention"))
    assert results.count("accepted") == 1, results
    day = now.strftime("%Y%m%d")
    root = firestore_client.collection("usage_days").document(day).collection("buckets")
    assert root.document("global").get().to_dict()["units"] == 2
    assert root.document(f"network-{network}").get().to_dict()["units"] == 2
    assert root.document("global").get().to_dict()["active_jobs"] == 1


def test_provider_retry_settlement_and_download_at_limit(firestore_client: Client) -> None:
    now = datetime.now(UTC) + timedelta(days=1)
    actor = Actor("temporary", "usage-download-owner")
    workspace = "usage-download-workspace"
    repository = FirestoreRepository(firestore_client)
    repository.create_owner_workspace(
        actor, workspace, expires_at=now + timedelta(days=1))
    objects = MemoryObjectStore()
    stored = objects.write_once(f"workspaces/{workspace}/reports/ready.pdf", b"saved result")
    repository.put_artifact(actor, workspace, "ready-report", sha256=stored.sha256,
        object_key=stored.key, generation=stored.generation,
        byte_count=stored.byte_count, kind="report", expected_revision=0)
    usage = FirestoreUsage(firestore_client, policy())
    network = network_bucket("198.51.100.10", b"engineering-only-32-byte-secret-value")
    jobs = FirestoreJobs(firestore_client, clock=lambda: now, budgets=usage)
    job_id = jobs.submit(actor, workspace, route="reports", idempotency_key="one",
        stage="report", input_hash="c" * 64, estimated_units=3,
        required_seconds=100, network_key=network)["job_id"]
    with pytest.raises(BudgetExceeded):
        jobs.submit(actor, workspace, route="reports", idempotency_key="two",
            stage="report", input_hash="c" * 64, estimated_units=1,
            required_seconds=100, network_key=network)
    first = settle_provider_usage(usage, workspace, job_id,
        provider_event_id="provider-attempt-1", units=1)
    repeated = settle_provider_usage(usage, workspace, job_id,
        provider_event_id="provider-attempt-1", units=1)
    assert repeated["actual_units"] == first["actual_units"] == 1
    with pytest.raises(InvalidRecord):
        settle_provider_usage(usage, workspace, job_id,
            provider_event_id="provider-attempt-1", units=2)
    final = settle_provider_usage(usage, workspace, job_id,
        provider_event_id="provider-attempt-2", units=1, final=True)
    assert final["actual_units"] == 2
    day = now.strftime("%Y%m%d")
    global_row = firestore_client.collection("usage_days").document(
        day).collection("buckets").document("global").get().to_dict()
    assert global_row["units"] == 2 and global_row["active_jobs"] == 0
    workspace_usage = firestore_client.collection("workspaces").document(
        workspace).collection("usage").document("total").get().to_dict()
    assert workspace_usage["reserved_units"] == 2
    documents = PrivateDocuments(repository, objects, scanner=None, validator=None,
        secret=b"engineering-only-32-byte-secret-value")  # type: ignore[arg-type]
    assert b"".join(documents.stream(lambda: actor, workspace, "ready-report")) == b"saved result"


def test_failed_challenge_closes_new_paid_work(firestore_client: Client) -> None:
    now = datetime.now(UTC) + timedelta(days=3)
    actor = Actor("temporary", "challenge-owner")
    workspace = "challenge-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace, expires_at=now + timedelta(hours=2))
    limits = UsagePolicy(guest_daily_units=5, network_daily_units=5,
        global_daily_units=10, global_active_jobs=2,
        challenge_after_network_units=1, network_daily_sessions=2,
        global_daily_sessions=4)
    jobs = FirestoreJobs(firestore_client, clock=lambda: now,
                         budgets=FirestoreUsage(firestore_client, limits))
    network = network_bucket("203.0.113.150", b"engineering-only-32-byte-secret-value")
    jobs.submit(actor, workspace, route="reports", idempotency_key="first",
        stage="report", input_hash="a" * 64, estimated_units=1,
        required_seconds=100, network_key=network)
    with pytest.raises(ChallengeRequired):
        jobs.submit(actor, workspace, route="reports", idempotency_key="second",
            stage="report", input_hash="b" * 64, estimated_units=1,
            required_seconds=100, network_key=network)
    root = firestore_client.collection("workspaces").document(workspace)
    assert len(list(root.collection("jobs").stream())) == 1
    assert len(list(root.collection("outbox").stream())) == 1
