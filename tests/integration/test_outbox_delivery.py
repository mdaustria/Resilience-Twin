"""Committed outbox delivery and crash recovery."""

from datetime import UTC, datetime, timedelta
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.tasks.cloud import CloudTasksQueue
from services.worker.dispatch import dispatch_one
from services.worker.leases import FirestoreLeases
from services.worker.reconcile import reconcile


class Queue:
    def __init__(self) -> None:
        self.tasks: set[str] = set()
        self.fail_after_enqueue = False

    def enqueue(self, *, task_name: str, workspace_id: str, job_id: str,
                stage: str, attempt: int) -> None:
        self.tasks.add(task_name)
        if self.fail_after_enqueue:
            raise RuntimeError("crash between enqueue and outbox mark")


def test_outbox_crash_and_expired_lease_recovery(firestore_client: Client) -> None:
    actor = Actor("temporary", "dispatch-owner")
    workspace_id = "dispatch-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    now = datetime.now(UTC)
    jobs = FirestoreJobs(firestore_client, clock=lambda: now)
    submitted = jobs.submit(actor, workspace_id, route="runs", idempotency_key="one",
                            stage="simulation", input_hash="a" * 64,
                            estimated_units=1, required_seconds=100)
    job_id = submitted["job_id"]
    outbox_id = f"{job_id}-000001"
    queue = Queue()
    queue.fail_after_enqueue = True
    try:
        dispatch_one(firestore_client, queue, workspace_id, outbox_id)
    except RuntimeError:
        pass
    else:
        raise AssertionError("crash injection did not occur")
    queue.fail_after_enqueue = False
    name = dispatch_one(firestore_client, queue, workspace_id, outbox_id)
    assert len(queue.tasks) == 1 and name in queue.tasks
    leases = FirestoreLeases(firestore_client, clock=lambda: now, lease_seconds=10)
    assert leases.claim(workspace_id, job_id) == 1
    assert reconcile(firestore_client, queue, workspace_id,
                     clock=lambda: now + timedelta(seconds=11))
    root = firestore_client.collection("workspaces").document(workspace_id)
    assert root.collection("jobs").document(job_id).get().to_dict()["attempt"] == 2
    assert len(queue.tasks) == 2


def test_cloud_queue_uses_stable_name_and_oidc_identity() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []

        def queue_path(self, project: str, location: str, queue: str) -> str:
            return f"projects/{project}/locations/{location}/queues/{queue}"

        def task_path(self, project: str, location: str, queue: str, task: str) -> str:
            return f"{self.queue_path(project, location, queue)}/tasks/{task}"

        def create_task(self, *, request: dict[str, Any]) -> None:
            self.requests.append(request)
            if len(self.requests) > 1:
                raise AlreadyExists("same task")

    fake = FakeClient()
    queue = CloudTasksQueue(project_id="test-project", location_id="asia-southeast1",
        queue_id="resilience-twin-test", worker_url="https://worker.example",
        audience="https://worker.example", service_account_email=(
            "worker@test-project.iam.gserviceaccount.com"), client=fake)
    args = {"task_name": "ws-job-000001", "workspace_id": "ws",
            "job_id": "job", "stage": "simulation", "attempt": 1}
    queue.enqueue(**args)
    queue.enqueue(**args)
    assert len(fake.requests) == 2
    assert fake.requests[0] == fake.requests[1]
    item = fake.requests[0]
    assert item["task"]["name"].endswith("/tasks/ws-job-000001")
    http = item["task"]["http_request"]
    assert http["url"] == "https://worker.example/internal/tasks/ws/job"
    assert http["oidc_token"] == {
        "service_account_email": "worker@test-project.iam.gserviceaccount.com",
        "audience": "https://worker.example",
    }
