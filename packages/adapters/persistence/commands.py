"""Transactional owner-scoped version commands and change history."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    Conflict,
    FirestoreRepository,
    InvalidRecord,
    _bounded,
)

_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")
KINDS = frozenset({"reviews", "baselines", "scenarios", "scenario_suites", "proposals", "reports"})


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {**{key: value for key, value in record.items() if key != "content_json"},
            "content": json.loads(record["content_json"])}


class FirestoreVersionCommands:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.repository = FirestoreRepository(client)

    def _entity(self, workspace_id: str, kind: str, entity_id: str) -> Any:
        if kind not in KINDS or not _ID.fullmatch(entity_id) or not _ID.fullmatch(workspace_id):
            raise InvalidRecord("Invalid version path")
        return self.client.collection("workspaces").document(workspace_id).collection(
            kind).document(entity_id)

    def replay(self, actor: Actor, workspace_id: str, kind: str, entity_id: str,
               *, expected_revision: int, idempotency_key: str, route: str) -> dict[str, Any] | None:
        """Return a committed bodyless command only to its original owner and path."""
        self.repository.get_workspace(actor, workspace_id)
        self._entity(workspace_id, kind, entity_id)
        idem_id = _hash([actor.kind, actor.owner_id, workspace_id, route, idempotency_key])
        prior = self.client.collection("workspaces").document(workspace_id).collection(
            "idempotency").document(idem_id).get().to_dict()
        if prior is None:
            return None
        if (prior.get("actor_kind") != actor.kind or prior.get("actor_id") != actor.owner_id
                or prior.get("kind") != kind or prior.get("entity_id") != entity_id
                or prior.get("expected_revision") != expected_revision):
            raise Conflict("Idempotency key reused with different command")
        return _public(cast(dict[str, Any], prior["result"]))

    def commit(self, actor: Actor, workspace_id: str, kind: str, entity_id: str,
               *, expected_revision: int, idempotency_key: str, route: str,
               content: dict[str, Any], seal: bool = False,
               immutable: bool = False) -> dict[str, Any]:
        if (expected_revision < 0 or not 1 <= len(idempotency_key) <= 128
                or not idempotency_key.isascii() or len(route) > 128):
            raise InvalidRecord("Invalid revision or idempotency key")
        _bounded(content)
        entity = self._entity(workspace_id, kind, entity_id)
        workspace = self.client.collection("workspaces").document(workspace_id)
        owner = self.client.collection("owners").document(f"{actor.kind}:{actor.owner_id}")
        idem_id = _hash([actor.kind, actor.owner_id, workspace_id, route,
                         idempotency_key])
        idem_ref = workspace.collection("idempotency").document(idem_id)
        request_hash = _hash([kind, entity_id, expected_revision, content, seal, immutable])
        now = datetime.now(UTC)

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            self.repository._authorize(tx, owner, workspace, actor, now)
            prior = idem_ref.get(transaction=tx).to_dict()
            if prior:
                if (prior.get("request_hash") != request_hash
                        or prior.get("actor_kind") != actor.kind
                        or prior.get("actor_id") != actor.owner_id):
                    raise Conflict("Idempotency key reused with different command")
                return _public(cast(dict[str, Any], prior["result"]))
            current = entity.get(transaction=tx).to_dict()
            revision = 0 if current is None else current.get("revision")
            if revision != expected_revision or (immutable and current is not None):
                raise Conflict("Stale or immutable version")
            new_revision = expected_revision + 1
            result = _bounded({"schema_version": 1, "workspace_id": workspace_id,
                               "kind": kind, "entity_id": entity_id,
                               "revision": new_revision,
                               "content_json": json.dumps(content, sort_keys=True,
                                                          separators=(",", ":")),
                               "content_hash": _hash(content), "sealed": seal,
                               "updated_at": now})
            history = _bounded({"schema_version": 1, "workspace_id": workspace_id,
                                "revision": new_revision, "content_hash": result["content_hash"],
                                "sealed": seal, "actor_kind": actor.kind,
                                "actor_id": actor.owner_id, "created_at": now})
            tx.set(entity, result)
            tx.create(entity.collection("history").document(f"{new_revision:010d}"), history)
            if seal:
                tx.create(entity.collection("versions").document(f"{new_revision:010d}"),
                          result)
            tx.create(idem_ref, _bounded({"schema_version": 1,
                                         "actor_kind": actor.kind, "actor_id": actor.owner_id,
                                         "kind": kind, "entity_id": entity_id,
                                         "expected_revision": expected_revision,
                                         "request_hash": request_hash, "result": result,
                                         "created_at": now}))
            return _public(result)

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))

    def read(self, actor: Actor, workspace_id: str, kind: str,
             entity_id: str) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        data = self._entity(workspace_id, kind, entity_id).get().to_dict()
        if (not data or data.get("workspace_id") != workspace_id
                or data.get("schema_version") != 1):
            raise AccessDenied("Version unavailable")
        return _public(cast(dict[str, Any], data))

    def history(self, actor: Actor, workspace_id: str, kind: str, entity_id: str,
                *, after_revision: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        if after_revision < 0 or not 1 <= limit <= 100:
            raise InvalidRecord("Invalid history page")
        self.read(actor, workspace_id, kind, entity_id)
        query = (self._entity(workspace_id, kind, entity_id).collection("history")
                 .where(filter=FieldFilter("revision", ">", after_revision))
                 .order_by("revision").limit(limit))
        return [cast(dict[str, Any], item.to_dict()) for item in query.stream()]

    def version(self, actor: Actor, workspace_id: str, kind: str,
                entity_id: str, revision: int) -> dict[str, Any]:
        self.repository.get_workspace(actor, workspace_id)
        data = self._entity(workspace_id, kind, entity_id).collection(
            "versions").document(f"{revision:010d}").get().to_dict()
        if not data or data.get("workspace_id") != workspace_id:
            raise AccessDenied("Version unavailable")
        return _public(cast(dict[str, Any], data))


__all__ = ["FirestoreVersionCommands"]
