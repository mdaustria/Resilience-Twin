"""Same-origin, CSRF-protected temporary browser session endpoints."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel

from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.sessions import (
    IssuanceDenied,
    SessionUnavailable,
    TemporarySession,
)
from packages.application.usage import network_bucket

COOKIE = "__session"
NO_STORE = {"Cache-Control": "private, no-store"}


class SessionStatus(BaseModel):
    workspace_id: str
    expires_at: datetime
    absolute_expires_at: datetime
    csrf_token: str


def sessions_router(store: FirestoreTemporarySessions, *, origin: str, csrf_key: bytes,
                    network_secret: bytes | None = None) -> APIRouter:
    if not origin.startswith("https://") or "/" in origin[8:]:
        raise ValueError("The public session origin must be one HTTPS origin")
    if len(csrf_key) < 32:
        raise ValueError("CSRF secret must contain at least 32 bytes")
    router = APIRouter(prefix="/api/v1/temporary-sessions")

    def token(handle: str) -> str:
        return hmac.new(csrf_key, handle.encode("utf-8"), hashlib.sha256).hexdigest()

    def status(view: TemporarySession, handle: str) -> SessionStatus:
        return SessionStatus(workspace_id=view.workspace_id, expires_at=view.expires_at,
                             absolute_expires_at=view.absolute_expires_at,
                             csrf_token=token(handle))

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Origin, Cookie"

    def same_origin(request_origin: str | None) -> None:
        if request_origin != origin:
            raise HTTPException(status_code=403, detail="Invalid origin", headers=NO_STORE)

    def require_csrf(handle: str, supplied: str | None) -> None:
        if supplied is None or not hmac.compare_digest(supplied, token(handle)):
            raise HTTPException(status_code=403, detail="Invalid CSRF token", headers=NO_STORE)

    @router.post("", response_model=SessionStatus)
    def create(response: Response, request: Request,
               origin_header: str | None = Header(default=None, alias="Origin"),
               handle: str | None = Cookie(default=None, alias=COOKIE),
               csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> SessionStatus:
        private(response)
        same_origin(origin_header)
        if handle:
            try:
                store.resolve(handle)
            except SessionUnavailable:
                pass
            else:
                require_csrf(handle, csrf_header)
        try:
            network_key = (network_bucket(request.client.host, network_secret)
                           if network_secret is not None and request.client is not None else None)
            issued_handle, view, created = store.issue(handle, network_key=network_key)
        except IssuanceDenied:
            raise HTTPException(status_code=429, detail="Session issuance unavailable",
                                headers=NO_STORE) from None
        if created:
            response.status_code = 201
            response.set_cookie(COOKIE, issued_handle, secure=True, httponly=True,
                                samesite="lax", path="/", max_age=24 * 60 * 60)
        return status(view, issued_handle)

    @router.get("/current", response_model=SessionStatus)
    def current(response: Response,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> SessionStatus:
        private(response)
        if not handle:
            raise HTTPException(status_code=401, detail="Session unavailable", headers=NO_STORE)
        try:
            return status(store.resolve(handle), handle)
        except SessionUnavailable:
            raise HTTPException(status_code=401, detail="Session unavailable",
                                headers=NO_STORE) from None

    @router.post("/current/activity", response_model=SessionStatus)
    def activity(response: Response,
                 origin_header: str | None = Header(default=None, alias="Origin"),
                 handle: str | None = Cookie(default=None, alias=COOKIE),
                 csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> SessionStatus:
        private(response)
        same_origin(origin_header)
        if not handle:
            raise HTTPException(status_code=401, detail="Session unavailable", headers=NO_STORE)
        require_csrf(handle, csrf_header)
        try:
            return status(store.renew(handle), handle)
        except SessionUnavailable:
            raise HTTPException(status_code=401, detail="Session unavailable",
                                headers=NO_STORE) from None

    @router.delete("/current", status_code=204)
    def end(response: Response,
            origin_header: str | None = Header(default=None, alias="Origin"),
            handle: str | None = Cookie(default=None, alias=COOKIE),
            csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
        private(response)
        same_origin(origin_header)
        if not handle:
            raise HTTPException(status_code=401, detail="Session unavailable", headers=NO_STORE)
        require_csrf(handle, csrf_header)
        try:
            store.revoke(handle)
        except SessionUnavailable:
            raise HTTPException(status_code=401, detail="Session unavailable",
                                headers=NO_STORE) from None
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True,
                               samesite="lax")

    return router


__all__ = ["SessionStatus", "sessions_router"]
