"""Authenticated worker claims and monotonic Firestore fencing."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.contracts.jobs import LeaseBusy, StaleFence


def verify_worker_token(token: str | None, *, audience: str,
                        service_account_email: str,
                        verifier: Callable[[str, str], dict[str, Any]]) -> None:
    """Verify signed OIDC claims; task headers carry no authority."""
    if not token or not token.startswith("Bearer "):
        raise AccessDenied("Worker token required")
    claims = verifier(token[7:], audience)
    if (claims.get("aud") != audience or claims.get("email") != service_account_email
            or claims.get("email_verified") is not True
            or claims.get("iss") not in {"https://accounts.google.com", "accounts.google.com"}):
        raise AccessDenied("Worker identity denied")


class FirestoreLeases:
    def __init__(self, client: Client, *, clock: Callable[[], datetime] | None = None,
                 lease_seconds: int = 300) -> None:
        if not 1 <= lease_seconds <= 600:
            raise ValueError("lease must fit a bounded stage")
        self.client = client
        self.repository = FirestoreRepository(client)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lease_seconds = lease_seconds

    def _refs(self, workspace_id: str, job_id: str) -> tuple[Any, Any]:
        workspace = self.client.collection("workspaces").document(workspace_id)
        return workspace, workspace.collection("jobs").document(job_id)

    def claim(self, workspace_id: str, job_id: str) -> int | None:
        workspace, job = self._refs(workspace_id, job_id)

        @firestore.transactional
        def write(tx: Transaction) -> int | None:
            now = self.clock()
            data = job.get(transaction=tx).to_dict()
            if not data:
                raise AccessDenied("Job unavailable")
            actor = Actor(data["owner_type"], data["owner_id"])
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            if data["status"] in {"complete", "cancelled"}:
                return None
            if data["status"] == "running" and data.get("lease_until", now) > now:
                raise LeaseBusy("Job already leased")
            fence = data["fence"] + 1
            tx.update(job, {"status": "running", "fence": fence,
                            "lease_until": now + timedelta(seconds=self.lease_seconds),
                            "updated_at": now})
            return cast(int, fence)

        return cast(int | None, write(self.client.transaction(max_attempts=5)))

    def publish(self, workspace_id: str, job_id: str, fence: int,
                *, artifact_key: str, result_hash: str,
                artifact_generation: int | None = None,
                artifact_byte_count: int | None = None) -> None:
        workspace, job = self._refs(workspace_id, job_id)
        run = workspace.collection("runs").document(job_id)

        @firestore.transactional
        def write(tx: Transaction) -> None:
            now = self.clock()
            data = job.get(transaction=tx).to_dict()
            if not data or data.get("fence") != fence or data.get("status") != "running":
                raise StaleFence("Worker no longer owns job")
            actor = Actor(data["owner_type"], data["owner_id"])
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            if data.get("lease_until", now) <= now or data.get("cancel_requested"):
                raise StaleFence("Lease expired or cancelled")
            artifact: dict[str, Any] = {"artifact_key": artifact_key, "result_hash": result_hash}
            if artifact_generation is not None or artifact_byte_count is not None:
                if (not isinstance(artifact_generation, int) or artifact_generation < 1
                        or not isinstance(artifact_byte_count, int) or artifact_byte_count < 1):
                    raise ValueError("Published artifact needs a positive generation and size")
                artifact.update({"artifact_generation": artifact_generation,
                                 "artifact_byte_count": artifact_byte_count})
            tx.update(job, {"status": "complete", "updated_at": now, **artifact})
            tx.update(run, {"status": "complete", "updated_at": now, **artifact})

        write(self.client.transaction(max_attempts=5))


__all__ = ["FirestoreLeases", "LeaseBusy", "StaleFence", "verify_worker_token"]
