"""Temporary workspace deletion with owner, origin and CSRF checks."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Cookie, Header, Response

from packages.adapters.persistence.firestore import AccessDenied
from packages.application.deletion import DeleteWorkspace
from packages.application.sessions import SessionUnavailable
from services.api.documents import OwnerResolver
from services.api.review import Problem
from services.api.sessions import COOKIE


def workspaces_router(service: DeleteWorkspace, owner_for: OwnerResolver, *,
                      origin: str, csrf_key: bytes) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces")

    @router.delete("/{workspace_id}", status_code=204)
    def delete(workspace_id: str, response: Response,
               handle: str | None = Cookie(default=None, alias=COOKIE),
               request_origin: str | None = Header(default=None, alias="Origin"),
               csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        if request_origin != origin or not handle or not csrf or not hmac.compare_digest(
            csrf, hmac.new(csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise Problem(403, "invalid_csrf", "Invalid mutation authority")
        try:
            owner_for(handle, workspace_id)
            service.delete(handle, workspace_id)
        except (AccessDenied, SessionUnavailable, ValueError):
            raise Problem(404, "workspace_unavailable", "Workspace unavailable") from None

    return router


__all__ = ["workspaces_router"]
