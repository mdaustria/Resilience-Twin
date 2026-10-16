"""Owner-checked artifact download proxy."""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from packages.adapters.persistence.firestore import AccessDenied, Actor
from packages.application.documents import PrivateDocuments
from packages.application.sessions import SessionUnavailable
from packages.contracts.documents import DocumentPage
from services.api.documents import OwnerResolver
from services.api.sessions import COOKIE, NO_STORE


class ArtifactCoverage(BaseModel):
    artifact_id: str
    sha256: str
    physical_page_count: int
    pages: tuple[DocumentPage, ...]
    review_basis: str


_EVIDENCE = Path(__file__).resolve().parents[2] / "release/validation/extraction"


@lru_cache(maxsize=2)
def _verified_pilot_pages(digest: str, count: int) -> tuple[DocumentPage, ...] | None:
    """Replay checked extraction coverage only for the two exact public source identities."""
    manifest = json.loads((_EVIDENCE / "verification.json").read_text(encoding="utf-8"))
    case = next((name for name, source in manifest["sources"].items()
                 if source["document_sha256"] == digest), None)
    if case is None:
        return None
    source = manifest["sources"][case]
    if (source["physical_pages_covered"] != count or source["failed_regions"]
            or source["unresolved_regions"]):
        raise ValueError("Verified extraction does not cover the uploaded source")
    methods: dict[int, set[str]] = {}
    for batch_path in sorted((_EVIDENCE / "batches").glob(f"{case}-p*-v11.json")):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if (batch["document_sha256"] != digest or
                source["raw_response_sha256"].get(batch_path.stem) != batch["raw_sha256"]):
            raise ValueError("Verified extraction group differs from its manifest")
        for region in batch["coverage"]:
            page = region["physical_page"]
            if region["status"] != "processed" or not 1 <= page <= count:
                raise ValueError("Pilot extraction contains unresolved or invalid regions")
            methods.setdefault(page, set()).add(region["method"])
    if set(methods) != set(range(1, count + 1)):
        raise ValueError("Verified extraction has missing or extra physical pages")
    pages: list[DocumentPage] = []
    for page in range(1, count + 1):
        method: Literal["text", "visual", "mixed"] = (
            "mixed" if len(methods[page]) > 1 else
            "visual" if "visual" in methods[page] else "text")
        pages.append(DocumentPage(physical_page=page, coverage_status="processed",
                                  extraction_method=method, recovery_reason=""))
    return tuple(pages)


def artifacts_router(documents: PrivateDocuments, owner_for: OwnerResolver) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/artifacts")

    @router.get("/{artifact_id}/coverage", response_model=ArtifactCoverage)
    def coverage(workspace_id: str, artifact_id: str, response: Response,
                 handle: str | None = Cookie(default=None, alias=COOKIE)) -> ArtifactCoverage:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Origin, Cookie"
        if not handle:
            raise HTTPException(401, "Session unavailable", headers=NO_STORE)
        try:
            actor = owner_for(handle, workspace_id)[0]
            metadata = documents.repository.get_record(actor, workspace_id, "artifacts", artifact_id)
        except (AccessDenied, SessionUnavailable, ValueError):
            raise HTTPException(404, "Artifact unavailable", headers=NO_STORE) from None
        count = metadata.get("physical_page_count")
        if metadata.get("kind") != "source_pdf" or not isinstance(count, int) or count < 1:
            raise HTTPException(404, "PDF coverage unavailable", headers=NO_STORE)
        try:
            reviewed = _verified_pilot_pages(metadata["sha256"], count)
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            raise HTTPException(503, "Verified source coverage unavailable", headers=NO_STORE) from None
        return ArtifactCoverage(artifact_id=artifact_id, sha256=metadata["sha256"],
                                physical_page_count=count,
                                pages=reviewed or tuple(DocumentPage(physical_page=page)
                                                        for page in range(1, count + 1)),
                                review_basis=("Hash-bound, previously verified full-PDF extraction replay"
                                              if reviewed is not None else "Awaiting extraction or manual review"))

    @router.get("/{artifact_id}/download")
    def download(workspace_id: str, artifact_id: str,
                 handle: str | None = Cookie(default=None, alias=COOKIE)) -> StreamingResponse:
        if not handle:
            raise HTTPException(401, "Session unavailable", headers=NO_STORE)

        def authorize() -> Actor:
            try:
                return owner_for(handle, workspace_id)[0]
            except (AccessDenied, SessionUnavailable, ValueError):
                raise HTTPException(403, "Artifact access ended", headers=NO_STORE) from None

        # Execute the first authorization and metadata lookup before streaming headers.
        stream = documents.stream(authorize, workspace_id, artifact_id)
        try:
            first = next(stream)
        except StopIteration:
            first = b""
        except AccessDenied:
            raise HTTPException(404, "Artifact unavailable", headers=NO_STORE) from None

        def chunks() -> Iterator[bytes]:
            if first:
                current = authorize()
                documents.repository.get_workspace(current, workspace_id)
                yield first
            yield from stream

        return StreamingResponse(chunks(), media_type="application/pdf", headers={
            "Cache-Control": "private, no-store", "Vary": "Origin, Cookie",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment; filename=source.pdf",
        })

    return router


__all__ = ["artifacts_router"]
