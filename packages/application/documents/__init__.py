"""Quarantined local PDF intake; persistence and scanning are ports."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from packages.contracts.documents import (
    INTAKE_POLICIES,
    DocumentArtifact,
    DocumentPage,
    IntakePolicy,
    OwnershipMode,
)

WORKSPACE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class IntakeError(Exception):
    """A repairable, content-free error suitable for an intake response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ScannerPort(Protocol):
    def scan(self, quarantined_path: Path) -> None: ...


class PdfValidatorPort(Protocol):
    def physical_page_count(self, quarantined_path: Path, max_pages: int) -> int: ...


class QuarantineStorePort(Protocol):
    def quarantine(self, workspace_id: str, source: bytes) -> Path: ...

    def publish(self, workspace_id: str, digest: str, quarantined_path: Path) -> str: ...

    def discard(self, quarantined_path: Path) -> None: ...


class ActorPort(Protocol):
    @property
    def kind(self) -> Literal["temporary", "account"]: ...
    @property
    def owner_id(self) -> str: ...


class ArtifactRepositoryPort(Protocol):
    def get_workspace(self, actor: ActorPort, workspace_id: str, *,
                      now: datetime | None = None) -> dict[str, Any]: ...
    def put_artifact(self, actor: ActorPort, workspace_id: str, artifact_id: str,
                     *, sha256: str, object_key: str, generation: int,
                     byte_count: int, kind: str, expected_revision: int,
                     crs: str | None = None, bounds: list[float] | None = None,
                     physical_page_count: int | None = None) -> None: ...
    def get_record(self, actor: ActorPort, workspace_id: str,
                   kind: Literal["artifacts", "evidence", "twins", "versions"],
                   record_id: str, *, twin_id: str | None = None) -> dict[str, Any]: ...


class ObjectConflict(Exception):
    pass


class ObjectMissing(Exception):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    generation: int
    sha256: str
    byte_count: int


class PrivateObjectStore(Protocol):
    def write_once(self, key: str, data: bytes) -> StoredObject: ...
    def read_all(self, key: str, generation: int) -> bytes: ...
    def read_range(self, key: str, generation: int, start: int, length: int) -> bytes: ...
    def delete(self, key: str, generation: int) -> None: ...


@dataclass(frozen=True)
class UploadGrant:
    upload_id: str
    expires_at: datetime
    token: str


class PrivateDocuments:
    """Owner-checked immutable PDF intake and revocable artifact reads."""

    def __init__(self, repository: Any, objects: PrivateObjectStore,
                 scanner: ScannerPort, validator: PdfValidatorPort, *, secret: bytes,
                 clock: Callable[[], datetime] | None = None) -> None:
        if len(secret) < 32:
            raise ValueError("Upload signing secret must contain 32 bytes")
        self.repository = repository
        self.objects = objects
        self.scanner = scanner
        self.validator = validator
        self.secret = secret
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Server clock must be timezone aware")
        return value

    def begin(self, actor: ActorPort, workspace_id: str, *, sha256: str,
              byte_count: int, temporary_expires_at: datetime | None = None) -> UploadGrant:
        from uuid import uuid4

        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise IntakeError("invalid_digest", "The upload checksum is invalid.")
        policy = INTAKE_POLICIES["temporary" if actor.kind == "temporary" else "saved"]
        if byte_count < 1 or byte_count > policy.max_bytes_per_file:
            raise IntakeError("file_too_large", "The PDF exceeds the published per-file byte limit.")
        self.repository.get_workspace(actor, workspace_id, now=self._now())
        expiry = self._now() + timedelta(minutes=10)
        if actor.kind == "temporary":
            if temporary_expires_at is None or temporary_expires_at <= self._now():
                raise IntakeError("session_expired", "The temporary session has expired.")
            expiry = min(expiry, temporary_expires_at)
        upload_id = uuid4().hex
        payload = {"v": 1, "actor_kind": actor.kind, "actor_id": actor.owner_id,
                   "workspace_id": workspace_id, "upload_id": upload_id,
                   "sha256": sha256, "byte_count": byte_count,
                   "expires_at": expiry.isoformat()}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return UploadGrant(upload_id, expiry, f"{encoded}.{signature}")

    def _grant(self, actor: ActorPort, workspace_id: str, token: str) -> dict[str, Any]:
        try:
            encoded, signature = token.split(".", 1)
            if len(token) > 2048 or not hmac.compare_digest(
                signature, hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            ):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if not isinstance(payload, dict):
                raise TypeError
            expiry = datetime.fromisoformat(payload["expires_at"])
            if (payload["v"] != 1 or payload["actor_kind"] != actor.kind
                    or payload["actor_id"] != actor.owner_id
                    or payload["workspace_id"] != workspace_id
                    or not re.fullmatch(r"[0-9a-f]{32}", payload["upload_id"])
                    or expiry.tzinfo is None or expiry <= self._now()):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
            raise IntakeError("invalid_upload", "The upload authorization is invalid or expired.") from None
        self.repository.get_workspace(actor, workspace_id, now=self._now())
        return cast(dict[str, Any], payload)

    def upload(self, actor: ActorPort, workspace_id: str, token: str, source: bytes) -> StoredObject:
        payload = self._grant(actor, workspace_id, token)
        if len(source) != payload["byte_count"] or hashlib.sha256(source).hexdigest() != payload["sha256"]:
            raise IntakeError("source_changed", "The uploaded PDF differs from its authorization.")
        if not source.startswith(b"%PDF-"):
            raise IntakeError("invalid_signature", "The file is not a supported PDF.")
        key = f"workspaces/{workspace_id}/quarantine/{payload['upload_id']}.pdf"
        try:
            return self.objects.write_once(key, source)
        except ObjectConflict:
            raise IntakeError("upload_conflict", "This upload was already received.") from None

    def grant_upload_id(self, actor: ActorPort, workspace_id: str, token: str) -> str:
        return cast(str, self._grant(actor, workspace_id, token)["upload_id"])

    def finalize(self, actor: ActorPort, workspace_id: str, token: str, *,
                 quarantine_generation: int, expected_revision: int) -> tuple[str, StoredObject, int]:
        payload = self._grant(actor, workspace_id, token)
        stage_key = f"workspaces/{workspace_id}/quarantine/{payload['upload_id']}.pdf"
        try:
            source = self.objects.read_all(stage_key, quarantine_generation)
        except ObjectMissing:
            raise IntakeError("missing_upload", "The quarantined PDF is unavailable.") from None
        if len(source) != payload["byte_count"] or hashlib.sha256(source).hexdigest() != payload["sha256"]:
            raise IntakeError("source_changed", "The quarantined PDF changed before finalization.")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pdf"
            path.write_bytes(source)
            self.scanner.scan(path)
            policy = INTAKE_POLICIES["temporary" if actor.kind == "temporary" else "saved"]
            pages = self.validator.physical_page_count(path, policy.max_physical_pages_per_file)
            if hashlib.sha256(path.read_bytes()).hexdigest() != payload["sha256"]:
                raise IntakeError("source_changed", "The PDF changed during validation.")
        final_key = f"workspaces/{workspace_id}/documents/{payload['upload_id']}.pdf"
        stored = self.objects.write_once(final_key, source)
        try:
            self.repository.put_artifact(actor, workspace_id, payload["upload_id"],
                sha256=stored.sha256, object_key=stored.key, generation=stored.generation,
                byte_count=stored.byte_count, kind="source_pdf",
                expected_revision=expected_revision, physical_page_count=pages)
        except BaseException:
            self.objects.delete(final_key, stored.generation)
            raise
        self.objects.delete(stage_key, quarantine_generation)
        return payload["upload_id"], stored, pages

    def stream(self, authorize: Callable[[], ActorPort], workspace_id: str,
               artifact_id: str, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        if not 1 <= chunk_size <= 1024 * 1024:
            raise ValueError("Invalid stream chunk size")
        actor = authorize()
        metadata = self.repository.get_record(actor, workspace_id, "artifacts", artifact_id)
        key = metadata["object_key"]
        generation = metadata["generation"]
        size = metadata["byte_count"]
        if (not isinstance(key, str) or not key.startswith(f"workspaces/{workspace_id}/")
                or not isinstance(generation, int) or generation < 1
                or not isinstance(size, int) or size < 0):
            raise IntakeError("invalid_artifact", "Artifact metadata is invalid.")
        for start in range(0, size, chunk_size):
            current = authorize()
            if current != actor:
                raise IntakeError("owner_changed", "Artifact access ended.")
            self.repository.get_workspace(current, workspace_id, now=self._now())
            chunk = self.objects.read_range(key, generation, start, min(chunk_size, size - start))
            if len(chunk) != min(chunk_size, size - start):
                raise IntakeError("source_changed", "The stored artifact is incomplete.")
            # Deletion may race an object-store read; check again before delivery.
            if authorize() != actor:
                raise IntakeError("owner_changed", "Artifact access ended.")
            self.repository.get_workspace(actor, workspace_id, now=self._now())
            yield chunk


class LocalPdfIntake:
    def __init__(
        self,
        *,
        scanner: ScannerPort,
        validator: PdfValidatorPort,
        store: QuarantineStorePort,
        policies: dict[OwnershipMode, IntakePolicy] | None = None,
    ) -> None:
        self.scanner = scanner
        self.validator = validator
        self.store = store
        self.policies = policies or INTAKE_POLICIES

    def accept(self, *, workspace_id: str, ownership_mode: OwnershipMode, source: bytes) -> DocumentArtifact:
        if not WORKSPACE_ID.fullmatch(workspace_id):
            raise IntakeError("invalid_workspace", "A valid workspace is required.")
        policy = self.policies[ownership_mode]
        if len(source) > policy.max_bytes_per_file:
            raise IntakeError("file_too_large", "The PDF exceeds the published per-file byte limit.")
        if not source.startswith(b"%PDF-"):
            raise IntakeError("invalid_signature", "The file is not a supported PDF.")

        expected_digest = hashlib.sha256(source).hexdigest()
        quarantined = self.store.quarantine(workspace_id, source)
        try:
            # A parser result cannot substitute for a clean malware scan.
            self.scanner.scan(quarantined)
            page_count = self.validator.physical_page_count(
                quarantined, policy.max_physical_pages_per_file
            )
            staged = quarantined.read_bytes()
            if len(staged) != len(source) or hashlib.sha256(staged).hexdigest() != expected_digest:
                raise IntakeError("source_changed", "The quarantined PDF changed during validation.")
            storage_key = self.store.publish(workspace_id, expected_digest, quarantined)
        finally:
            self.store.discard(quarantined)

        return DocumentArtifact(
            workspace_id=workspace_id,
            ownership_mode=ownership_mode,
            storage_key=storage_key,
            sha256=expected_digest,
            byte_size=len(source),
            physical_page_count=page_count,
            pages=tuple(DocumentPage(physical_page=index) for index in range(1, page_count + 1)),
        )


__all__ = ["IntakeError", "LocalPdfIntake", "PdfValidatorPort", "QuarantineStorePort", "ScannerPort"]
