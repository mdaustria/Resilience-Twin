"""Local pilot location review against two pinned OSM samples."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from packages.adapters.geo.compiler import (
    CompilePolicy,
    compile_small_import,
    route_compiled,
)
from packages.adapters.persistence.firestore import AccessDenied, Actor
from packages.application.documents import PrivateDocuments
from packages.application.review import ReviewService, pilot_review
from packages.domain.geography import AreaMember, Connector, StudyArea
from packages.domain.versions import RevisionConflict
from services.api.review import (
    COMMAND_ERRORS,
    DurableReviewRecord,
    VersionHttp,
)

PilotCase = Literal["qc", "guiguinto"]
ROOT = Path(__file__).resolve().parents[2]


class GeographySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: PilotCase
    area: StudyArea
    source_sha256: str
    graph_sha256: str
    graph_edge_count: int
    route_status: str
    route_seconds: int | None
    route_distance_mm: int | None
    scope_digest: str
    scope_id: str
    blockers: tuple[str, ...]


class GeographyReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    expected_scope_digest: str


class GeographyReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str
    review_revision: int
    scenario_reviewed: bool


def _distance_m(point: tuple[float, float], road: list[float]) -> int:
    lat1, lon1 = map(radians, point)
    lat2, lon2 = map(radians, road)
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return round(12_742_000 * asin(sqrt(h)))


def pilot_geography(case: PilotCase) -> GeographySnapshot:
    if case not in ("qc", "guiguinto"):
        raise ValueError("unknown pilot geography")
    name = "talayan" if case == "qc" else "guiguinto"
    path = ROOT / "release" / "validation" / "geography" / f"{name}-small.json"
    raw = path.read_bytes()
    sample = json.loads(raw)
    graph, record = compile_small_import(sample, CompilePolicy(30))
    if case == "qc":
        coords = ((14.6340, 121.0113), (14.6360, 121.0140))
        road_ids = ("13137612581", "39649824")
        labels = ("Talayan representative pickup anchor", "Illustrative Talayan shelter anchor")
        polygon = ((121.005, 14.629), (121.018, 14.629), (121.018, 14.638),
                   (121.005, 14.638), (121.005, 14.629))
        members = (
            AreaMember("talayan-pilot-cohort", "Talayan-centered scenario cohort", True, 100,
                       "Illustrative 100-person assumption; no city or barangay total is allocated"),
            AreaMember("rest-of-qc", "Rest of Quezon City", False, None,
                       "Outside this bounded pilot cell and cohort"),
        )
        area_id = "qc-talayan-pilot-cell"
        area_label = "Talayan-centered QC pilot cell"
    else:
        coords = ((14.8290, 120.8760), (14.82683, 120.87889))
        road_ids = ("5733371091", "9357839617")
        labels = ("Poblacion representative pickup anchor", "Approximate GMACC anchor")
        polygon = ((120.874, 14.823), (120.884, 14.823), (120.884, 14.832),
                   (120.874, 14.832), (120.874, 14.823))
        members = (
            AreaMember("poblacion-pilot-cohort", "Poblacion-centered scenario cohort", True, 100,
                       "Illustrative 100-person assumption; no municipal or barangay total is allocated"),
            AreaMember("rest-of-guiguinto", "Rest of Guiguinto", False, None,
                       "Outside this bounded pilot cell and cohort"),
        )
        area_id = "guiguinto-poblacion-pilot-cell"
        area_label = "Poblacion-centered Guiguinto pilot cell"
    connectors = tuple(
        Connector(f"{area_id}-{kind}", label, road_id,
                  _distance_m(point, sample["nodes"][road_id]), True, True,
                  "Manual exploratory coordinate and pinned OSM road proximity; physical access assumed",
                  point[1], point[0])
        for kind, label, point, road_id in zip(("pickup", "facility"), labels, coords, road_ids)
    )
    area = StudyArea(
        id=area_id, label=area_label, source="manual", boundary_lon_lat=polygon,
        members=members, connectors=connectors, routing_buffer_m=250,
        cross_boundary_assumptions=(
            "Only the named 100-person hypothetical cohort is modeled; no plan-wide population is allocated",
            "Neighboring facilities and populations are excluded; their availability and permission are unknown",
            "The rectangle is a modeling cell, not an administrative barangay boundary",
            "Road-node proximity is checked; physical connector access and shelter operability are assumptions",
        ), reviewer="local-operator-source-and-route-review-2026-10-14", revision=1,
    )
    route = route_compiled(graph, road_ids[0], road_ids[1])
    blockers = list(area.blockers())
    if route.status != "found" or route.boundary_edges:
        blockers.append("pickup-to-facility route unresolved or crosses source extent")
    graph_bytes = json.dumps({
        "edges": [asdict(edge) for edge in graph.edges],
        "restrictions": [asdict(restriction) for restriction in graph.restrictions],
    }, sort_keys=True, separators=(",", ":")).encode()
    graph_sha = hashlib.sha256(graph_bytes).hexdigest()
    scope_digest = hashlib.sha256((area.digest() + hashlib.sha256(raw).hexdigest()
                                   + graph_sha).encode()).hexdigest()
    return GeographySnapshot(
        case=case, area=area, source_sha256=record.source_sha256, graph_sha256=graph_sha,
        graph_edge_count=record.edge_count, route_status=route.status,
        route_seconds=route.travel_seconds, route_distance_mm=route.distance_mm,
        scope_digest=scope_digest, scope_id=f"{area.id}:{scope_digest[:16]}", blockers=tuple(blockers),
    )


def geography_router(review_service: ReviewService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/local/geography", tags=["local-geography"])

    @router.get("/{case}", response_model=GeographySnapshot)
    def read_geography(case: PilotCase) -> GeographySnapshot:
        return pilot_geography(case)

    @router.post("/{case}/review", response_model=GeographyReviewResult)
    def review_geography(case: PilotCase, command: GeographyReviewCommand,
                         x_fixture_owner: str = Header()) -> GeographyReviewResult:
        current = pilot_geography(case)
        if current.blockers or command.expected_scope_digest != current.scope_digest:
            raise HTTPException(status_code=422, detail="Geography changed or has unresolved connectors")
        try:
            draft, _ = review_service.confirm_geography(
                x_fixture_owner, command.expected_revision, current.scope_id, case)
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="Review changed; reload before editing") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return GeographyReviewResult(scope_id=draft.scope_id, review_revision=draft.revision,
                                     scenario_reviewed=draft.scenario_reviewed)

    @router.get("/{case}/suggestions")
    def suggestions(case: PilotCase, text: str) -> dict[str, object]:
        from packages.adapters.geo.geocoding import suggest_locations

        if len(text) < 3 or len(text) > 100:
            raise HTTPException(status_code=422, detail="Use 3–100 characters")
        key = os.environ.get("GEOAPIFY_API_KEY")
        if not key:
            return {"available": False, "suggestions": [],
                    "reason": "Geoapify key is unavailable; use the reviewed manual pilot area"}
        try:
            found = suggest_locations(f"{text}, Philippines", key)
        except (ValueError, OSError, TimeoutError):
            raise HTTPException(status_code=503, detail="Geoapify suggestions unavailable") from None
        return {"available": True, "suggestions": [asdict(item) for item in found],
                "reason": "Suggestions require manual location and connector review"}

    return router


class PrivatePilotLocation(BaseModel):
    snapshot: GeographySnapshot
    graph_artifact_id: str


class ConfirmPrivateLocation(BaseModel):
    expected_scope_digest: str


class ConfirmedPrivateLocation(BaseModel):
    snapshot: GeographySnapshot
    graph_artifact_id: str
    review: DurableReviewRecord


def private_pilot_geography_router(http: VersionHttp, documents: PrivateDocuments) -> APIRouter:
    """Bind a hash-matched uploaded pilot to its reviewed OSM cell and graph."""
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/geography/pilot")

    def matching(workspace_id: str, case: PilotCase, handle: str | None) -> tuple[Actor, GeographySnapshot]:
        actor = http.owner(workspace_id, handle)
        review = http.service.store.read(actor, workspace_id, "reviews", "main")
        sources = review["content"]["draft"]["sources"]
        expected = pilot_review("uploaded", case).sources[0].sha256
        if len(sources) != 1 or sources[0]["sha256"] != expected:
            raise HTTPException(404, "Pilot geography does not match the private source")
        return actor, pilot_geography(case)

    @router.get("/{case}", response_model=PrivatePilotLocation)
    def read_pilot(workspace_id: str, case: PilotCase, response: Response,
                   handle: str | None = Cookie(default=None, alias="__session")) -> PrivatePilotLocation:
        http.private(response)
        try:
            _, snapshot = matching(workspace_id, case, handle)
        except (AccessDenied, KeyError, ValueError):
            raise HTTPException(404, "Pilot geography unavailable") from None
        return PrivatePilotLocation(snapshot=snapshot,
            graph_artifact_id=f"pilot-graph-{case}-{snapshot.scope_digest[:16]}")

    @router.post("/{case}/confirm", response_model=ConfirmedPrivateLocation)
    def confirm(workspace_id: str, case: PilotCase, body: ConfirmPrivateLocation,
                response: Response,
                handle: str | None = Cookie(default=None, alias="__session"),
                request_origin: str | None = Header(default=None, alias="Origin"),
                csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
                if_match: str | None = Header(default=None, alias="If-Match"),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> ConfirmedPrivateLocation:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        _, snapshot = matching(workspace_id, case, handle)
        if snapshot.blockers or body.expected_scope_digest != snapshot.scope_digest:
            raise HTTPException(422, "Pinned geography changed or has unresolved connectors")
        graph_id = f"pilot-graph-{case}-{snapshot.scope_digest[:16]}"
        try:
            documents.repository.get_record(actor, workspace_id, "artifacts", graph_id)
        except AccessDenied:
            name = "talayan" if case == "qc" else "guiguinto"
            sample = json.loads((ROOT / "release/validation/geography" /
                                 f"{name}-small.json").read_text(encoding="utf-8"))
            graph, _ = compile_small_import(sample, CompilePolicy(30))
            data = json.dumps({"edges": [asdict(edge) for edge in graph.edges],
                               "restrictions": [asdict(item) for item in graph.restrictions]},
                              sort_keys=True, separators=(",", ":")).encode()
            if hashlib.sha256(data).hexdigest() != snapshot.graph_sha256:
                raise HTTPException(503, "Pinned graph identity changed")
            object_key = f"workspaces/{workspace_id}/graphs/{graph_id}-{uuid.uuid4().hex}.json"
            stored = documents.objects.write_once(object_key, data)
            try:
                workspace = documents.repository.get_workspace(actor, workspace_id)
                documents.repository.put_artifact(actor, workspace_id, graph_id,
                    sha256=stored.sha256, object_key=stored.key,
                    generation=stored.generation, byte_count=stored.byte_count,
                    kind="compiled_graph", expected_revision=workspace["revision"])
            except BaseException:
                documents.objects.delete(object_key, stored.generation)
                raise
        try:
            reviewed = http.service.confirm_pilot_location(actor, workspace_id, "main",
                source_sha256=pilot_review("uploaded", case).sources[0].sha256,
                scope_id=snapshot.scope_id, revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None
        return ConfirmedPrivateLocation(snapshot=snapshot, graph_artifact_id=graph_id,
                                        review=DurableReviewRecord.model_validate(reviewed))

    return router


__all__ = ["GeographySnapshot", "geography_router", "pilot_geography",
           "private_pilot_geography_router"]
