"""Irreversible owner/workspace tombstones and bounded expiry sweep."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter

from packages.adapters.persistence.firestore import (
    AccessDenied,
    FirestoreRepository,
)


class FirestoreDeletion:
    def __init__(self, client: Client, *, clock: Callable[[], datetime] | None = None) -> None:
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))
        self.repository = FirestoreRepository(client)

    def expire_page(self, *, limit: int = 100) -> list[str]:
        if not 1 <= limit <= 100:
            raise ValueError("Expiry page must be bounded")
        now = self.clock()
        sessions = self.client.collection("browser_sessions")
        rows = sessions.where(filter=FieldFilter("expires_at", "<=", now)).limit(limit).stream()
        ended: list[str] = []
        for row in rows:
            data = row.to_dict() or {}
            owner_id = data.get("temporary_owner_id")
            workspace_id = data.get("temporary_workspace_id")
            if not isinstance(owner_id, str) or not isinstance(workspace_id, str):
                continue
            owner = self.client.collection("owners").document(f"temporary:{owner_id}")
            workspace = self.repository._workspace(workspace_id)

            @firestore.transactional
            def write(tx: Transaction, session_ref: Any = row.reference,
                      owner_ref: Any = owner, workspace_ref: Any = workspace,
                      expected_owner: str = owner_id,
                      expected_workspace: str = workspace_id) -> bool:
                current = session_ref.get(transaction=tx).to_dict()
                owner_data = owner_ref.get(transaction=tx).to_dict()
                workspace_data = workspace_ref.get(transaction=tx).to_dict()
                if (not current or not owner_data or not workspace_data
                        or not isinstance(current.get("expires_at"), datetime)
                        or current["expires_at"] > now
                        or current.get("temporary_owner_id") != expected_owner
                        or current.get("temporary_workspace_id") != expected_workspace
                        or owner_data.get("owner_id") != expected_owner
                        or workspace_data.get("owner_id") != expected_owner
                        or workspace_data.get("owner_type") != "temporary"):
                    return False
                tx.update(session_ref, {"temporary_owner_id": None,
                                        "temporary_workspace_id": None,
                                        "expires_at": None,
                                        "temporary_revoked_at": now})
                tx.update(owner_ref, {"tombstoned_at": now})
                tx.update(workspace_ref, {"tombstoned_at": now,
                                          "cancel_requested_at": now,
                                          "purge_next_at": now})
                return True

            if write(self.client.transaction(max_attempts=5)):
                ended.append(workspace_id)
                self.cancel_jobs(workspace_id)
        return ended

    def cancel_jobs(self, workspace_id: str, *, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Cancellation page must be bounded")
        workspace = self.repository._workspace(workspace_id)
        count = 0
        while True:
            pending = list(workspace.collection("jobs").where(filter=FieldFilter(
                "status", "in", ["queued", "running"])).limit(limit).stream())
            if not pending:
                break
            for snapshot in pending:
                job = snapshot.reference
                run = workspace.collection("runs").document(snapshot.id)

                @firestore.transactional
                def write(tx: Transaction, job_ref: Any = job,
                          run_ref: Any = run) -> bool:
                    current = job_ref.get(transaction=tx).to_dict()
                    if not current or current.get("status") not in {"queued", "running"}:
                        return False
                    now = self.clock()
                    tx.update(job_ref, {"status": "cancelled", "cancel_requested": True,
                                        "fence": current.get("fence", 0) + 1,
                                        "updated_at": now})
                    tx.update(run_ref, {"status": "partial", "cancelled_at": now})
                    return True

                if write(self.client.transaction(max_attempts=5)):
                    count += 1
        return count

    def require_tombstone(self, workspace_id: str) -> dict[str, Any]:
        data = self.repository._workspace(workspace_id).get().to_dict()
        if not data or data.get("tombstoned_at") is None:
            raise AccessDenied("Workspace is not terminated")
        return cast(dict[str, Any], data)

    def purge_documents(self, workspace_id: str, *, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Purge page must be bounded")
        self.require_tombstone(workspace_id)
        remaining = limit

        def descend(document: Any) -> bool:
            nonlocal remaining
            for collection in document.collections():
                for child in collection.list_documents(page_size=limit):
                    if remaining == 0 or not descend(child):
                        return False
                    child.delete()
                    remaining -= 1
            return True

        descend(self.repository._workspace(workspace_id))
        return limit - remaining


__all__ = ["FirestoreDeletion"]
