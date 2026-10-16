"""Digest-only Firestore browser sessions and atomic temporary ownership."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction

from packages.adapters.persistence.usage import BudgetExceeded, FirestoreUsage
from packages.application.sessions import (
    ABSOLUTE_LIFETIME,
    IssuanceDenied,
    SessionUnavailable,
    TemporarySession,
    expiry_for,
)

SCHEMA_VERSION = 1


def _digest(handle: str) -> str:
    return hashlib.sha256(handle.encode("utf-8")).hexdigest()


class FirestoreTemporarySessions:
    def __init__(
        self, client: Client, *, clock: Callable[[], datetime] | None = None,
        issuance_check: Callable[[], bool] | None = None,
        issuance_budgets: FirestoreUsage | None = None,
    ) -> None:
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))
        # Task 4.9 wires network/account/global budgets. No per-cookie reset loophole.
        self.issuance_check = issuance_check
        self.issuance_budgets = issuance_budgets

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Server clock must be timezone aware")
        return now

    def _session_ref(self, handle: str) -> Any:
        return self.client.collection("browser_sessions").document(_digest(handle))

    @staticmethod
    def _validated(
        session: dict[str, Any] | None, owner: dict[str, Any] | None,
        workspace: dict[str, Any] | None, now: datetime,
    ) -> TemporarySession:
        if not session or not owner or not workspace:
            raise SessionUnavailable
        owner_id = session.get("temporary_owner_id")
        workspace_id = session.get("temporary_workspace_id")
        created = session.get("created_at")
        activity = session.get("last_user_activity_at")
        expires = session.get("expires_at")
        absolute = session.get("absolute_expires_at")
        if not isinstance(created, datetime) or not isinstance(activity, datetime):
            raise SessionUnavailable
        try:
            expected_expiry = expiry_for(created, activity)
        except ValueError:
            raise SessionUnavailable from None
        if (not isinstance(expires, datetime) or not isinstance(absolute, datetime)
            or session.get("schema_version") != SCHEMA_VERSION
            or any(session.get(field) is not None for field in (
                "account_owner_id", "account_auth_time", "account_expires_at",
                "account_revoked_at"))
            or owner.get("schema_version") != SCHEMA_VERSION
            or workspace.get("schema_version") != SCHEMA_VERSION
            or not isinstance(owner_id, str) or not isinstance(workspace_id, str)
            or expires != expected_expiry
            or absolute != created + ABSOLUTE_LIFETIME
            or expires <= now or session.get("revoked_at") is not None
            or owner.get("type") != "temporary" or owner.get("owner_id") != owner_id
            or owner.get("expires_at") != expires or owner.get("tombstoned_at") is not None
            or workspace.get("owner_type") != "temporary"
            or workspace.get("owner_id") != owner_id
            or workspace.get("tombstoned_at") is not None):
            raise SessionUnavailable
        return TemporarySession(owner_id, workspace_id, created, activity, expires, absolute)

    def _read(self, tx: Transaction, handle: str, now: datetime) -> tuple[TemporarySession, Any, Any, Any]:
        session_ref = self._session_ref(handle)
        session_snapshot = session_ref.get(transaction=tx)
        session = session_snapshot.to_dict()
        if not session_snapshot.exists or session is None:
            raise SessionUnavailable
        owner_id = session.get("temporary_owner_id")
        workspace_id = session.get("temporary_workspace_id")
        if not isinstance(owner_id, str) or not isinstance(workspace_id, str):
            raise SessionUnavailable
        owner_ref = self.client.collection("owners").document(f"temporary:{owner_id}")
        workspace_ref = self.client.collection("workspaces").document(workspace_id)
        owner = owner_ref.get(transaction=tx).to_dict()
        workspace = workspace_ref.get(transaction=tx).to_dict()
        view = self._validated(session, owner, workspace, now)
        return view, session_ref, owner_ref, workspace_ref

    def resolve(self, handle: str) -> TemporarySession:
        now = self._now()

        @firestore.transactional
        def read(tx: Transaction) -> TemporarySession:
            return self._read(tx, handle, now)[0]

        return cast(TemporarySession, read(self.client.transaction(max_attempts=5)))

    def issue(self, existing_handle: str | None = None, *,
              network_key: str | None = None) -> tuple[str, TemporarySession, bool]:
        if existing_handle:
            try:
                return existing_handle, self.resolve(existing_handle), False
            except SessionUnavailable:
                pass
        if self.issuance_check is None or not self.issuance_check():
            raise IssuanceDenied("Session issuance is unavailable")
        if self.issuance_budgets is not None and network_key is None:
            raise IssuanceDenied("Network issuance identity required")
        now = self._now()
        handle = secrets.token_urlsafe(32)
        owner_id = uuid4().hex
        workspace_id = uuid4().hex
        expires = expiry_for(now, now)
        session_ref = self._session_ref(handle)
        owner_ref = self.client.collection("owners").document(f"temporary:{owner_id}")
        workspace_ref = self.client.collection("workspaces").document(workspace_id)
        session = {
            "schema_version": SCHEMA_VERSION,
            "temporary_owner_id": owner_id, "temporary_workspace_id": workspace_id,
            "created_at": now,
            "last_user_activity_at": now,
            "absolute_expires_at": now + ABSOLUTE_LIFETIME,
            "expires_at": expires, "revoked_at": None,
        }
        owner = {"schema_version": SCHEMA_VERSION, "type": "temporary",
                 "owner_id": owner_id, "expires_at": expires,
                 "tombstoned_at": None, "created_at": now}
        workspace = {"schema_version": SCHEMA_VERSION, "owner_type": "temporary",
                     "owner_id": owner_id, "revision": 0,
                     "tombstoned_at": None, "created_at": now}

        @firestore.transactional
        def write(tx: Transaction) -> None:
            if self.issuance_budgets is not None:
                assert network_key is not None
                self.issuance_budgets.reserve_issuance_in_transaction(
                    tx, network_key=network_key, now=now)
            tx.create(session_ref, session)
            tx.create(owner_ref, owner)
            tx.create(workspace_ref, workspace)

        try:
            write(self.client.transaction(max_attempts=5))
        except BudgetExceeded:
            raise IssuanceDenied("Session issuance budget exhausted") from None
        return handle, TemporarySession(owner_id, workspace_id, now, now,
                                        expires, now + ABSOLUTE_LIFETIME), True

    def renew(self, handle: str) -> TemporarySession:
        now = self._now()

        @firestore.transactional
        def write(tx: Transaction) -> TemporarySession:
            current, session_ref, owner_ref, _ = self._read(tx, handle, now)
            if now < current.last_user_activity_at:
                raise SessionUnavailable
            expires = expiry_for(current.created_at, now)
            tx.update(session_ref, {"last_user_activity_at": now, "expires_at": expires})
            tx.update(owner_ref, {"expires_at": expires})
            return TemporarySession(current.owner_id, current.workspace_id,
                                    current.created_at, now, expires,
                                    current.absolute_expires_at)

        return cast(TemporarySession, write(self.client.transaction(max_attempts=5)))

    def revoke(self, handle: str) -> None:
        """Tombstone the temporary owner and its active workspace."""
        now = self._now()

        @firestore.transactional
        def write(tx: Transaction) -> str:
            view, session_ref, owner_ref, workspace_ref = self._read(tx, handle, now)
            tx.update(session_ref, {"temporary_owner_id": None,
                                    "temporary_workspace_id": None,
                                    "expires_at": None,
                                    "revoked_at": now})
            tx.update(owner_ref, {"tombstoned_at": now})
            tx.update(workspace_ref, {"tombstoned_at": now,
                                      "cancel_requested_at": now,
                                      "purge_next_at": now})
            return view.workspace_id

        workspace_id = cast(str, write(self.client.transaction(max_attempts=5)))
        from packages.adapters.persistence.deletion import FirestoreDeletion

        FirestoreDeletion(self.client, clock=self.clock).cancel_jobs(workspace_id)


__all__ = ["FirestoreTemporarySessions"]
