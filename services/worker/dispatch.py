"""Dispatch committed obligations with stable Cloud Task names."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2.id_token import verify_oauth2_token

from packages.adapters.persistence.firestore import AccessDenied
from packages.adapters.tasks import TaskQueue
from services.worker.leases import LeaseBusy, verify_worker_token


def dispatch_one(client: Client, queue: TaskQueue, workspace_id: str,
                 outbox_id: str) -> str:
    root = client.collection("workspaces").document(workspace_id)
    ref = root.collection("outbox").document(outbox_id)
    item = ref.get().to_dict()
    if not item or item.get("status") not in {"pending", "sent"}:
        return "absent"
    job_id = item["job_id"]
    task_name = f"{workspace_id}-{job_id}-{item['attempt']:06d}"
    # At-least-once queue creation is safe when the task name already exists.
    queue.enqueue(task_name=task_name, workspace_id=workspace_id,
                  job_id=job_id, stage=item["stage"], attempt=item["attempt"])

    @firestore.transactional
    def mark(tx: Transaction) -> None:
        current = ref.get(transaction=tx).to_dict()
        if current and current.get("status") == "pending":
            tx.update(ref, {"status": "sent", "task_name": task_name})

    mark(client.transaction(max_attempts=5))
    return task_name


def dispatch_pending(client: Client, queue: TaskQueue, workspace_id: str,
                     *, limit: int = 50) -> list[str]:
    if not 1 <= limit <= 100:
        raise ValueError("invalid outbox page")
    root = client.collection("workspaces").document(workspace_id)
    pending: list[Any] = list(root.collection("outbox").where(
        filter=FieldFilter("status", "==", "pending")).limit(limit).stream())
    return [dispatch_one(client, queue, workspace_id, row.id) for row in pending]


def worker_router(*, audience: str, service_account_email: str,
                  process: Any) -> APIRouter:
    """Authenticate the queue service account before executing a bounded stage."""
    if not audience.startswith("https://") or not service_account_email:
        raise ValueError("Worker audience and service account required")
    router = APIRouter(prefix="/internal/tasks")

    @router.post("/{workspace_id}/{job_id}")
    def execute(workspace_id: str, job_id: str,
                authorization: str | None = Header(default=None)) -> dict[str, str]:
        try:
            verify_worker_token(authorization, audience=audience,
                service_account_email=service_account_email,
                verifier=lambda token, aud: verify_oauth2_token(  # type: ignore[no-untyped-call]
                    token, GoogleRequest(), aud))
        except (AccessDenied, ValueError, GoogleAuthError):
            raise HTTPException(status_code=401, detail="Worker identity denied") from None
        try:
            process(workspace_id, job_id)
        except LeaseBusy:
            raise HTTPException(status_code=503, detail="Stage already leased") from None
        return {"status": "acknowledged"}

    return router


__all__ = ["dispatch_one", "dispatch_pending", "worker_router"]
