"""Owner-scoped Firestore metadata transactions."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter

from packages.contracts.ownership import Actor

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 128 * 1024
_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


class AccessDenied(Exception):
    pass


class Conflict(Exception):
    pass


class InvalidRecord(Exception):
    pass


def _id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise InvalidRecord("Invalid document identifier")
    return value


def _bounded(record: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(record, default=str, separators=(",", ":")).encode()) > MAX_DOCUMENT_BYTES:
        raise InvalidRecord("Metadata document exceeds 128 KiB")
    return record


class FirestoreRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def _owner(self, actor: Actor) -> Any:
        if actor.kind != "temporary":
            raise AccessDenied("Temporary session required")
        return self.client.collection("owners").document(f"{actor.kind}:{_id(actor.owner_id)}")

    def _workspace(self, workspace_id: str) -> Any:
        return self.client.collection("workspaces").document(_id(workspace_id))

    @staticmethod
    def _authorize(tx: Transaction, owner_ref: Any, workspace_ref: Any,
                   actor: Actor, now: datetime) -> dict[str, Any]:
        if actor.kind != "temporary":
            raise AccessDenied("Temporary session required")
        owner = owner_ref.get(transaction=tx)
        workspace = workspace_ref.get(transaction=tx)
        if not owner.exists or not workspace.exists:
            raise AccessDenied("Workspace unavailable")
        owner_data = owner.to_dict()
        data = workspace.to_dict()
        if (owner_data is None or data is None
                or owner_data.get("schema_version") != SCHEMA_VERSION
                or data.get("schema_version") != SCHEMA_VERSION
                or owner_data.get("type") != "temporary"
                or owner_data.get("owner_id") != actor.owner_id
                or data.get("owner_type") != "temporary"
                or data.get("owner_id") != actor.owner_id
                or owner_data.get("owner_user_id") is not None
                or data.get("owner_user_id") is not None
                or (data.get("owner_temporary_session_id") is not None
                    and data.get("owner_temporary_session_id") != actor.owner_id)
                or owner_data.get("tombstoned_at") is not None
                or data.get("tombstoned_at") is not None):
            raise AccessDenied("Workspace unavailable")
        expiry = owner_data.get("expires_at")
        if not isinstance(expiry, datetime) or expiry <= now:
            raise AccessDenied("Workspace expired")
        return cast(dict[str, Any], data)

    def create_owner_workspace(self, actor: Actor, workspace_id: str, *,
                               expires_at: datetime | None = None) -> None:
        if actor.kind != "temporary":
            raise AccessDenied("Temporary session required")
        if expires_at is None or expires_at.tzinfo is None or expires_at <= datetime.now(UTC):
            raise InvalidRecord("Temporary owner needs timezone-aware expiry")
        owner_ref = self._owner(actor)
        workspace_ref = self._workspace(workspace_id)
        now = datetime.now(UTC)
        owner_data = _bounded({"schema_version": SCHEMA_VERSION, "type": "temporary",
                               "owner_id": actor.owner_id, "expires_at": expires_at,
                               "tombstoned_at": None, "created_at": now})
        workspace_data = _bounded({"schema_version": SCHEMA_VERSION,
                                   "owner_type": "temporary", "owner_id": actor.owner_id,
                                   "owner_temporary_session_id": actor.owner_id,
                                   "revision": 0, "tombstoned_at": None, "created_at": now})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            existing_owner = owner_ref.get(transaction=tx)
            if workspace_ref.get(transaction=tx).exists:
                raise Conflict("Workspace already exists")
            if existing_owner.exists:
                raise Conflict("Temporary owner already has a workspace")
            tx.create(owner_ref, owner_data)
            tx.create(workspace_ref, workspace_data)

        write(self.client.transaction(max_attempts=5))

    def get_workspace(self, actor: Actor, workspace_id: str, *,
                      now: datetime | None = None) -> dict[str, Any]:
        @firestore.transactional
        def read(tx: Transaction) -> dict[str, Any]:
            return self._authorize(tx, self._owner(actor), self._workspace(workspace_id),
                                   actor, now or datetime.now(UTC))

        return cast(dict[str, Any], read(self.client.transaction(max_attempts=5)))

    def get_record(self, actor: Actor, workspace_id: str,
                   kind: Literal["artifacts", "evidence", "twins", "versions"],
                   record_id: str, *, twin_id: str | None = None) -> dict[str, Any]:
        if kind not in ("artifacts", "evidence", "twins", "versions"):
            raise InvalidRecord("Unsupported record kind")
        workspace_ref = self._workspace(workspace_id)
        if kind == "versions":
            if twin_id is None:
                raise InvalidRecord("Version lookup needs twin ID")
            ref = workspace_ref.collection("twins").document(_id(twin_id)).collection(
                "versions"
            ).document(_id(record_id))
        else:
            ref = workspace_ref.collection(kind).document(_id(record_id))

        @firestore.transactional
        def read(tx: Transaction) -> dict[str, Any]:
            self._authorize(tx, self._owner(actor), workspace_ref, actor, datetime.now(UTC))
            snapshot = ref.get(transaction=tx)
            data = snapshot.to_dict()
            if (not snapshot.exists or data is None or data.get("workspace_id") != workspace_id
                    or data.get("schema_version") != SCHEMA_VERSION):
                raise AccessDenied("Record unavailable")
            return cast(dict[str, Any], data)

        return cast(dict[str, Any], read(self.client.transaction(max_attempts=5)))

    def list_workspaces(self, actor: Actor, *, limit: int = 50) -> list[dict[str, Any]]:
        if actor.kind != "temporary":
            raise AccessDenied("Temporary session required")
        if not 1 <= limit <= 100:
            raise InvalidRecord("Invalid page size")
        owner = self._owner(actor).get()
        data = owner.to_dict()
        if (not owner.exists or data is None or data.get("schema_version") != SCHEMA_VERSION
                or data.get("type") != actor.kind
                or data.get("owner_id") != actor.owner_id
                or data.get("owner_user_id") is not None
                or data.get("tombstoned_at") is not None
                or not isinstance(data.get("expires_at"), datetime)
                or data["expires_at"] <= datetime.now(UTC)):
            raise AccessDenied("Owner unavailable")
        query = (self.client.collection("workspaces")
                 .where(filter=FieldFilter("owner_type", "==", actor.kind))
                 .where(filter=FieldFilter("owner_id", "==", actor.owner_id))
                 .where(filter=FieldFilter("tombstoned_at", "==", None))
                 .order_by("created_at").limit(limit))
        rows = [cast(dict[str, Any], snapshot.to_dict()) for snapshot in query.stream()]
        if len(rows) > 1 or any(row.get("schema_version") != SCHEMA_VERSION
               or row.get("owner_type") != "temporary"
               or row.get("owner_id") != actor.owner_id
               or row.get("owner_user_id") is not None
               or (row.get("owner_temporary_session_id") is not None
                   and row.get("owner_temporary_session_id") != actor.owner_id)
               for row in rows):
            raise AccessDenied("Workspace unavailable")
        return rows

    def put_artifact(self, actor: Actor, workspace_id: str, artifact_id: str,
                     *, sha256: str, object_key: str, generation: int,
                     byte_count: int, kind: str, expected_revision: int,
                     crs: str | None = None, bounds: list[float] | None = None,
                     physical_page_count: int | None = None) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256) or generation < 1 or byte_count < 0:
            raise InvalidRecord("Invalid artifact identity")
        if not object_key.startswith(f"workspaces/{workspace_id}/") or ".." in object_key:
            raise InvalidRecord("Artifact key must be workspace-scoped")
        if bounds is not None and (
            len(bounds) != 4
            or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                   for value in bounds)
            or bounds[0] > bounds[2] or bounds[1] > bounds[3]
        ):
            raise InvalidRecord("Invalid geometry bounds")
        if kind == "reviewed_geometry" and (not crs or bounds is None):
            raise InvalidRecord("Reviewed geometry needs CRS and searchable bounds")
        if physical_page_count is not None and (kind != "source_pdf" or
                                                not 1 <= physical_page_count <= 200):
            raise InvalidRecord("Source PDF page count is invalid")
        workspace_ref = self._workspace(workspace_id)
        artifact_ref = workspace_ref.collection("artifacts").document(_id(artifact_id))
        record = _bounded({"schema_version": SCHEMA_VERSION, "workspace_id": workspace_id,
                           "sha256": sha256, "object_key": object_key,
                           "generation": generation, "byte_count": byte_count,
                           "kind": kind, "crs": crs, "bounds": bounds,
                           "physical_page_count": physical_page_count,
                           "created_at": datetime.now(UTC)})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            workspace = self._authorize(tx, self._owner(actor), workspace_ref, actor, datetime.now(UTC))
            if workspace["revision"] != expected_revision:
                raise Conflict("Stale workspace revision")
            if artifact_ref.get(transaction=tx).exists:
                raise Conflict("Artifact is immutable")
            tx.create(artifact_ref, record)
            tx.update(workspace_ref, {"revision": expected_revision + 1})

        write(self.client.transaction(max_attempts=5))

    def put_evidence(self, actor: Actor, workspace_id: str, evidence_id: str,
                     *, source_artifact_id: str, physical_page: int,
                     claim: str, expected_revision: int) -> None:
        if physical_page < 1 or not claim.strip():
            raise InvalidRecord("Evidence requires physical page and claim")
        workspace_ref = self._workspace(workspace_id)
        source_ref = workspace_ref.collection("artifacts").document(_id(source_artifact_id))
        evidence_ref = workspace_ref.collection("evidence").document(_id(evidence_id))
        record = _bounded({"schema_version": SCHEMA_VERSION, "workspace_id": workspace_id,
                           "source_artifact_id": source_artifact_id,
                           "physical_page": physical_page, "claim": claim,
                           "revision": 0, "created_at": datetime.now(UTC)})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            workspace = self._authorize(tx, self._owner(actor), workspace_ref, actor, datetime.now(UTC))
            if workspace["revision"] != expected_revision:
                raise Conflict("Stale workspace revision")
            source = source_ref.get(transaction=tx)
            if not source.exists or source.to_dict().get("workspace_id") != workspace_id:
                raise InvalidRecord("Source artifact missing")
            if evidence_ref.get(transaction=tx).exists:
                raise Conflict("Evidence already exists")
            tx.create(evidence_ref, record)
            tx.update(workspace_ref, {"revision": expected_revision + 1})

        write(self.client.transaction(max_attempts=5))

    def create_twin(self, actor: Actor, workspace_id: str, twin_id: str,
                    *, source_artifact_id: str, expected_revision: int) -> None:
        workspace_ref = self._workspace(workspace_id)
        source_ref = workspace_ref.collection("artifacts").document(_id(source_artifact_id))
        twin_ref = workspace_ref.collection("twins").document(_id(twin_id))
        record = _bounded({"schema_version": SCHEMA_VERSION, "workspace_id": workspace_id,
                           "source_artifact_id": source_artifact_id,
                           "revision": 0, "created_at": datetime.now(UTC)})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            workspace = self._authorize(tx, self._owner(actor), workspace_ref, actor, datetime.now(UTC))
            if workspace["revision"] != expected_revision:
                raise Conflict("Stale workspace revision")
            source = source_ref.get(transaction=tx)
            if not source.exists or source.to_dict().get("workspace_id") != workspace_id:
                raise InvalidRecord("Source artifact missing")
            if twin_ref.get(transaction=tx).exists:
                raise Conflict("Twin already exists")
            tx.create(twin_ref, record)
            tx.update(workspace_ref, {"revision": expected_revision + 1})

        write(self.client.transaction(max_attempts=5))

    def seal_version(self, actor: Actor, workspace_id: str, twin_id: str,
                     version_id: str, *, artifact_id: str, evidence_ids: list[str],
                     input_hash: str, expected_revision: int) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise InvalidRecord("Invalid input hash")
        if len(evidence_ids) > 100 or len(set(evidence_ids)) != len(evidence_ids):
            raise InvalidRecord("Invalid evidence references")
        workspace_ref = self._workspace(workspace_id)
        artifact_ref = workspace_ref.collection("artifacts").document(_id(artifact_id))
        twin_ref = workspace_ref.collection("twins").document(_id(twin_id))
        version_ref = twin_ref.collection("versions").document(_id(version_id))
        evidence_refs = [workspace_ref.collection("evidence").document(_id(item)) for item in evidence_ids]
        record = _bounded({"schema_version": SCHEMA_VERSION, "workspace_id": workspace_id,
                           "twin_id": twin_id, "source_artifact_id": artifact_id,
                           "evidence_ids": evidence_ids, "input_hash": input_hash,
                           "sealed_at": datetime.now(UTC)})

        @firestore.transactional
        def write(tx: Transaction) -> None:
            self._authorize(tx, self._owner(actor), workspace_ref, actor, datetime.now(UTC))
            twin = twin_ref.get(transaction=tx)
            if (not twin.exists or twin.to_dict().get("workspace_id") != workspace_id
                    or twin.to_dict().get("source_artifact_id") != artifact_id):
                raise InvalidRecord("Twin reference missing")
            if twin.to_dict().get("revision") != expected_revision:
                raise Conflict("Stale twin revision")
            artifact = artifact_ref.get(transaction=tx)
            if not artifact.exists or artifact.to_dict().get("workspace_id") != workspace_id:
                raise InvalidRecord("Artifact reference missing")
            for ref in evidence_refs:
                item = ref.get(transaction=tx)
                if (not item.exists or item.to_dict().get("workspace_id") != workspace_id
                        or item.to_dict().get("source_artifact_id") != artifact_id):
                    raise InvalidRecord("Evidence reference missing or mismatched")
            if version_ref.get(transaction=tx).exists:
                raise Conflict("Version is immutable")
            tx.create(version_ref, record)
            tx.update(twin_ref, {"revision": expected_revision + 1})

        write(self.client.transaction(max_attempts=5))


__all__ = ["AccessDenied", "Actor", "Conflict", "FirestoreRepository", "InvalidRecord"]
