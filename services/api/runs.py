"""Owner-scoped run cancellation, event pages and suite progress."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Cookie, Header, Response
from pydantic import BaseModel, Field

from packages.adapters.persistence.firestore import AccessDenied, Actor, Conflict
from packages.adapters.persistence.runs import FirestoreRuns
from services.api.documents import OwnerResolver
from services.api.review import Problem
from services.api.sessions import COOKIE


class SuiteMembers(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=50)


class RunStatus(BaseModel):
    job_id: str
    stage: str
    status: str
    run_status: str
    attempt: int
    checkpoint_sequence: int
    result_hash: str | None
    cancel_requested: bool


class RunEvent(BaseModel):
    time_seconds: int
    phase: int
    sequence: int
    kind: str
    target_id: str | None


class EventPage(BaseModel):
    items: list[RunEvent]
    next: int | None
    status: str


def runs_router(runs: FirestoreRuns, owner_for: OwnerResolver, *,
                origin: str, csrf_key: bytes) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/runs")

    def actor(workspace_id: str, handle: str | None) -> Actor:
        if not handle:
            raise Problem(401, "session_unavailable", "Session unavailable")
        try:
            return owner_for(handle, workspace_id)[0]
        except AccessDenied:
            raise Problem(404, "workspace_unavailable", "Workspace unavailable") from None

    def mutation_authority(handle: str | None, request_origin: str | None,
                           csrf: str | None) -> None:
        if request_origin != origin or not handle or not csrf or not hmac.compare_digest(
            csrf, hmac.new(csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise Problem(403, "invalid_csrf", "Invalid mutation authority")

    @router.get("/{job_id}", response_model=RunStatus)
    def status(workspace_id: str, job_id: str, response: Response,
               handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        try:
            return runs.status(actor(workspace_id, handle), workspace_id, job_id)
        except ValueError:
            raise Problem(404, "run_unavailable", "Run unavailable") from None

    @router.get("/{job_id}/events", response_model=EventPage)
    def events(workspace_id: str, job_id: str, response: Response,
               after: int = 0, limit: int = 100,
               handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        if after < 0 or not 1 <= limit <= 100:
            raise Problem(422, "invalid_page", "Invalid event cursor or limit")
        try:
            return runs.event_page(actor(workspace_id, handle), workspace_id,
                                   job_id, after=after, limit=limit)
        except ValueError:
            raise Problem(404, "run_unavailable", "Run unavailable") from None

    @router.post("/{job_id}/cancel")
    def cancel(workspace_id: str, job_id: str, response: Response,
               handle: str | None = Cookie(default=None, alias=COOKIE),
               request_origin: str | None = Header(default=None, alias="Origin"),
               csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        mutation_authority(handle, request_origin, csrf)
        return runs.cancel(actor(workspace_id, handle), workspace_id, job_id)

    @router.post("/{job_id}/retry", status_code=202)
    def retry(workspace_id: str, job_id: str, response: Response,
              handle: str | None = Cookie(default=None, alias=COOKIE),
              request_origin: str | None = Header(default=None, alias="Origin"),
              csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
              key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        mutation_authority(handle, request_origin, csrf)
        if not key:
            raise Problem(400, "idempotency_required", "Idempotency-Key required")
        try:
            return runs.retry_failed(actor(workspace_id, handle), workspace_id,
                                     job_id, idempotency_key=key)
        except Conflict:
            raise Problem(409, "retry_conflict", "Job cannot be retried") from None
        except ValueError:
            raise Problem(422, "invalid_retry", "Invalid retry command") from None

    @router.post("/{job_id}/acknowledge")
    def acknowledge(workspace_id: str, job_id: str, response: Response,
                    handle: str | None = Cookie(default=None, alias=COOKIE),
                    request_origin: str | None = Header(default=None, alias="Origin"),
                    csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        mutation_authority(handle, request_origin, csrf)
        try:
            return runs.acknowledge(actor(workspace_id, handle), workspace_id, job_id)
        except Conflict:
            raise Problem(409, "acknowledge_conflict", "Job has not finished") from None
        except ValueError:
            raise Problem(404, "job_unavailable", "Job unavailable") from None

    @router.put("/suites/{suite_id}")
    def plan_suite(workspace_id: str, suite_id: str, body: SuiteMembers,
                   response: Response,
                   handle: str | None = Cookie(default=None, alias=COOKIE),
                   request_origin: str | None = Header(default=None, alias="Origin"),
                   csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        mutation_authority(handle, request_origin, csrf)
        try:
            return runs.create_suite_plan(actor(workspace_id, handle), workspace_id,
                                          suite_id, body.job_ids)
        except Conflict:
            raise Problem(409, "suite_conflict", "Suite ID already used") from None
        except ValueError:
            raise Problem(422, "invalid_suite", "Suite members unavailable") from None

    @router.get("/suites/{suite_id}")
    def read_suite(workspace_id: str, suite_id: str, response: Response,
                   handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        try:
            return runs.read_suite(actor(workspace_id, handle), workspace_id, suite_id)
        except ValueError:
            raise Problem(404, "suite_unavailable", "Suite unavailable") from None

    @router.post("/suite-status")
    def suite_status(workspace_id: str, body: SuiteMembers, response: Response,
                     handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        return runs.suite_status(actor(workspace_id, handle), workspace_id, body.job_ids)

    return router


__all__ = ["runs_router"]
