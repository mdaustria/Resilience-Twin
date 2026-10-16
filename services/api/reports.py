"""Owner-checked durable report commands and revocable PDF downloads."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Cookie, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import AccessDenied, Conflict
from packages.adapters.persistence.jobs import LifetimeTooShort, UsageExceeded
from packages.application.comparisons import PrivateComparisons
from packages.application.documents import PrivateDocuments
from packages.application.jobs import JobSubmission
from packages.application.reports.private import build_report_spec
from packages.application.usage import stage_budget
from services.api.documents import OwnerResolver
from services.api.review import Problem
from services.api.sessions import COOKIE


class ReportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_job_ids: list[str] = Field(default_factory=list, max_length=50)
    variant_job_ids: list[str] = Field(default_factory=list, max_length=50)


def reports_router(versions: FirestoreVersionCommands, jobs: JobSubmission,
                   documents: PrivateDocuments, comparisons: PrivateComparisons,
                   owner_for: OwnerResolver, *, origin: str, csrf_key: bytes) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/reports")

    def actor(workspace_id: str, handle: str | None) -> Any:
        if not handle:
            raise Problem(401, "session_unavailable", "Session unavailable")
        try:
            return owner_for(handle, workspace_id)[0]
        except (AccessDenied, ValueError):
            raise Problem(404, "workspace_unavailable", "Workspace unavailable") from None

    def report_job(workspace_id: str, handle: str | None, job_id: str) -> dict[str, Any]:
        try:
            job = jobs.store.read(actor(workspace_id, handle), workspace_id, job_id)
        except (AccessDenied, ValueError):
            raise Problem(404, "report_unavailable", "Report unavailable") from None
        if job.get("stage") != "report":
            raise Problem(404, "report_unavailable", "Report unavailable")
        return job

    @router.post("/{kind}", status_code=202)
    def submit(workspace_id: str, kind: str, body: ReportCommand,
               response: Response, handle: str | None = Cookie(default=None, alias=COOKIE),
               request_origin: str | None = Header(default=None, alias="Origin"),
               csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
               key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, str]:
        response.headers["Cache-Control"] = "private, no-store"
        if request_origin != origin or not handle or not csrf or not hmac.compare_digest(
            csrf, hmac.new(csrf_key, handle.encode(), hashlib.sha256).hexdigest()
        ):
            raise Problem(403, "invalid_csrf", "Invalid report authority")
        if not key:
            raise Problem(400, "idempotency_required", "Idempotency-Key required")
        current = actor(workspace_id, handle)
        try:
            review = versions.read(current, workspace_id, "reviews", "main")
            proposal = (versions.read(current, workspace_id, "proposals", "main")
                        if kind in {"findings", "revision"} else None)
            comparison = (comparisons.evaluate(current, workspace_id, "main",
                body.baseline_job_ids, body.variant_job_ids)
                if kind == "findings" or (kind == "revision" and body.baseline_job_ids) else None)
            spec = build_report_spec(review, kind=kind, proposal=proposal,
                                     comparison=comparison)
            source_id = next(source["source_id"] for source in review["content"]["draft"]["sources"]
                             if source["role"] == "primary")
            metadata = documents.repository.get_record(current, workspace_id, "artifacts", source_id)
            if metadata.get("sha256") != spec.source_sha256 or metadata.get("kind") != "source_pdf":
                raise ValueError("Source artifact differs from reviewed source")
            content = {"spec": asdict(spec), "source_artifact_id": source_id}
            digest = hashlib.sha256(json.dumps(content, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            report_id = digest[:40]
            try:
                version = versions.commit(current, workspace_id, "reports", report_id,
                    expected_revision=0, idempotency_key=key, route="report.snapshot",
                    content=content, seal=True, immutable=True)
            except Conflict:
                version = versions.read(current, workspace_id, "reports", report_id)
                if version["content"] != content:
                    raise
            units, seconds = stage_budget("report")
            result = jobs.submit(current, workspace_id, route="reports/submit",
                idempotency_key=key, stage="report", input_hash=version["content_hash"],
                estimated_units=units, required_seconds=seconds)
            return {"report_id": report_id, "job_id": result["job_id"],
                    "status": result["status"], "kind": kind}
        except AccessDenied:
            raise Problem(404, "report_input_unavailable", "Report input unavailable") from None
        except Conflict:
            raise Problem(409, "report_conflict", "Report command conflict") from None
        except LifetimeTooShort:
            raise Problem(409, "temporary_lifetime", "Session expires too soon") from None
        except UsageExceeded:
            raise Problem(429, "usage_exceeded", "Usage reservation exceeded") from None
        except (ValueError, KeyError, TypeError):
            raise Problem(422, "invalid_report", "Report inputs are invalid") from None

    @router.get("/jobs/{job_id}")
    def status(workspace_id: str, job_id: str, response: Response,
               handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, str]:
        response.headers["Cache-Control"] = "private, no-store"
        job = report_job(workspace_id, handle, job_id)
        return {"job_id": job_id, "status": job["status"],
                "result_hash": job.get("result_hash") or ""}

    @router.get("/jobs/{job_id}/download")
    def download(workspace_id: str, job_id: str,
                 handle: str | None = Cookie(default=None, alias=COOKIE)) -> StreamingResponse:
        job = report_job(workspace_id, handle, job_id)
        key, generation, size = (job.get("artifact_key"), job.get("artifact_generation"),
                                 job.get("artifact_byte_count"))
        if (job.get("status") != "complete" or not isinstance(key, str)
                or not key.startswith(f"workspaces/{workspace_id}/reports/")
                or not isinstance(generation, int) or not isinstance(size, int) or size < 1):
            raise Problem(404, "report_unavailable", "Report unavailable")

        def chunks() -> Iterator[bytes]:
            for start in range(0, size, 65536):
                report_job(workspace_id, handle, job_id)
                piece = documents.objects.read_range(key, generation, start,
                                                     min(65536, size - start))
                if len(piece) != min(65536, size - start):
                    raise ValueError("Report object is incomplete")
                report_job(workspace_id, handle, job_id)
                yield piece

        stream = chunks()
        first = next(stream)

        def verified() -> Iterator[bytes]:
            report_job(workspace_id, handle, job_id)
            yield first
            yield from stream

        return StreamingResponse(verified(), media_type="application/pdf", headers={
            "Cache-Control": "private, no-store", "Vary": "Origin, Cookie",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment; filename=independent-analysis.pdf",
        })

    return router


__all__ = ["ReportCommand", "reports_router"]
