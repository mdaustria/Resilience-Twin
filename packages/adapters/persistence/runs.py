"""Fenced checkpoints, paged events and durable suite member status."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction

from packages.adapters.persistence.firestore import (
    Actor,
    Conflict,
    FirestoreRepository,
    _bounded,
    _id,
)
from packages.contracts.checkpoints import canonical_json
from packages.contracts.jobs import StaleFence
from packages.contracts.outcomes import Outcome


class FirestoreRuns:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.repository = FirestoreRepository(client)

    def _refs(self, workspace_id: str, job_id: str) -> tuple[Any, Any, Any]:
        workspace = self.client.collection("workspaces").document(_id(workspace_id))
        return (workspace, workspace.collection("jobs").document(_id(job_id)),
                workspace.collection("runs").document(_id(job_id)))

    def checkpoint(self, workspace_id: str, job_id: str, fence: int,
                   *, checkpoint_json: str, sequence: int) -> None:
        workspace, job, run = self._refs(workspace_id, job_id)
        if len(checkpoint_json.encode()) > 110_000 or sequence < 0:
            raise ValueError("Checkpoint needs bounded artifact storage")

        @firestore.transactional
        def write(tx: Transaction) -> None:
            now = datetime.now(UTC)
            data = job.get(transaction=tx).to_dict()
            if not data or data.get("fence") != fence or data.get("status") != "running":
                raise StaleFence("Checkpoint fence expired")
            actor = Actor(data["owner_type"], data["owner_id"])
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            if data.get("cancel_requested") or data.get("lease_until", now) <= now:
                raise StaleFence("Checkpoint cancelled or expired")
            tx.update(run, {"checkpoint_json": checkpoint_json,
                            "checkpoint_sequence": sequence, "status": "partial",
                            "updated_at": now})

        write(self.client.transaction(max_attempts=5))

    def read_checkpoint(self, workspace_id: str, job_id: str) -> str | None:
        _, _, run = self._refs(workspace_id, job_id)
        data = run.get().to_dict() or {}
        return cast(str | None, data.get("checkpoint_json"))

    def append_events(self, workspace_id: str, job_id: str, fence: int,
                      events: list[dict[str, Any]], *, chunk_size: int = 50) -> None:
        if not 1 <= chunk_size <= 100:
            raise ValueError("Invalid event chunk size")
        workspace, job, run = self._refs(workspace_id, job_id)
        for index in range(0, len(events), chunk_size):
            chunk = _bounded({"schema_version": 1, "start": index,
                              "end": min(index + chunk_size, len(events)),
                              "events_json": json.dumps(events[index:index + chunk_size],
                                                        sort_keys=True, separators=(",", ":"))})
            ref = run.collection("event_chunks").document(f"{index:010d}")

            @firestore.transactional
            def write(tx: Transaction, event_ref: Any = ref,
                      event_chunk: dict[str, Any] = chunk) -> None:
                now = datetime.now(UTC)
                data = job.get(transaction=tx).to_dict()
                if not data or data.get("fence") != fence or data.get("status") != "running":
                    raise StaleFence("Event fence expired")
                actor = Actor(data["owner_type"], data["owner_id"])
                self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
                if data.get("cancel_requested") or data.get("lease_until", now) <= now:
                    raise StaleFence("Event publication cancelled or expired")
                tx.set(event_ref, event_chunk)

            write(self.client.transaction(max_attempts=5))

    def event_page(self, actor: Actor, workspace_id: str, job_id: str, *,
                   after: int = 0, limit: int = 100) -> dict[str, Any]:
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid event page")
        self.repository.get_workspace(actor, workspace_id)
        _, _, run = self._refs(workspace_id, job_id)
        data = run.get().to_dict()
        if not data:
            raise ValueError("Run unavailable")
        items: list[dict[str, Any]] = []
        for chunk in run.collection("event_chunks").order_by("start").stream():
            part = chunk.to_dict() or {}
            if part.get("end", 0) <= after:
                continue
            for offset, event in enumerate(json.loads(part["events_json"]), part["start"]):
                if offset >= after:
                    items.append(event)
                    if len(items) == limit:
                        return {"items": items, "next": offset + 1, "status": data["status"]}
        return {"items": items, "next": None, "status": data["status"]}

    def status(self, actor: Actor, workspace_id: str, job_id: str) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        _, job, run = self._refs(workspace_id, job_id)
        job_data = job.get().to_dict()
        if not job_data or (job_data.get("owner_type"), job_data.get("owner_id")) != (
            actor.kind, actor.owner_id
        ):
            raise ValueError("Job unavailable")
        run_data = run.get().to_dict()
        if not run_data:
            raise ValueError("Run unavailable")
        return {"job_id": job_id, "stage": job_data["stage"],
                "status": job_data["status"], "run_status": run_data["status"],
                "attempt": job_data["attempt"],
                "checkpoint_sequence": run_data.get("checkpoint_sequence", 0),
                "result_hash": run_data.get("result_hash"),
                "cancel_requested": job_data.get("cancel_requested", False)}

    def record_member_outcome(self, workspace_id: str, job_id: str, fence: int,
                              *, member_id: str, pins: dict[str, Any],
                              outcome: Outcome, event_hash: str) -> None:
        """Worker-only fenced publication of a measured paired-member outcome."""
        workspace, job, run = self._refs(workspace_id, job_id)
        if not member_id or len(event_hash) != 64:
            raise ValueError("Measured member identity and event hash required")
        values = (outcome.on_time_people, outcome.vulnerable_on_time_people,
                  outcome.water_unmet_ml, outcome.stranded_people)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Measured outcome requires nonnegative integer units")
        _, _, event_run = self._refs(workspace_id, job_id)
        committed = [event for chunk in event_run.collection("event_chunks").order_by("start").stream()
                     for event in json.loads((chunk.to_dict() or {})["events_json"])]
        if hashlib.sha256(canonical_json(committed)).hexdigest() != event_hash:
            raise ValueError("Outcome event hash differs from committed events")
        event_ids = {f"{event['sequence']}:{event['kind']}" for event in committed}
        if not outcome.evidence_event_ids or not set(outcome.evidence_event_ids) <= event_ids:
            raise ValueError("Outcome evidence references uncommitted events")
        payload = _bounded({"member_id": member_id, "pins": pins,
                            "outcome": {"on_time_people": outcome.on_time_people,
                                        "vulnerable_on_time_people": outcome.vulnerable_on_time_people,
                                        "water_unmet_ml": outcome.water_unmet_ml,
                                        "stranded_people": outcome.stranded_people,
                                        "evidence_event_ids": list(outcome.evidence_event_ids)},
                            "event_hash": event_hash})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            now = datetime.now(UTC)
            data = job.get(transaction=tx).to_dict()
            if not data or data.get("fence") != fence or data.get("status") != "running":
                raise StaleFence("Outcome fence expired")
            actor = Actor(data["owner_type"], data["owner_id"])
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            if data.get("stage") != "simulation" or data.get("cancel_requested") or (
                data.get("lease_until", now) <= now or data.get("input_hash") != pins.get("input_hash")
            ):
                raise StaleFence("Outcome inputs or lease differ")
            current = run.get(transaction=tx).to_dict() or {}
            if current.get("member_result") not in (None, payload):
                raise StaleFence("Outcome already differs")
            tx.update(run, {"member_result": payload, "updated_at": now})

        write(self.client.transaction(max_attempts=5))

    def read_member_outcome(self, actor: Actor, workspace_id: str,
                            job_id: str) -> dict[str, Any] | None:
        self.repository.get_workspace(actor, workspace_id)
        _, job, run = self._refs(workspace_id, job_id)
        data = job.get().to_dict()
        if not data or (data.get("owner_type"), data.get("owner_id")) != (
            actor.kind, actor.owner_id
        ):
            raise ValueError("Member job unavailable")
        result = run.get().to_dict() or {}
        if data.get("status") != "complete" or result.get("status") != "complete":
            return None
        member = result.get("member_result")
        if member is None or member.get("event_hash") != result.get("result_hash"):
            return None
        return cast(dict[str, Any], member)

    def cancel(self, actor: Actor, workspace_id: str, job_id: str) -> dict[str, Any]:
        workspace, job, run = self._refs(workspace_id, job_id)

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            now = datetime.now(UTC)
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            data = job.get(transaction=tx).to_dict()
            if not data or (data.get("owner_type"), data.get("owner_id")) != (
                actor.kind, actor.owner_id
            ):
                raise ValueError("Job unavailable")
            if data["status"] not in {"complete", "cancelled", "failed"}:
                tx.update(job, {"cancel_requested": True, "status": "cancelled",
                                "fence": data["fence"] + 1, "updated_at": now})
                tx.update(run, {"status": "partial", "cancelled_at": now})
            return {"job_id": job_id, "status": "cancelled" if data["status"] != "complete"
                    else "complete"}

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))

    def suite_status(self, actor: Actor, workspace_id: str,
                     member_job_ids: list[str]) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        if not member_job_ids or len(member_job_ids) > 50 or len(set(member_job_ids)) != len(member_job_ids):
            raise ValueError("Invalid suite members")
        rows = [self._refs(workspace_id, job_id)[1].get().to_dict()
                for job_id in member_job_ids]
        if any(not row or (row.get("owner_type"), row.get("owner_id")) !=
               (actor.kind, actor.owner_id) for row in rows):
            raise ValueError("Suite member unavailable")
        statuses = [row["status"] for row in rows if row]
        complete = statuses.count("complete")
        failed = statuses.count("failed")
        cancelled = statuses.count("cancelled")
        return {"planned": len(statuses), "completed": complete, "failed": failed,
                "cancelled": cancelled, "partial": complete != len(statuses),
                "members": [{"job_id": job_id, "status": status}
                            for job_id, status in zip(member_job_ids, statuses, strict=True)]}

    def create_suite_plan(self, actor: Actor, workspace_id: str, suite_id: str,
                          member_job_ids: list[str]) -> dict[str, Any]:
        if not member_job_ids or len(member_job_ids) > 50 or len(set(member_job_ids)) != len(member_job_ids):
            raise ValueError("Invalid suite members")
        workspace = self.client.collection("workspaces").document(_id(workspace_id))
        suite = workspace.collection("suites").document(_id(suite_id))
        members = [workspace.collection("jobs").document(_id(job_id))
                   for job_id in member_job_ids]

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            self.repository._authorize(tx, self.repository._owner(actor),
                                       workspace, actor, datetime.now(UTC))
            prior = suite.get(transaction=tx).to_dict()
            if prior:
                if prior.get("member_job_ids") != member_job_ids:
                    raise Conflict("Suite ID reused with different members")
                return {"suite_id": suite_id, "member_job_ids": member_job_ids}
            for ref in members:
                job = ref.get(transaction=tx).to_dict()
                if not job or (job.get("owner_type"), job.get("owner_id")) != (
                    actor.kind, actor.owner_id):
                    raise ValueError("Suite member unavailable")
            tx.create(suite, _bounded({"schema_version": 1,
                                       "member_job_ids": member_job_ids,
                                       "created_at": datetime.now(UTC)}))
            return {"suite_id": suite_id, "member_job_ids": member_job_ids}

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))

    def read_suite(self, actor: Actor, workspace_id: str, suite_id: str) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        suite = self.client.collection("workspaces").document(_id(workspace_id)).collection(
            "suites").document(_id(suite_id)).get().to_dict()
        if not suite:
            raise ValueError("Suite unavailable")
        return {"suite_id": suite_id, **self.suite_status(actor, workspace_id,
                                                          suite["member_job_ids"])}

    def retry_failed(self, actor: Actor, workspace_id: str, job_id: str,
                     *, idempotency_key: str, max_attempts: int = 3) -> dict[str, Any]:
        if not 1 <= len(idempotency_key) <= 128 or not 2 <= max_attempts <= 10:
            raise ValueError("Invalid retry command")
        workspace, job, run = self._refs(workspace_id, job_id)

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            now = datetime.now(UTC)
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            data = job.get(transaction=tx).to_dict()
            if not data or (data.get("owner_type"), data.get("owner_id")) != (
                actor.kind, actor.owner_id):
                raise ValueError("Job unavailable")
            if data.get("retry_key") == idempotency_key:
                return cast(dict[str, Any], data["retry_response"])
            if data["status"] != "failed" or data.get("cancel_requested"):
                raise Conflict("Only failed uncancelled jobs can be retried")
            attempt = data["attempt"] + 1
            if attempt > max_attempts:
                raise Conflict("Retry limit reached")
            response = {"job_id": job_id, "attempt": attempt, "status": "queued"}
            tx.update(job, {"status": "queued", "attempt": attempt,
                            "retry_key": idempotency_key, "retry_response": response,
                            "updated_at": now})
            tx.update(run, {"status": "queued", "updated_at": now})
            tx.create(job.collection("attempts").document(f"{attempt:06d}"), _bounded({
                "schema_version": 1, "number": attempt, "status": "queued", "created_at": now}))
            tx.create(workspace.collection("outbox").document(f"{job_id}-{attempt:06d}"),
                      _bounded({"schema_version": 1, "job_id": job_id,
                                "stage": data["stage"], "attempt": attempt,
                                "status": "pending", "created_at": now}))
            return response

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))

    def acknowledge(self, actor: Actor, workspace_id: str, job_id: str) -> dict[str, Any]:
        workspace, job, run = self._refs(workspace_id, job_id)

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            now = datetime.now(UTC)
            self.repository._authorize(tx, self.repository._owner(actor), workspace, actor, now)
            data = job.get(transaction=tx).to_dict()
            if not data or (data.get("owner_type"), data.get("owner_id")) != (
                actor.kind, actor.owner_id):
                raise ValueError("Job unavailable")
            if data["status"] not in {"complete", "failed", "cancelled"}:
                raise Conflict("Job has not reached a terminal state")
            if not data.get("acknowledged_at"):
                tx.update(job, {"acknowledged_at": now})
                tx.update(run, {"acknowledged_at": now})
            return {"job_id": job_id, "status": data["status"], "acknowledged": True}

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))


__all__ = ["FirestoreRuns"]
