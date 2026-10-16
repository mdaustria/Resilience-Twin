"""Owner-checked durable job submission and status endpoints."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable

from fastapi import APIRouter, Cookie, Header, Request, Response
from pydantic import BaseModel, ConfigDict

from packages.adapters.persistence.firestore import (
    AccessDenied,
    Conflict,
    InvalidRecord,
)
from packages.adapters.persistence.jobs import LifetimeTooShort, UsageExceeded
from packages.adapters.persistence.usage import BudgetExceeded, ChallengeRequired
from packages.application.jobs import JobSubmission
from packages.application.usage import network_bucket, stage_budget
from services.api.documents import OwnerResolver
from services.api.review import Problem
from services.api.sessions import COOKIE


class SubmitJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    input_hash: str


def jobs_router(service: JobSubmission, owner_for: OwnerResolver, *,
                origin: str, csrf_key: bytes,
                network_secret: bytes | None = None,
                challenge_verifier: Callable[[Request], bool] | None = None) -> APIRouter:
    if not origin.startswith("https://") or "/" in origin[8:] or len(csrf_key) < 32:
        raise ValueError("Jobs need HTTPS origin and CSRF secret")
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/jobs")

    @router.post("", status_code=202)
    def submit(workspace_id: str, body: SubmitJob, response: Response,
               request: Request,
               handle: str | None = Cookie(default=None, alias=COOKIE),
               request_origin: str | None = Header(default=None, alias="Origin"),
               csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
               key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, str]:
        response.headers["Cache-Control"] = "private, no-store"
        if request_origin != origin:
            raise Problem(403, "invalid_origin", "Invalid origin")
        if not handle or not csrf or not hmac.compare_digest(
            csrf, hmac.new(csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise Problem(403, "invalid_csrf", "Invalid CSRF token")
        if not key:
            raise Problem(400, "idempotency_required", "Idempotency-Key required")
        try:
            actor, _expiry = owner_for(handle, workspace_id)
            estimated_units, required_seconds = stage_budget(body.stage)
            network_key = (network_bucket(request.client.host, network_secret)
                           if network_secret is not None and request.client is not None else None)
            return service.submit(actor, workspace_id, route="jobs/submit",
                idempotency_key=key, network_key=network_key,
                challenge_satisfied=(challenge_verifier(request)
                                     if challenge_verifier is not None else False),
                stage=body.stage, input_hash=body.input_hash,
                estimated_units=estimated_units, required_seconds=required_seconds)
        except AccessDenied:
            raise Problem(404, "workspace_unavailable", "Workspace unavailable") from None
        except Conflict:
            raise Problem(409, "job_conflict", "Job command conflict") from None
        except LifetimeTooShort:
            raise Problem(409, "temporary_lifetime", "Temporary session expires too soon") from None
        except UsageExceeded:
            raise Problem(429, "usage_exceeded", "Usage reservation exceeded") from None
        except BudgetExceeded:
            raise Problem(429, "budget_exceeded", "Compute budget exhausted") from None
        except ChallengeRequired:
            raise Problem(429, "challenge_required", "Additional verification required") from None
        except InvalidRecord:
            raise Problem(422, "invalid_job", "Invalid job submission") from None
        except ValueError:
            raise Problem(422, "invalid_job", "Invalid processing stage") from None

    return router


__all__ = ["SubmitJob", "jobs_router"]
