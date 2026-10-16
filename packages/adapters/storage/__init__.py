"""Immutable object stores for private workspace artifacts."""

from __future__ import annotations

import hashlib
from typing import Any

from packages.application.documents import (
    WORKSPACE_ID,
    ObjectConflict,
    ObjectMissing,
    StoredObject,
)


class MemoryObjectStore:
    """Faithful immutable/generation local adapter for authorization tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[int, bytes]] = {}
        self.next_generation = 1

    def write_once(self, key: str, data: bytes) -> StoredObject:
        if key in self.objects:
            raise ObjectConflict
        generation = self.next_generation
        self.next_generation += 1
        self.objects[key] = generation, bytes(data)
        return StoredObject(key, generation, hashlib.sha256(data).hexdigest(), len(data))

    def read_range(self, key: str, generation: int, start: int, length: int) -> bytes:
        record = self.objects.get(key)
        if record is None or record[0] != generation:
            raise ObjectMissing
        return record[1][start:start + length]

    def read_all(self, key: str, generation: int) -> bytes:
        record = self.objects.get(key)
        if record is None or record[0] != generation:
            raise ObjectMissing
        return record[1]

    def delete(self, key: str, generation: int) -> None:
        if key in self.objects and self.objects[key][0] == generation:
            del self.objects[key]

    def list_workspace_versions(self, workspace_id: str, *, limit: int = 100) -> list[tuple[str, int]]:
        if not WORKSPACE_ID.fullmatch(workspace_id) or not 1 <= limit <= 100:
            raise ValueError("Invalid workspace purge page")
        prefix = f"workspaces/{workspace_id}/"
        return [(key, generation) for key, (generation, _) in
                sorted(self.objects.items()) if key.startswith(prefix)][:limit]


class FirebaseObjectStore:
    """Cloud Storage adapter; the bucket is configured and verified by deployment."""

    def __init__(self, bucket: Any, *, prefix: str = "resilience-twin") -> None:
        if not prefix or "/" in prefix or ".." in prefix:
            raise ValueError("Invalid application object prefix")
        self.bucket = bucket
        self.prefix = prefix

    @classmethod
    def from_configured_bucket(cls, bucket_name: str, *, prefix: str = "resilience-twin") -> FirebaseObjectStore:
        from firebase_admin import storage  # type: ignore[import-untyped]

        if not bucket_name or "/" in bucket_name:
            raise ValueError("A private bucket name is required")
        bucket = storage.bucket(bucket_name)
        if not bucket.exists():
            raise ValueError("Configured private bucket does not exist")
        return cls(bucket, prefix=prefix)

    def _blob(self, key: str) -> Any:
        if not key.startswith("workspaces/") or ".." in key or "\\" in key:
            raise ValueError("Invalid workspace object key")
        return self.bucket.blob(f"{self.prefix}/{key}")

    def write_once(self, key: str, data: bytes) -> StoredObject:
        from google.api_core.exceptions import PreconditionFailed

        blob = self._blob(key)
        try:
            blob.upload_from_string(data, content_type="application/octet-stream",
                                    if_generation_match=0)
        except PreconditionFailed as exc:
            raise ObjectConflict from exc
        if blob.generation is None:
            blob.reload()
        return StoredObject(key, int(blob.generation), hashlib.sha256(data).hexdigest(),
                            len(data))

    def read_range(self, key: str, generation: int, start: int, length: int) -> bytes:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        try:
            return bytes(self._blob(key).download_as_bytes(
                start=start, end=start + length - 1, if_generation_match=generation))
        except (NotFound, PreconditionFailed) as exc:
            raise ObjectMissing from exc

    def read_all(self, key: str, generation: int) -> bytes:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        try:
            return bytes(self._blob(key).download_as_bytes(
                if_generation_match=generation))
        except (NotFound, PreconditionFailed) as exc:
            raise ObjectMissing from exc

    def delete(self, key: str, generation: int) -> None:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        try:
            self._blob(key).delete(if_generation_match=generation)
        except (NotFound, PreconditionFailed):
            return

    def list_workspace_versions(self, workspace_id: str, *, limit: int = 100) -> list[tuple[str, int]]:
        if not WORKSPACE_ID.fullmatch(workspace_id) or not 1 <= limit <= 100:
            raise ValueError("Invalid workspace purge page")
        prefix = f"workspaces/{workspace_id}/"
        full_prefix = f"{self.prefix}/{prefix}"
        blobs = self.bucket.list_blobs(prefix=full_prefix, versions=True, page_size=limit)
        result: list[tuple[str, int]] = []
        for blob in blobs:
            if blob.name.startswith(full_prefix) and blob.generation is not None:
                result.append((blob.name[len(self.prefix) + 1:], int(blob.generation)))
                if len(result) == limit:
                    break
        return result


__all__ = ["FirebaseObjectStore", "MemoryObjectStore", "ObjectConflict",
           "ObjectMissing", "StoredObject"]
