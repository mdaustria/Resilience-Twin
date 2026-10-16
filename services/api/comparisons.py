"""Owner-checked paired evaluation over worker-published run outcomes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Response
from pydantic import BaseModel, Field

from packages.adapters.persistence.firestore import AccessDenied
from packages.application.comparisons import PrivateComparisons
from services.api.documents import OwnerResolver
from services.api.review import Problem
from services.api.sessions import COOKIE


class EvaluatePair(BaseModel):
    baseline_job_ids: list[str] = Field(min_length=1, max_length=50)
    variant_job_ids: list[str] = Field(default_factory=list, max_length=50)


class ComparisonView(BaseModel):
    status: str
    reason: str | None = None
    measured_improvement: bool
    priority_label: str = "provisional"
    paired_member_ids: list[str] = Field(default_factory=list)
    excluded_member_ids: list[str] = Field(default_factory=list)
    deltas: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    planned_members: int
    completed_baseline_members: int
    operations: list[dict[str, Any]]
    variant: dict[str, Any]
    policy_version: str | None = None
    source_hashes: list[str] = Field(default_factory=list)
    baseline_hash: str | None = None
    variant_hash: str | None = None


def comparisons_router(service: PrivateComparisons,
                       owner_for: OwnerResolver) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/comparisons")

    @router.post("/{proposal_id}/evaluate", response_model=ComparisonView)
    def evaluate(workspace_id: str, proposal_id: str, body: EvaluatePair,
                 response: Response,
                 handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "private, no-store"
        if not handle:
            raise Problem(401, "session_unavailable", "Session unavailable")
        try:
            actor = owner_for(handle, workspace_id)[0]
            return service.evaluate(actor, workspace_id, proposal_id,
                                    body.baseline_job_ids, body.variant_job_ids)
        except AccessDenied:
            raise Problem(404, "comparison_unavailable", "Comparison inputs unavailable") from None
        except (ValueError, KeyError, TypeError):
            raise Problem(422, "invalid_pair", "Paired run inputs or pins differ") from None

    return router


__all__ = ["ComparisonView", "EvaluatePair", "comparisons_router"]
