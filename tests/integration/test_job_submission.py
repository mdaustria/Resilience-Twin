"""Firestore emulator coverage for atomic job acceptance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from time import perf_counter
from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from google.cloud.firestore_v1 import Client

import packages.adapters.persistence.jobs as jobs_module
from packages.adapters.persistence.firestore import Actor, Conflict, FirestoreRepository
from packages.adapters.persistence.jobs import (
    FirestoreJobs,
    LifetimeTooShort,
    UsageExceeded,
)
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.persistence.usage import BudgetExceeded, FirestoreUsage
from packages.application.jobs import JobSubmission
from packages.application.usage import UsagePolicy
from services.api.documents import session_owner_resolver
from services.api.main import create_app


def test_atomic_idempotent_reservation_and_failure(firestore_client: Client) -> None:
    repository = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "job-owner")
    repository.create_owner_workspace(
        actor, "job-workspace", expires_at=datetime.now(UTC) + timedelta(hours=1))
    jobs = FirestoreJobs(firestore_client, workspace_limit=8)
    args = {"route": "runs", "idempotency_key": "once", "stage": "simulation",
            "input_hash": "a" * 64, "estimated_units": 5, "required_seconds": 120}
    first = jobs.submit(actor, "job-workspace", **args)
    assert jobs.submit(actor, "job-workspace", **args) == first
    root = firestore_client.collection("workspaces").document("job-workspace")
    assert len(list(root.collection("jobs").stream())) == 1
    assert len(list(root.collection("usage_reservations").stream())) == 1
    assert len(list(root.collection("outbox").stream())) == 1
    assert root.collection("usage").document("total").get().to_dict()["reserved_units"] == 5
    with pytest.raises(Conflict):
        jobs.submit(actor, "job-workspace", **{**args, "input_hash": "b" * 64})
    with pytest.raises(UsageExceeded):
        jobs.submit(actor, "job-workspace", **{**args, "idempotency_key": "too-much"})
    assert len(list(root.collection("job_commands").stream())) == 1
    assert len(list(root.collection("jobs").stream())) == 1
    assert len(list(root.collection("usage_reservations").stream())) == 1
    assert len(list(root.collection("outbox").stream())) == 1
    assert root.collection("usage").document("total").get().to_dict()["reserved_units"] == 5
    original = jobs_module._bounded

    def abort_after_queued_writes(record: dict[str, Any]) -> dict[str, Any]:
        if record.get("status") == "pending":
            raise RuntimeError("abort after buffered writes")
        return original(record)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(jobs_module, "_bounded", abort_after_queued_writes)
        with pytest.raises(RuntimeError, match="buffered"):
            jobs.submit(actor, "job-workspace", **{**args, "idempotency_key": "abort",
                                                    "estimated_units": 3})
    assert len(list(root.collection("job_commands").stream())) == 1
    assert len(list(root.collection("jobs").stream())) == 1
    assert len(list(root.collection("usage_reservations").stream())) == 1
    assert len(list(root.collection("outbox").stream())) == 1
    assert root.collection("usage").document("total").get().to_dict()["reserved_units"] == 5


def test_temporary_lifetime_and_http_202(firestore_client: Client) -> None:
    now = datetime.now(UTC)
    actor = Actor("temporary", "short-guest")
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, "short-workspace", expires_at=now + timedelta(seconds=100))
    jobs = FirestoreJobs(firestore_client, clock=lambda: now)
    with pytest.raises(LifetimeTooShort):
        jobs.submit(actor, "short-workspace", route="runs", idempotency_key="short",
                    stage="simulation", input_hash="a" * 64,
                    estimated_units=1, required_seconds=90)
    root = firestore_client.collection("workspaces").document("short-workspace")
    assert list(root.collection("outbox").stream()) == []

    temporary = FirestoreTemporarySessions(firestore_client, clock=lambda: now,
                                           issuance_check=lambda: True)
    origin = "https://resilience.example"
    key = b"test-only-secret-32-bytes-at-least!!"
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_owner_for=session_owner_resolver(temporary, FirestoreRepository(firestore_client)),
        job_submission=JobSubmission(jobs), session_origin=origin, session_csrf_key=key)
    client = TestClient(app, base_url=origin)
    guest = client.post("/api/v1/temporary-sessions", headers={"Origin": origin})
    assert guest.status_code == 201
    csrf = guest.json()["csrf_token"]
    workspace = guest.json()["workspace_id"]
    url = f"/api/v1/workspaces/{workspace}/jobs"
    headers = {"Origin": origin, "X-CSRF-Token": csrf, "Idempotency-Key": "http-job"}
    body = {"stage": "simulation", "input_hash": "c" * 64}
    accepted = client.post(url, json=body, headers=headers)
    assert accepted.status_code == 202, accepted.text
    assert client.post(url, json=body, headers=headers).json() == accepted.json()
    assert accepted.headers["cache-control"] == "private, no-store"
    live_owner = firestore_client.document(f"workspaces/{workspace}").get().to_dict()["owner_id"]
    near_expiry = FirestoreJobs(firestore_client,
        clock=lambda: now + timedelta(minutes=118))
    with pytest.raises(LifetimeTooShort):
        near_expiry.submit(Actor("temporary", live_owner), workspace, route="runs",
            idempotency_key="late-real-guest", stage="simulation", input_hash="d" * 64,
            estimated_units=1, required_seconds=180)
    assert len(list(firestore_client.collection("workspaces").document(workspace)
                    .collection("outbox").stream())) == 1


def test_contended_reservations_never_exceed_hard_cap(firestore_client: Client) -> None:
    # Keep this budget day separate from other emulator checks in a combined run.
    now = datetime.now(UTC) + timedelta(days=7)
    sessions = FirestoreTemporarySessions(firestore_client, clock=lambda: now,
                                          issuance_check=lambda: True)
    _handle, guest, _fresh = sessions.issue()
    actor = Actor("temporary", guest.owner_id)
    workspace_id = guest.workspace_id
    network_key = "a" * 64
    policy = UsagePolicy(guest_daily_units=6,
        network_daily_units=6, global_daily_units=6, global_active_jobs=2,
        challenge_after_network_units=6, network_daily_sessions=10,
        global_daily_sessions=10)
    jobs = FirestoreJobs(firestore_client, clock=lambda: now, workspace_limit=6,
                         budgets=FirestoreUsage(firestore_client, policy))
    start = Barrier(4)

    def submit(index: int) -> str:
        start.wait(timeout=10)
        try:
            jobs.submit(actor, workspace_id, route="runs",
                        idempotency_key=f"contended-{index}", stage="simulation",
                        input_hash=f"{index:064x}", estimated_units=3,
                        required_seconds=120, network_key=network_key)
            return "accepted"
        except (UsageExceeded, BudgetExceeded):
            return "limit"
        except Aborted:
            return "retry_exhausted"
        except ValueError as error:
            if "Failed to commit transaction in 5 attempts" not in str(error):
                raise
            return "retry_exhausted"

    began = perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    elapsed = perf_counter() - began
    accepted = results.count("accepted")
    if accepted == 0:
        assert "retry_exhausted" in results, results
        results.append(submit_after_contention(jobs, actor, workspace_id, network_key))
        accepted = results.count("accepted")
    assert 1 <= accepted <= 2, results
    root = firestore_client.collection("workspaces").document(workspace_id)
    tally = root.collection("usage").document("total").get().to_dict()
    assert tally is not None and tally["reserved_units"] == accepted * 3
    assert len(list(root.collection("job_commands").stream())) == accepted
    assert len(list(root.collection("jobs").stream())) == accepted
    assert len(list(root.collection("outbox").stream())) == accepted
    assert len(list(root.collection("usage_reservations").stream())) == accepted
    buckets = firestore_client.collection("usage_days").document(now.strftime("%Y%m%d")).collection(
        "buckets")
    for name in ("global", f"owner-temporary-{actor.owner_id}", f"network-{network_key}"):
        row = buckets.document(name).get().to_dict()
        assert row is not None and row["units"] == accepted * 3 <= 6
    assert buckets.document("global").get().to_dict()["active_jobs"] == accepted <= 2
    print(f"reservation contention: {results}; {elapsed:.2f}s")


def submit_after_contention(jobs: FirestoreJobs, actor: Actor, workspace_id: str,
                            network_key: str) -> str:
    jobs.submit(actor, workspace_id, route="runs", idempotency_key="after-contention",
                stage="simulation", input_hash="f" * 64, estimated_units=3,
                required_seconds=120, network_key=network_key)
    return "accepted"
