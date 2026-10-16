"""Validate review, scenario and hypothetical proposal commands before persistence."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import date
from typing import Any, cast

from packages.contracts.checkpoints import canonical_json
from packages.contracts.scenarios import (
    Scenario,
    ScenarioEvent,
    ScenarioSuite,
    SuiteMember,
)
from packages.domain.evidence import ReviewDraft, ReviewSource
from packages.domain.proposals import (
    AddVehicle,
    AddWater,
    BaselineResources,
    DeferredOperation,
    MoveVehicleStart,
    RedistributeWater,
    ShelterPreference,
    apply_variant,
)
from packages.domain.readiness import evaluate
from packages.domain.scenarios import suite_hash
from packages.domain.versions import RevisionConflict, acknowledge, seal

_OPERATIONS = {
    "redistribute_water": RedistributeWater,
    "add_water": AddWater,
    "move_vehicle_start": MoveVehicleStart,
    "shelter_preference": ShelterPreference,
    "add_vehicle": AddVehicle,
    "deferred": DeferredOperation,
}


class DurableVersions:
    def __init__(self, store: Any) -> None:
        self.store = store

    def initialize_review(self, actor: Any, workspace_id: str, review_id: str,
                          artifact_id: str, *, title: str, publication_reference: str,
                          textual_location: str, scenario_date: date,
                          revision: int, key: str) -> dict[str, Any]:
        """Bind a newly uploaded immutable PDF to a source-only review."""
        from packages.application.review import pilot_review

        artifact = self.store.repository.get_record(actor, workspace_id, "artifacts", artifact_id)
        pages = artifact.get("physical_page_count")
        if artifact.get("kind") != "source_pdf" or not isinstance(pages, int) or not 1 <= pages <= 200:
            raise ValueError("A finalized PDF with full page count is required")
        if not title.strip() or not publication_reference.strip() or not textual_location.strip():
            raise ValueError("Source title, publication reference and textual location are required")
        reference = pilot_review("uploaded", "qc")
        known = None
        for case in ("qc", "guiguinto"):
            candidate = pilot_review("uploaded", case)
            if artifact["sha256"] == candidate.sources[0].sha256:
                if pages != candidate.sources[0].physical_page_count:
                    raise ValueError("Source page count differs from reviewed source")
                known = candidate
                break
        scope = f"pending location: {textual_location.strip()}"
        source = ReviewSource(source_id=artifact_id, title=title.strip(),
                              sha256=artifact["sha256"], physical_page_count=pages,
                              role="primary", publication_reference=publication_reference.strip())
        template = known or reference
        draft = ReviewDraft(workspace_id=workspace_id, revision=revision,
                            sources=(source,),
                            claims=tuple(claim.model_copy(update={"source_id": artifact_id,
                                                          "scope_id": scope})
                                         for claim in known.claims) if known else (),
                            assumptions=(), required_fields=reference.required_fields,
                            scope_id=scope, scenario_date=scenario_date,
                            scenario_reviewed=False,
                            pending_annexes=template.pending_annexes,
                            unsupported_procedures=template.unsupported_procedures)
        return self.save_review(actor, workspace_id, review_id, draft, revision=revision, key=key)

    def save_review(self, actor: Any, workspace_id: str, review_id: str,
                    draft: ReviewDraft, *, revision: int, key: str,
                    location_change: bool = False) -> dict[str, Any]:
        if draft.workspace_id != workspace_id:
            raise ValueError("Review workspace differs from owner workspace")
        if revision:
            previous = self.store.read(actor, workspace_id, "reviews", review_id)
            prior = ReviewDraft.model_validate(previous["content"]["draft"])
            if draft.sources != prior.sources or draft.required_fields != prior.required_fields:
                raise ValueError("Review sources and required fields cannot be rewritten")
            if not location_change and (draft.scope_id != prior.scope_id or
                                        draft.scenario_reviewed != prior.scenario_reviewed):
                raise ValueError("Use the reviewed geography command to change scope")
        for source in draft.sources:
            metadata = self.store.repository.get_record(actor, workspace_id,
                                                        "artifacts", source.source_id)
            if metadata.get("sha256") != source.sha256:
                raise ValueError("Review source hash differs from immutable artifact")
        clean = ReviewDraft.model_validate(draft.model_copy(update={
            "revision": revision + 1, "sealed_hash": None,
            "acknowledged_hash": None}).model_dump())
        content = {"draft": clean.model_dump(mode="json"),
                   "readiness": evaluate(clean).model_dump(mode="json")}
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "reviews", review_id,
            expected_revision=revision, idempotency_key=key, route="review.save",
            content=content))

    def confirm_pilot_location(self, actor: Any, workspace_id: str, review_id: str,
                               *, source_sha256: str, scope_id: str,
                               revision: int, key: str) -> dict[str, Any]:
        current = self.store.read(actor, workspace_id, "reviews", review_id)
        if current["revision"] != revision:
            raise RevisionConflict("Review changed before location confirmation")
        draft = ReviewDraft.model_validate(current["content"]["draft"])
        if (len(draft.sources) != 1 or draft.sources[0].sha256 != source_sha256
                or draft.scenario_reviewed or not scope_id):
            raise ValueError("Location does not match the uploaded source or was already reviewed")
        reviewed = draft.model_copy(update={"scope_id": scope_id,
                                    "scenario_reviewed": True, "assumptions": ()})
        return self.save_review(actor, workspace_id, review_id, reviewed,
                                revision=revision, key=key, location_change=True)

    def seal_review(self, actor: Any, workspace_id: str, review_id: str,
                    *, revision: int, key: str) -> dict[str, Any]:
        prior = self.store.replay(actor, workspace_id, "reviews", review_id,
            expected_revision=revision, idempotency_key=key, route="review.seal")
        if prior is not None:
            return cast(dict[str, Any], prior)
        current = self.store.read(actor, workspace_id, "reviews", review_id)
        if current["revision"] != revision:
            raise RevisionConflict("Stale review revision")
        draft = ReviewDraft.model_validate(current["content"]["draft"])
        sealed = seal(draft, revision)
        content = {"draft": sealed.model_dump(mode="json"),
                   "readiness": evaluate(sealed).model_dump(mode="json")}
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "reviews", review_id,
            expected_revision=revision, idempotency_key=key, route="review.seal",
            content=content, seal=True))

    def acknowledge_review(self, actor: Any, workspace_id: str, review_id: str,
                           *, revision: int, key: str) -> dict[str, Any]:
        prior = self.store.replay(actor, workspace_id, "reviews", review_id,
            expected_revision=revision, idempotency_key=key, route="review.acknowledge")
        if prior is not None:
            return cast(dict[str, Any], prior)
        current = self.store.read(actor, workspace_id, "reviews", review_id)
        if current["revision"] != revision:
            raise RevisionConflict("Stale review revision")
        draft = ReviewDraft.model_validate(current["content"]["draft"])
        if not evaluate(draft).computable or not draft.scenario_reviewed:
            raise ValueError("Resolve run inputs and review the scenario first")
        acknowledged = acknowledge(draft, revision)
        content = {"draft": acknowledged.model_dump(mode="json"),
                   "readiness": evaluate(acknowledged).model_dump(mode="json")}
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "reviews", review_id,
            expected_revision=revision, idempotency_key=key, route="review.acknowledge",
            content=content, seal=True))

    def seal_baseline(self, actor: Any, workspace_id: str, baseline_id: str,
                      body: dict[str, Any], *, revision: int, key: str) -> dict[str, Any]:
        review_id = str(body["review_id"])
        review_revision = int(body["review_revision"])
        graph_artifact_id = str(body["graph_artifact_id"])
        review = self.store.version(actor, workspace_id, "reviews", review_id, review_revision)
        if not review["sealed"] or not review["content"]["readiness"]["ready_to_run"]:
            raise ValueError("A sealed, acknowledged and computable review is required")
        graph = self.store.repository.get_record(actor, workspace_id, "artifacts", graph_artifact_id)
        if graph["kind"] != "compiled_graph":
            raise ValueError("Baseline requires an immutable compiled graph artifact")
        draft = ReviewDraft.model_validate(review["content"]["draft"])
        sources = tuple(sorted((source.source_id, source.sha256) for source in draft.sources))
        raw_resources = body["resources"]
        base_material = {"review_hash": review["content_hash"], "graph_hash": graph["sha256"],
                         "sources": sources, "resources": raw_resources}
        baseline_hash = hashlib.sha256(canonical_json(base_material)).hexdigest()
        resources = BaselineResources(baseline_hash=baseline_hash,
            source_hashes=tuple(value for _, value in sources), **raw_resources)
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "baselines", baseline_id,
            expected_revision=revision, idempotency_key=key, route="baseline.seal",
            content={"review_id": review_id, "review_revision": review_revision,
                     "review_hash": review["content_hash"],
                     "graph_artifact_id": graph_artifact_id, "graph_hash": graph["sha256"],
                     "source_ids": [name for name, _ in sources],
                     "resources": asdict(resources), "baseline_hash": baseline_hash},
            seal=True, immutable=True))

    def _baseline(self, actor: Any, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        baseline = self.store.read(actor, workspace_id, "baselines", str(body["baseline_id"]))
        if not baseline["sealed"] or baseline["content"]["baseline_hash"] != body["baseline_hash"]:
            raise ValueError("Sealed baseline hash differs from command")
        return cast(dict[str, Any], baseline)

    def save_scenario(self, actor: Any, workspace_id: str, scenario_id: str,
                      body: dict[str, Any], *, revision: int, key: str) -> dict[str, Any]:
        baseline = self._baseline(actor, workspace_id, body)
        events = tuple(ScenarioEvent(**event) for event in body["events"])
        if any(event.effect not in ("edge_closed", "asset_closed", "vehicle_outage",
                                    "shelter_capacity") for event in events):
            raise ValueError("Unknown scenario effect")
        scenario = Scenario(id=scenario_id, horizon_seconds=body["horizon_seconds"],
                            events=events)
        editor = ({name: body[name] for name in (
            "schema_version", "scenario_start_utc", "demand_people", "deadline_seconds",
            "power_event_id", "communication_event_id", "assumption_notes",
            "scenario_title")}
            if body.get("schema_version") == "scenario.editor.v1" else None)
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "scenarios", scenario_id,
            expected_revision=revision, idempotency_key=key, route="scenario.save",
            content={"baseline_id": body["baseline_id"],
                     "baseline_hash": baseline["content"]["baseline_hash"],
                     "scenario": asdict(scenario), "editor": editor}, seal=True, immutable=True))

    def seal_scenario_suite(self, actor: Any, workspace_id: str, suite_id: str,
                            body: dict[str, Any], *, revision: int, key: str) -> dict[str, Any]:
        ids = body["scenario_ids"]
        seed = body["seed"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 50
                or not all(isinstance(item, str) and item for item in ids)
                or len(set(ids)) != len(ids) or type(seed) is not int or seed < 0):
            raise ValueError("Suite requires 1–50 distinct scenario IDs and a nonnegative seed")
        records = [self.store.read(actor, workspace_id, "scenarios", item) for item in ids]
        if any(not item["sealed"] for item in records):
            raise ValueError("Suite members must be sealed scenarios")
        baselines = {item["content"]["baseline_hash"] for item in records}
        if len(baselines) != 1:
            raise ValueError("Suite scenarios must share one immutable baseline")
        members = []
        for scenario_id, record in zip(ids, records, strict=True):
            content = record["content"]["scenario"]
            events = tuple(ScenarioEvent(**item) for item in content["events"])
            members.append(SuiteMember(scenario_id, seed,
                Scenario(scenario_id, content["horizon_seconds"], events)))
        suite = ScenarioSuite(suite_id, "manual-selected-v1", tuple(members))
        return cast(dict[str, Any], self.store.commit(actor, workspace_id,
            "scenario_suites", suite_id, expected_revision=revision,
            idempotency_key=key, route="scenario_suite.seal",
            content={"baseline_hash": next(iter(baselines)),
                     "scenario_ids": ids,
                     "scenario_hashes": [item["content_hash"] for item in records],
                     "seed": seed, "generator_version": suite.generator_version,
                     "suite_hash": suite_hash(suite)}, seal=True, immutable=True))

    def save_proposal(self, actor: Any, workspace_id: str, proposal_id: str,
                      body: dict[str, Any], *, revision: int, key: str) -> dict[str, Any]:
        baseline_record = self._baseline(actor, workspace_id, body)
        baseline = BaselineResources(**baseline_record["content"]["resources"])
        operations = []
        for item in body["operations"]:
            operation_type = item["type"]
            implementation = _OPERATIONS.get(operation_type)
            if implementation is None:
                raise ValueError("Unknown proposal operation")
            operations.append(implementation(**{name: value for name, value in item.items()
                                                if name != "type"}))
        variant = apply_variant(baseline, tuple(operations))
        return cast(dict[str, Any], self.store.commit(actor, workspace_id, "proposals", proposal_id,
            expected_revision=revision, idempotency_key=key, route="proposal.save",
            content={"baseline_id": body["baseline_id"], "baseline": asdict(baseline),
                     "operations": body["operations"],
                     "variant": asdict(variant), "status": "untested"},
            seal=True, immutable=True))


__all__ = ["DurableVersions"]
