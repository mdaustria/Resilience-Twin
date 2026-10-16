"""Repeated bounded purge of terminated workspace objects and records."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol

from google.cloud.firestore_v1 import Client
from google.cloud.firestore_v1.base_query import FieldFilter

from packages.adapters.persistence.deletion import FirestoreDeletion


class PurgeObjects(Protocol):
    def list_workspace_versions(self, workspace_id: str, *, limit: int = 100) -> list[tuple[str, int]]: ...
    def delete(self, key: str, generation: int) -> None: ...


def purge_page(deletion: FirestoreDeletion, objects: PurgeObjects,
               workspace_id: str, *, limit: int = 100) -> dict[str, int]:
    if not 1 <= limit <= 100:
        raise ValueError("Purge page must be bounded")
    deletion.require_tombstone(workspace_id)
    versions = objects.list_workspace_versions(workspace_id, limit=limit)
    for key, generation in versions:
        objects.delete(key, generation)
    documents = deletion.purge_documents(workspace_id, limit=limit)
    return {"objects": len(versions), "documents": documents}


def run_purge_cycle(client: Client, objects: PurgeObjects, *,
                    clock: Callable[[], datetime] | None = None,
                    workspace_limit: int = 100, page_limit: int = 100,
                    max_pages_per_workspace: int = 1000) -> dict[str, int | float]:
    """One schedulable pass; unfinished work remains due after interruption."""
    if not 1 <= workspace_limit <= 100 or not 1 <= page_limit <= 100 or not 1 <= max_pages_per_workspace <= 1000:
        raise ValueError("Purge cycle bounds invalid")
    now = (clock or (lambda: datetime.now(UTC)))()
    deletion = FirestoreDeletion(client, clock=lambda: now)
    started = perf_counter()
    expired = deletion.expire_page(limit=workspace_limit)
    due = list(client.collection("workspaces").where(filter=FieldFilter(
        "purge_next_at", "<=", now)).limit(workspace_limit).stream())
    totals: dict[str, int | float] = {"expired": len(expired), "workspaces": 0,
                                       "objects": 0, "documents": 0,
                                       "pages": 0, "backlog": 0}
    for snapshot in due:
        totals["workspaces"] += 1
        complete = False
        for _ in range(max_pages_per_workspace):
            page = purge_page(deletion, objects, snapshot.id, limit=page_limit)
            totals["objects"] += page["objects"]
            totals["documents"] += page["documents"]
            totals["pages"] += 1
            if page == {"objects": 0, "documents": 0}:
                complete = True
                break
        if not complete:
            totals["backlog"] += 1
            continue
        tombstoned = (snapshot.to_dict() or {}).get("tombstoned_at")
        if not isinstance(tombstoned, datetime):
            raise TypeError("Purge workspace has no termination time")
        deadline = tombstoned + timedelta(hours=24)
        if now >= deadline:
            snapshot.reference.update({"purge_next_at": None, "purge_completed_at": now})
        else:
            snapshot.reference.update({"purge_next_at": min(
                now + timedelta(hours=1), deadline)})
    totals["elapsed_seconds"] = round(perf_counter() - started, 3)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded temporary-content purge cycle")
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--workspace-limit", type=int, default=100)
    parser.add_argument("--page-limit", type=int, default=100)
    args = parser.parse_args()
    if os.environ.get("RT_PURGE_ENABLED") != "1":
        raise SystemExit("RT_PURGE_ENABLED=1 required before live purge")
    from google.cloud import storage  # type: ignore[attr-defined]

    from packages.adapters.storage import FirebaseObjectStore

    client = Client(project=args.project, database=args.database)
    bucket = storage.Client(project=args.project).bucket(args.bucket)
    if not bucket.exists():
        raise SystemExit("Configured purge bucket is unavailable")
    result = run_purge_cycle(client, FirebaseObjectStore(bucket),
                             workspace_limit=args.workspace_limit,
                             page_limit=args.page_limit)
    print(json.dumps(result, sort_keys=True))
    return 0


__all__ = ["purge_page", "run_purge_cycle"]


if __name__ == "__main__":
    raise SystemExit(main())
