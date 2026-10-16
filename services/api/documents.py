"""Bounded private PDF upload and finalization routes."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    Conflict,
    FirestoreRepository,
)
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.documents import IntakeError, PrivateDocuments
from packages.application.sessions import SessionUnavailable
from services.api.sessions import COOKIE, NO_STORE

OwnerResolver = Callable[[str, str], tuple[Actor, datetime | None]]


def session_owner_resolver(temporary: FirestoreTemporarySessions,
                           repository: FirestoreRepository) -> OwnerResolver:
    """Resolve only a valid temporary credential for this workspace."""
    def resolve(handle: str, workspace_id: str) -> tuple[Actor, datetime | None]:
        try:
            guest = temporary.resolve(handle)
            actor = Actor("temporary", guest.owner_id)
            repository.get_workspace(actor, workspace_id)
            return actor, guest.expires_at
        except (SessionUnavailable, AccessDenied):
            raise AccessDenied("Workspace unavailable") from None
    return resolve


class UploadStart(BaseModel):
    sha256: str
    byte_count: int = Field(gt=0)


class UploadStatus(BaseModel):
    upload_id: str
    expires_at: datetime
    token: str


class UploadReceipt(BaseModel):
    generation: int


class FinalizeRequest(BaseModel):
    token: str
    quarantine_generation: int = Field(gt=0)


class ArtifactStatus(BaseModel):
    artifact_id: str
    sha256: str
    byte_count: int
    page_count: int


def documents_router(documents: PrivateDocuments, owner_for: OwnerResolver, *,
                     origin: str, csrf_key: bytes) -> APIRouter:
    if not origin.startswith("https://") or "/" in origin[8:] or len(csrf_key) < 32:
        raise ValueError("Private uploads require an HTTPS origin and CSRF secret")
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents")

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Origin, Cookie"

    def actor(handle: str | None, workspace_id: str) -> tuple[Actor, datetime | None]:
        if not handle:
            raise HTTPException(401, "Session unavailable", headers=NO_STORE)
        try:
            return owner_for(handle, workspace_id)
        except (AccessDenied, ValueError):
            raise HTTPException(404, "Workspace unavailable", headers=NO_STORE) from None

    def mutation(origin_header: str | None, handle: str | None,
                 csrf_header: str | None) -> None:
        if origin_header != origin:
            raise HTTPException(403, "Invalid origin", headers=NO_STORE)
        if not handle or csrf_header is None or not hmac.compare_digest(
            csrf_header, hmac.new(csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise HTTPException(403, "Invalid CSRF token", headers=NO_STORE)

    @router.post("/uploads", response_model=UploadStatus, status_code=201)
    def start(workspace_id: str, body: UploadStart, response: Response,
              origin_header: str | None = Header(default=None, alias="Origin"),
              handle: str | None = Cookie(default=None, alias=COOKIE),
              csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> UploadStatus:
        private(response)
        mutation(origin_header, handle, csrf_header)
        owner, expires = actor(handle, workspace_id)
        try:
            grant = documents.begin(owner, workspace_id, sha256=body.sha256,
                                    byte_count=body.byte_count, temporary_expires_at=expires)
        except IntakeError as exc:
            raise HTTPException(400, exc.code, headers=NO_STORE) from None
        return UploadStatus(upload_id=grant.upload_id, expires_at=grant.expires_at,
                            token=grant.token)

    @router.post("/uploads/{upload_id}/content", response_model=UploadReceipt)
    async def content(workspace_id: str, upload_id: str, request: Request,
                      response: Response, upload_token: str = Header(alias="X-Upload-Token"),
                      origin_header: str | None = Header(default=None, alias="Origin"),
                      handle: str | None = Cookie(default=None, alias=COOKIE),
                      csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> UploadReceipt:
        private(response)
        mutation(origin_header, handle, csrf_header)
        owner, _ = actor(handle, workspace_id)
        try:
            if documents.grant_upload_id(owner, workspace_id, upload_token) != upload_id:
                raise HTTPException(403, "Invalid upload", headers=NO_STORE)
        except IntakeError as exc:
            raise HTTPException(400, exc.code, headers=NO_STORE) from None
        limit = 10_000_000
        chunks: list[bytes] = []
        length = 0
        async for chunk in request.stream():
            length += len(chunk)
            if length > limit:
                raise HTTPException(413, "file_too_large", headers=NO_STORE)
            chunks.append(chunk)
        try:
            stored = documents.upload(owner, workspace_id, upload_token, b"".join(chunks))
        except IntakeError as exc:
            raise HTTPException(400, exc.code, headers=NO_STORE) from None
        return UploadReceipt(generation=stored.generation)

    @router.post("/uploads/{upload_id}/finalize", response_model=ArtifactStatus)
    def finalize(workspace_id: str, upload_id: str, body: FinalizeRequest,
                 response: Response, if_match: str = Header(alias="If-Match"),
                 origin_header: str | None = Header(default=None, alias="Origin"),
                 handle: str | None = Cookie(default=None, alias=COOKIE),
                 csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> ArtifactStatus:
        private(response)
        mutation(origin_header, handle, csrf_header)
        owner, _ = actor(handle, workspace_id)
        if not if_match.isdecimal():
            raise HTTPException(400, "invalid_revision", headers=NO_STORE)
        try:
            if documents.grant_upload_id(owner, workspace_id, body.token) != upload_id:
                raise HTTPException(403, "Invalid upload", headers=NO_STORE)
            artifact_id, stored, pages = documents.finalize(
                owner, workspace_id, body.token,
                quarantine_generation=body.quarantine_generation,
                expected_revision=int(if_match))
        except IntakeError as exc:
            raise HTTPException(400, exc.code, headers=NO_STORE) from None
        except Conflict:
            raise HTTPException(409, "stale_revision", headers=NO_STORE) from None
        return ArtifactStatus(artifact_id=artifact_id, sha256=stored.sha256,
                              byte_count=stored.byte_count, page_count=pages)

    return router


__all__ = ["OwnerResolver", "documents_router", "session_owner_resolver"]
