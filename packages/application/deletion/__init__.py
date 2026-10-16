"""Deletion use case boundary: tombstone access before asynchronous cleanup."""

from dataclasses import dataclass
from typing import Protocol

from packages.application.sessions import TemporarySession


class DeletionStore(Protocol):
    def resolve(self, handle: str) -> TemporarySession: ...
    def revoke(self, handle: str) -> None: ...


@dataclass(frozen=True)
class DeleteWorkspace:
    store: DeletionStore

    def delete(self, handle: str, workspace_id: str) -> None:
        if self.store.resolve(handle).workspace_id != workspace_id:
            raise ValueError("Workspace does not belong to this session")
        self.store.revoke(handle)


__all__ = ["DeleteWorkspace"]
