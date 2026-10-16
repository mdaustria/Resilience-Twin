"""Cloud Tasks boundary with deterministic task naming."""

from typing import Protocol

from packages.adapters.tasks.cloud import CloudTasksQueue


class TaskQueue(Protocol):
    def enqueue(self, *, task_name: str, workspace_id: str, job_id: str,
                stage: str, attempt: int) -> None: ...


__all__ = ["CloudTasksQueue", "TaskQueue"]
