"""Recover pending dispatch and expired worker leases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter

from packages.adapters.tasks import TaskQueue
from services.worker.dispatch import dispatch_pending


def reconcile(client: Client, queue: TaskQueue, workspace_id: str, *,
              clock: Callable[[], datetime] | None = None,
              max_attempts: int = 3) -> list[str]:
    now = (clock or (lambda: datetime.now(UTC)))()
    root = client.collection("workspaces").document(workspace_id)
    rows: list[Any] = list(root.collection("jobs").where(
        filter=FieldFilter("status", "==", "running")).limit(100).stream())
    for row in rows:
        job = row.reference
        outbox = root.collection("outbox")

        @firestore.transactional
        def recover(tx: Transaction, job_ref: Any = job,
                    outbox_ref: Any = outbox, job_id: str = row.id) -> None:
            data = job_ref.get(transaction=tx).to_dict()
            if not data or data.get("status") != "running" or data.get("lease_until", now) > now:
                return
            attempt = data["attempt"] + 1
            if attempt > max_attempts:
                tx.update(job_ref, {"status": "failed", "error": "retry_exhausted", "updated_at": now})
                return
            tx.update(job_ref, {"status": "queued", "attempt": attempt, "updated_at": now})
            tx.create(job_ref.collection("attempts").document(f"{attempt:06d}"), {
                "schema_version": 1, "number": attempt, "status": "queued", "created_at": now})
            tx.create(outbox_ref.document(f"{job_id}-{attempt:06d}"), {
                "schema_version": 1, "job_id": job_id, "stage": data["stage"],
                "attempt": attempt, "status": "pending", "created_at": now})

        recover(client.transaction(max_attempts=5))
    return dispatch_pending(client, queue, workspace_id)


__all__ = ["reconcile"]
