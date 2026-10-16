"""Development-only synthetic evidence review API."""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Cookie, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    Conflict,
    InvalidRecord,
)
from packages.application.review import (
    DEFAULTS_VERSION,
    ReviewCase,
    ReviewService,
    default_assumptions,
)
from packages.application.versions import DurableVersions
from packages.domain.evidence import ReviewAssumption, ReviewClaim, ReviewDraft
from packages.domain.readiness import Readiness
from packages.domain.versions import RevisionConflict
from services.api.documents import OwnerResolver
from services.api.sessions import COOKIE


class ReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ReviewDraft
    readiness: Readiness
    defaults_version: str
    default_assumptions: tuple[ReviewAssumption, ...]


class AssumptionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    assumption: ReviewAssumption


class BundleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    defaults_version: str
    assumptions: tuple[ReviewAssumption, ...]


class CorrectionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    correction: ReviewClaim


class RevisionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)


class InitializeReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publication_reference: str = Field(min_length=1)
    textual_location: str = Field(min_length=1)
    scenario_date: date


class DurableReviewContent(BaseModel):
    draft: ReviewDraft
    readiness: Readiness


class DurableReviewRecord(BaseModel):
    workspace_id: str
    entity_id: str
    revision: int
    content_hash: str
    sealed: bool
    updated_at: datetime
    content: DurableReviewContent


def review_router(service: ReviewService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/local/review", tags=["local-review"])

    def snapshot(result: tuple[ReviewDraft, Readiness]) -> ReviewSnapshot:
        return ReviewSnapshot(draft=result[0], readiness=result[1],
                              defaults_version=DEFAULTS_VERSION,
                              default_assumptions=default_assumptions(result[0]))

    @router.get("", response_model=ReviewSnapshot)
    def read_review(x_fixture_owner: str = Header(),
                    x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        return snapshot(service.get(x_fixture_owner, x_fixture_case))

    @router.post("/assumption", response_model=ReviewSnapshot)
    def add_assumption(command: AssumptionCommand, x_fixture_owner: str = Header(),
                       x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        try:
            return snapshot(service.declare_assumption(x_fixture_owner, command.expected_revision,
                                                       command.assumption, x_fixture_case))
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.post("/assumptions", response_model=ReviewSnapshot)
    def add_assumptions(command: BundleCommand, x_fixture_owner: str = Header(),
                        x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        try:
            return snapshot(service.declare_bundle(x_fixture_owner, command.expected_revision,
                                                   command.assumptions, command.defaults_version,
                                                   x_fixture_case))
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.post("/correction", response_model=ReviewSnapshot)
    def add_correction(command: CorrectionCommand, x_fixture_owner: str = Header(),
                       x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        try:
            return snapshot(service.correct(x_fixture_owner, command.expected_revision,
                                            command.correction, x_fixture_case))
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.post("/seal", response_model=ReviewSnapshot)
    def seal_review(command: RevisionCommand, x_fixture_owner: str = Header(),
                    x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        try:
            return snapshot(service.seal(x_fixture_owner, command.expected_revision, x_fixture_case))
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None

    @router.post("/acknowledge", response_model=ReviewSnapshot)
    def acknowledge_review(command: RevisionCommand, x_fixture_owner: str = Header(),
                           x_fixture_case: Annotated[ReviewCase, Header()] = "synthetic") -> ReviewSnapshot:
        try:
            return snapshot(service.acknowledge(x_fixture_owner, command.expected_revision, x_fixture_case))
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    return router


__all__ = ["ReviewSnapshot", "review_router"]


class Problem(Exception):
    def __init__(self, status: int, code: str, title: str) -> None:
        self.status = status
        self.code = code
        self.title = title


def problem_response(error: Problem) -> JSONResponse:
    return JSONResponse(status_code=error.status, media_type="application/problem+json",
        content={"type": "about:blank", "title": error.title,
                 "status": error.status, "code": error.code},
        headers={"Cache-Control": "private, no-store"})


class VersionHttp:
    def __init__(self, service: DurableVersions, owner_for: OwnerResolver, *,
                 origin: str, csrf_key: bytes) -> None:
        if not origin.startswith("https://") or "/" in origin[8:] or len(csrf_key) < 32:
            raise ValueError("Durable commands need HTTPS origin and CSRF secret")
        self.service = service
        self.owner_for = owner_for
        self.origin = origin
        self.csrf_key = csrf_key

    def owner(self, workspace_id: str, handle: str | None) -> Actor:
        if not handle:
            raise Problem(401, "session_unavailable", "Session unavailable")
        try:
            return self.owner_for(handle, workspace_id)[0]
        except (AccessDenied, ValueError):
            raise Problem(404, "workspace_unavailable", "Workspace unavailable") from None

    def mutation(self, workspace_id: str, handle: str | None,
                 request_origin: str | None, csrf: str | None,
                 if_match: str | None, idempotency_key: str | None) -> tuple[Actor, int, str]:
        if request_origin != self.origin:
            raise Problem(403, "invalid_origin", "Invalid origin")
        if not handle or csrf is None or not hmac.compare_digest(
            csrf, hmac.new(self.csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise Problem(403, "invalid_csrf", "Invalid CSRF token")
        if if_match is None or not if_match.isdecimal():
            raise Problem(428, "revision_required", "If-Match revision required")
        if idempotency_key is None or not 1 <= len(idempotency_key) <= 128:
            raise Problem(400, "idempotency_required", "Idempotency-Key required")
        return self.owner(workspace_id, handle), int(if_match), idempotency_key

    @staticmethod
    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Origin, Cookie"

    @staticmethod
    def translate(exc: Exception) -> Problem:
        if isinstance(exc, (Conflict, RevisionConflict)):
            return Problem(409, "version_conflict", "Version conflict")
        if isinstance(exc, AccessDenied):
            return Problem(404, "version_unavailable", "Version unavailable")
        if isinstance(exc, (InvalidRecord, ValueError, TypeError, KeyError)):
            return Problem(422, "invalid_command", "Invalid version command")
        raise exc


COMMAND_ERRORS = (Conflict, RevisionConflict, AccessDenied, InvalidRecord, ValueError,
                  TypeError, KeyError)


def durable_review_router(http: VersionHttp) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/reviews")

    @router.post("/{review_id}/initialize", response_model=DurableReviewRecord)
    def initialize(workspace_id: str, review_id: str, body: InitializeReviewCommand,
                   response: Response,
                   handle: str | None = Cookie(default=None, alias=COOKIE),
                   request_origin: str | None = Header(default=None, alias="Origin"),
                   csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
                   if_match: str | None = Header(default=None, alias="If-Match"),
                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.initialize_review(actor, workspace_id, review_id,
                body.artifact_id, title=body.title,
                publication_reference=body.publication_reference,
                textual_location=body.textual_location,
                scenario_date=body.scenario_date, revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.put("/{review_id}", response_model=DurableReviewRecord)
    def save(workspace_id: str, review_id: str, draft: ReviewDraft, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE),
             request_origin: str | None = Header(default=None, alias="Origin"),
             csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
             if_match: str | None = Header(default=None, alias="If-Match"),
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.save_review(actor, workspace_id, review_id, draft,
                                            revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.post("/{review_id}/seal", response_model=DurableReviewRecord)
    def seal_version(workspace_id: str, review_id: str, response: Response,
                     handle: str | None = Cookie(default=None, alias=COOKIE),
                     request_origin: str | None = Header(default=None, alias="Origin"),
                     csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
                     if_match: str | None = Header(default=None, alias="If-Match"),
                     idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.seal_review(actor, workspace_id, review_id,
                                            revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.post("/{review_id}/acknowledge", response_model=DurableReviewRecord)
    def acknowledge_version(workspace_id: str, review_id: str, response: Response,
                            handle: str | None = Cookie(default=None, alias=COOKIE),
                            request_origin: str | None = Header(default=None, alias="Origin"),
                            csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
                            if_match: str | None = Header(default=None, alias="If-Match"),
                            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.acknowledge_review(actor, workspace_id, review_id,
                                                   revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{review_id}")
    def read(workspace_id: str, review_id: str, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.read(http.owner(workspace_id, handle),
                                           workspace_id, "reviews", review_id))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{review_id}/history")
    def history(workspace_id: str, review_id: str, response: Response,
                after_revision: int = 0, limit: int = 20,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            items = http.service.store.history(http.owner(workspace_id, handle),
                workspace_id, "reviews", review_id,
                after_revision=after_revision, limit=limit)
            return {"items": items, "next_after_revision": items[-1]["revision"] if items else None}
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{review_id}/versions/{revision}")
    def version(workspace_id: str, review_id: str, revision: int, response: Response,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.version(http.owner(workspace_id, handle),
                                              workspace_id, "reviews", review_id, revision))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    return router


__all__ += ["Problem", "VersionHttp", "durable_review_router", "problem_response"]


def baselines_router(http: VersionHttp) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/baselines")

    @router.put("/{baseline_id}")
    def seal_baseline(workspace_id: str, baseline_id: str, body: dict[str, Any], response: Response,
                      handle: str | None = Cookie(default=None, alias=COOKIE),
                      request_origin: str | None = Header(default=None, alias="Origin"),
                      csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
                      if_match: str | None = Header(default=None, alias="If-Match"),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.seal_baseline(actor, workspace_id, baseline_id, body,
                                              revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{baseline_id}")
    def read(workspace_id: str, baseline_id: str, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.read(http.owner(workspace_id, handle),
                                           workspace_id, "baselines", baseline_id))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{baseline_id}/history")
    def history(workspace_id: str, baseline_id: str, response: Response,
                after_revision: int = 0, limit: int = 20,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            items = http.service.store.history(http.owner(workspace_id, handle),
                workspace_id, "baselines", baseline_id,
                after_revision=after_revision, limit=limit)
            return {"items": items, "next_after_revision": items[-1]["revision"] if items else None}
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    return router


__all__ += ["baselines_router"]
