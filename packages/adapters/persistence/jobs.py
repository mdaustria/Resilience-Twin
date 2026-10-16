"""Atomic owner-scoped job, reservation and outbox ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    Conflict,
    FirestoreRepository,
    InvalidRecord,
    _bounded,
    _id,
)
from packages.adapters.persistence.usage import FirestoreUsage


class LifetimeTooShort(Exception):
    pass


class UsageExceeded(Exception):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FirestoreJobs:
    """Keep every accepted command and its dispatch obligation atomic."""

    def __init__(self, client: Client, *, clock: Callable[[], datetime] | None = None,
                 workspace_limit: int = 100_000,
                 budgets: FirestoreUsage | None = None) -> None:
        self.client = client
        self.repository = FirestoreRepository(client)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.workspace_limit = workspace_limit
        self.budgets = budgets

    def _workspace(self, workspace_id: str) -> Any:
        return self.client.collection("workspaces").document(_id(workspace_id))

    def submit(self, actor: Actor, workspace_id: str, *, route: str,
               idempotency_key: str, stage: str, input_hash: str,
               estimated_units: int, required_seconds: int,
               network_key: str | None = None,
               challenge_satisfied: bool = False) -> dict[str, Any]:
        if (not 1 <= len(idempotency_key) <= 128 or not idempotency_key.isascii()
                or not 1 <= len(route) <= 128 or stage not in
                {"extraction", "graph", "simulation", "report"}
                or len(input_hash) != 64 or any(c not in "0123456789abcdef" for c in input_hash)
                or type(estimated_units) is not int or estimated_units <= 0
                or type(required_seconds) is not int or not 1 <= required_seconds <= 600):
            raise InvalidRecord("Invalid job submission")
        workspace = self._workspace(workspace_id)
        owner = self.repository._owner(actor)
        command_id = _digest([actor.kind, actor.owner_id, workspace_id, route,
                              idempotency_key])
        request_hash = _digest([stage, input_hash, estimated_units, required_seconds])
        job_id = command_id[:40]
        command = workspace.collection("job_commands").document(command_id)
        job = workspace.collection("jobs").document(job_id)
        attempt = job.collection("attempts").document("000001")
        outbox = workspace.collection("outbox").document(f"{job_id}-000001")
        reservation = workspace.collection("usage_reservations").document(job_id)
        usage = workspace.collection("usage").document("total")

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            now = self.clock()
            self.repository._authorize(tx, owner, workspace, actor, now)
            prior = command.get(transaction=tx).to_dict()
            if prior:
                if prior.get("request_hash") != request_hash:
                    raise Conflict("Idempotency key reused with different job")
                return cast(dict[str, Any], prior["response"])
            owner_data = owner.get(transaction=tx).to_dict() or {}
            expires = owner_data.get("expires_at")
            if actor.kind == "temporary" and (
                not isinstance(expires, datetime)
                or expires < now + timedelta(seconds=required_seconds + 30)
            ):
                raise LifetimeTooShort("Temporary lifetime cannot fit this stage")
            tally = usage.get(transaction=tx).to_dict() or {}
            reserved = tally.get("reserved_units", 0)
            if type(reserved) is not int or reserved < 0 or reserved + estimated_units > self.workspace_limit:
                raise UsageExceeded("Workspace usage reservation exceeded")
            budget_metadata = {}
            if self.budgets is not None:
                if network_key is None:
                    raise InvalidRecord("Network budget identity required")
                budget_metadata = self.budgets.reserve_in_transaction(
                    tx, actor, workspace_id, job_id, network_key=network_key,
                    estimated_units=estimated_units, now=now,
                    challenge_satisfied=challenge_satisfied)
            response = {"job_id": job_id, "run_id": job_id,
                        "status": "queued", "stage": stage}
            tx.create(command, _bounded({"schema_version": 1, "request_hash": request_hash,
                                          "response": response, "created_at": now}))
            tx.create(job, _bounded({"schema_version": 1, "workspace_id": workspace_id,
                                      "owner_type": actor.kind, "owner_id": actor.owner_id,
                                      "stage": stage, "status": "queued", "input_hash": input_hash,
                                      "attempt": 1, "fence": 0, "cancel_requested": False,
                                      "created_at": now, "updated_at": now}))
            tx.create(attempt, _bounded({"schema_version": 1, "number": 1,
                                          "status": "queued", "created_at": now}))
            tx.create(workspace.collection("runs").document(job_id), _bounded({
                "schema_version": 1, "job_id": job_id, "input_hash": input_hash,
                "stage": stage, "status": "queued", "created_at": now}))
            tx.create(outbox, _bounded({"schema_version": 1, "job_id": job_id,
                                         "stage": stage, "attempt": 1,
                                         "status": "pending", "created_at": now}))
            tx.create(reservation, _bounded({"schema_version": 1, "job_id": job_id,
                                              "estimated_units": estimated_units,
                                              "status": "reserved", "created_at": now,
                                              **budget_metadata}))
            tx.set(usage, _bounded({"schema_version": 1,
                                    "reserved_units": reserved + estimated_units,
                                    "updated_at": now}))
            return response

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))

    def read(self, actor: Actor, workspace_id: str, job_id: str) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        data = self._workspace(workspace_id).collection("jobs").document(_id(job_id)).get().to_dict()
        if not data or data.get("owner_type") != actor.kind or data.get("owner_id") != actor.owner_id:
            raise AccessDenied("Job unavailable")
        return cast(dict[str, Any], data)


__all__ = ["FirestoreJobs", "LifetimeTooShort", "UsageExceeded"]
