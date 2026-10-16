"""Cloud Tasks HTTP queue with stable task names and OIDC worker identity."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from google.api_core.exceptions import AlreadyExists
from google.cloud.tasks_v2 import CloudTasksClient

_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


class CloudTasksQueue:
    def __init__(self, *, project_id: str, location_id: str, queue_id: str,
                 worker_url: str, audience: str, service_account_email: str,
                 client: Any = None) -> None:
        if not all(_ID.fullmatch(value) for value in (project_id, location_id, queue_id)):
            raise ValueError("Invalid Cloud Tasks queue path")
        for value in (worker_url, audience):
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError("Cloud Tasks worker and audience must be HTTPS URLs")
        if not service_account_email.endswith(".iam.gserviceaccount.com"):
            raise ValueError("Cloud Tasks OIDC service account required")
        self.client = client if client is not None else CloudTasksClient()
        self.parent = self.client.queue_path(project_id, location_id, queue_id)
        self.project_id = project_id
        self.location_id = location_id
        self.queue_id = queue_id
        self.worker_url = worker_url.rstrip("/")
        self.audience = audience
        self.service_account_email = service_account_email

    def enqueue(self, *, task_name: str, workspace_id: str, job_id: str,
                stage: str, attempt: int) -> None:
        if (not all(_ID.fullmatch(value) for value in (workspace_id, job_id))
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,500}", task_name)
                or stage not in {"extraction", "graph", "simulation", "report"}
                or type(attempt) is not int or attempt < 1):
            raise ValueError("Invalid Cloud Tasks job identity")
        name = self.client.task_path(self.project_id, self.location_id,
                                     self.queue_id, task_name)
        body = json.dumps({"workspace_id": workspace_id, "job_id": job_id,
                           "stage": stage, "attempt": attempt},
                          sort_keys=True, separators=(",", ":")).encode()
        task = {
            "name": name,
            "http_request": {
                "http_method": "POST",
                "url": f"{self.worker_url}/internal/tasks/{workspace_id}/{job_id}",
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "oidc_token": {"service_account_email": self.service_account_email,
                               "audience": self.audience},
            },
        }
        try:
            self.client.create_task(request={"parent": self.parent, "task": task})
        except AlreadyExists:
            # The outbox can be retried after enqueue succeeds but marking it fails.
            return


__all__ = ["CloudTasksQueue"]
