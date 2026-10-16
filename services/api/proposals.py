"""Owner-checked immutable hypothetical proposal command route."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Cookie, Header, Response

from services.api.review import COMMAND_ERRORS, VersionHttp
from services.api.sessions import COOKIE


def proposals_router(http: VersionHttp) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/proposals")

    @router.put("/{proposal_id}")
    def save(workspace_id: str, proposal_id: str, body: dict[str, Any], response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE),
             request_origin: str | None = Header(default=None, alias="Origin"),
             csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
             if_match: str | None = Header(default=None, alias="If-Match"),
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.save_proposal(actor, workspace_id, proposal_id,
                body, revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{proposal_id}")
    def read(workspace_id: str, proposal_id: str, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.read(http.owner(workspace_id, handle),
                                           workspace_id, "proposals", proposal_id))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{proposal_id}/history")
    def history(workspace_id: str, proposal_id: str, response: Response,
                after_revision: int = 0, limit: int = 20,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            items = http.service.store.history(http.owner(workspace_id, handle),
                workspace_id, "proposals", proposal_id,
                after_revision=after_revision, limit=limit)
            return {"items": items, "next_after_revision": items[-1]["revision"] if items else None}
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    return router


__all__ = ["proposals_router"]
