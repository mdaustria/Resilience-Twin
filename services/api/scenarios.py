"""Owner-checked immutable scenario command route."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Cookie, Header, Response
from pydantic import BaseModel

from packages.adapters.persistence.firestore import AccessDenied
from packages.application.documents import ObjectMissing, PrivateDocuments
from packages.contracts.scenarios import Scenario, ScenarioEvent
from packages.domain.scenarios import validate_scenario
from services.api.review import COMMAND_ERRORS, Problem, VersionHttp
from services.api.sessions import COOKIE


class ScenarioTargets(BaseModel):
    baseline_hash: str
    edge_ids: tuple[str, ...]
    asset_ids: tuple[str, ...]
    vehicle_ids: tuple[str, ...]
    shelter_ids: tuple[str, ...]


def scenarios_router(http: VersionHttp, documents: PrivateDocuments | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/scenarios")

    def targets(workspace_id: str, handle: str | None) -> ScenarioTargets:
        if documents is None:
            raise Problem(503, "targets_unavailable", "Private graph store unavailable")
        actor = http.owner(workspace_id, handle)
        try:
            baseline = http.service.store.read(actor, workspace_id, "baselines", "main")
            content = baseline["content"]
            artifact = documents.repository.get_record(actor, workspace_id, "artifacts",
                                                       content["graph_artifact_id"])
            raw = documents.objects.read_all(artifact["object_key"], artifact["generation"])
            if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                raise ValueError("Compiled graph hash differs from immutable artifact")
            graph = json.loads(raw)
            edges = graph["edges"]
            resources = content["resources"]
            return ScenarioTargets(
                baseline_hash=content["baseline_hash"],
                edge_ids=tuple(sorted(edge["id"] for edge in edges)),
                asset_ids=tuple(sorted({edge["asset_id"] for edge in edges
                                        if edge.get("asset_id")})),
                vehicle_ids=tuple(sorted(item[0] for item in resources["vehicle_starts"])),
                shelter_ids=tuple(sorted(resources["shelter_ids"])),
            )
        except AccessDenied:
            raise Problem(404, "baseline_unavailable", "Sealed baseline unavailable") from None
        except (KeyError, ValueError, ObjectMissing, json.JSONDecodeError) as exc:
            raise Problem(422, "invalid_resource", str(exc)) from None

    @router.get("/targets", response_model=ScenarioTargets)
    def read_targets(workspace_id: str, response: Response,
                     handle: str | None = Cookie(default=None, alias=COOKIE)) -> ScenarioTargets:
        http.private(response)
        return targets(workspace_id, handle)

    def validate_editor(body: dict[str, Any], scenario_id: str,
                        allowed: ScenarioTargets) -> None:
        try:
            if body.get("schema_version") != "scenario.editor.v1":
                raise ValueError("Structured scenario version is required")
            if body.get("baseline_hash") != allowed.baseline_hash:
                raise ValueError("Baseline resource identity changed")
            horizon = body["horizon_seconds"]
            deadline = body["deadline_seconds"]
            demand = body["demand_people"]
            if (type(horizon) is not int or not 1 <= horizon <= 259_200 or
                    type(deadline) is not int or not 1 <= deadline <= horizon or
                    type(demand) is not int or not 1 <= demand <= 1_000_000):
                raise ValueError("Demand, deadline or horizon interval is invalid")
            started = datetime.fromisoformat(body["scenario_start_utc"])
            if started.tzinfo is None or started.utcoffset() != timedelta(0):
                raise ValueError("Scenario start requires UTC time")
            events = tuple(ScenarioEvent(**item) for item in body["events"])
            scenario = Scenario(scenario_id, horizon, events)
            if any(event.known_seconds > horizon for event in events):
                raise ValueError("Known-time interval exceeds the horizon")
            validate_scenario(scenario, edge_ids=frozenset(allowed.edge_ids),
                asset_ids=frozenset(allowed.asset_ids),
                vehicle_ids=frozenset(allowed.vehicle_ids),
                shelter_ids=frozenset(allowed.shelter_ids))
            ids = {event.id for event in events}
            for name in ("power_event_id", "communication_event_id"):
                linked = body.get(name)
                if linked is not None and linked not in ids:
                    raise ValueError(f"{name} must identify an explicit operational event")
            if (not isinstance(body.get("assumption_notes"), list)
                    or not all(isinstance(item, str) and item.strip()
                               for item in body["assumption_notes"])):
                raise ValueError("Scenario assumption notes are required")
            if not isinstance(body.get("scenario_title"), str) or not body["scenario_title"].strip():
                raise ValueError("Scenario title is required")
        except (AttributeError, KeyError, TypeError) as exc:
            raise Problem(422, "invalid_scenario", f"Missing or malformed {exc}") from None
        except ValueError as exc:
            label = str(exc)
            code = ("invalid_target" if "target" in label else
                    "invalid_interval" if "interval" in label or "horizon" in label else
                    "invalid_resource" if "resource" in label or "Baseline" in label else
                    "invalid_scenario")
            raise Problem(422, code, label) from None

    @router.put("/{scenario_id}")
    def save(workspace_id: str, scenario_id: str, body: dict[str, Any], response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE),
             request_origin: str | None = Header(default=None, alias="Origin"),
             csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
             if_match: str | None = Header(default=None, alias="If-Match"),
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        if documents is not None:
            validate_editor(body, scenario_id, targets(workspace_id, handle))
        try:
            return http.service.save_scenario(actor, workspace_id, scenario_id,
                body, revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{scenario_id}")
    def read(workspace_id: str, scenario_id: str, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.read(http.owner(workspace_id, handle),
                                           workspace_id, "scenarios", scenario_id))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{scenario_id}/history")
    def history(workspace_id: str, scenario_id: str, response: Response,
                after_revision: int = 0, limit: int = 20,
                handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            items = http.service.store.history(http.owner(workspace_id, handle),
                workspace_id, "scenarios", scenario_id,
                after_revision=after_revision, limit=limit)
            return {"items": items, "next_after_revision": items[-1]["revision"] if items else None}
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    return router


def scenario_suites_router(http: VersionHttp) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/scenario-suites")

    @router.put("/{suite_id}")
    def seal(workspace_id: str, suite_id: str, body: dict[str, Any], response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE),
             request_origin: str | None = Header(default=None, alias="Origin"),
             csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
             if_match: str | None = Header(default=None, alias="If-Match"),
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        http.private(response)
        actor, revision, key = http.mutation(workspace_id, handle, request_origin,
                                             csrf, if_match, idempotency_key)
        try:
            return http.service.seal_scenario_suite(actor, workspace_id, suite_id, body,
                                                     revision=revision, key=key)
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    @router.get("/{suite_id}")
    def read(workspace_id: str, suite_id: str, response: Response,
             handle: str | None = Cookie(default=None, alias=COOKIE)) -> dict[str, Any]:
        http.private(response)
        try:
            return cast(dict[str, Any], http.service.store.read(http.owner(workspace_id, handle),
                                           workspace_id, "scenario_suites", suite_id))
        except COMMAND_ERRORS as exc:
            raise http.translate(exc) from None

    return router


__all__ = ["scenario_suites_router", "scenarios_router"]
