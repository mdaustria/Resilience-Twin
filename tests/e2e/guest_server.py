"""Local, emulator-backed guest API used by the Community Twin browser check."""

from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from google.cloud import firestore
from pydantic import BaseModel
from pypdf import PdfWriter

from packages.adapters.documents import ClamAvScanner, PypdfValidator
from packages.adapters.geo.compiler import CompilePolicy, compile_small_import
from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.runs import FirestoreRuns
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from packages.application.documents import PrivateDocuments
from packages.application.jobs import JobSubmission
from packages.application.reports.pilot import ENGINE_VERSION, run_pilot_proof
from packages.application.versions import DurableVersions
from packages.simulation.policies.deadline_greedy import POLICY_VERSION
from services.api.documents import session_owner_resolver
from services.api.geography import pilot_geography
from services.api.main import create_app
from services.worker.handlers import run_report_job
from services.worker.leases import FirestoreLeases

if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
    raise RuntimeError("The Community Twin browser API requires the Firestore emulator")

ROOT = Path(__file__).resolve().parents[2]
client = firestore.Client(project="demo-resilience-twin")
sessions = FirestoreTemporarySessions(client, issuance_check=lambda: True)
repository = FirestoreRepository(client)
scanner = ClamAvScanner(
    ROOT / ".runtime/clamav-1.5.4/clamav-1.5.4.win.x64/clamscan.exe",
    ROOT / ".runtime/clamav-db",
)
documents = PrivateDocuments(repository, MemoryObjectStore(), scanner,
                             PypdfValidator(), secret=b"guest-e2e-upload-secret-32-bytes!!")
app = create_app(local_fixture_mode=True, temporary_sessions=sessions,
                 private_documents=documents,
                 private_owner_for=session_owner_resolver(sessions, repository),
                 durable_versions=DurableVersions(FirestoreVersionCommands(client)),
                 durable_runs=FirestoreRuns(client),
                 job_submission=JobSubmission(FirestoreJobs(client)),
                 session_origin="https://resilience.example",
                 session_csrf_key=b"guest-e2e-session-secret-32-bytes!!")


class FixtureReport(BaseModel):
    workspace_id: str
    job_id: str


class FixtureReportSource(BaseModel):
    workspace_id: str


@app.post("/_fixture/report-expire")
def fixture_report_expire(body: FixtureReportSource) -> dict[str, str]:
    workspace = client.collection("workspaces").document(body.workspace_id).get().to_dict()
    if not workspace or workspace.get("owner_type") != "temporary":
        raise HTTPException(404, "Fixture workspace unavailable")
    client.collection("owners").document(
        f"temporary:{workspace['owner_id']}").update({
            "expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    return {"status": "expired"}


@app.post("/_fixture/report-source")
def fixture_report_source(body: FixtureReportSource) -> dict[str, str]:
    """Seed one fictional immutable PDF and an actual durable source-only review."""
    workspace = client.collection("workspaces").document(body.workspace_id).get().to_dict()
    if not workspace or workspace.get("owner_type") != "temporary":
        raise HTTPException(404, "Fixture workspace unavailable")
    actor = Actor("temporary", workspace["owner_id"])
    repository.get_workspace(actor, body.workspace_id)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    source = output.getvalue()
    stored = documents.objects.write_once(
        f"workspaces/{body.workspace_id}/documents/report-source.pdf", source)
    repository.put_artifact(actor, body.workspace_id, "report-source",
        sha256=stored.sha256, object_key=stored.key, generation=stored.generation,
        byte_count=stored.byte_count, kind="source_pdf", expected_revision=0,
        physical_page_count=1)
    DurableVersions(FirestoreVersionCommands(client)).initialize_review(actor,
        body.workspace_id, "main", "report-source", title="Fictional training source",
        publication_reference="Synthetic fixture", textual_location="Fictional area",
        scenario_date=date(2026, 10, 16), revision=0, key="report-source-review")
    return {"source_sha256": stored.sha256, "source_artifact_id": "report-source"}


@app.post("/_fixture/report")
def fixture_report(body: FixtureReport) -> dict[str, str]:
    """Execute the real bounded report stage after browser submission, emulator only."""
    return run_report_job(FirestoreJobs(client), FirestoreVersionCommands(client),
        repository, documents.objects, FirestoreLeases(client),
        body.workspace_id, body.job_id)


class FixtureRun(BaseModel):
    workspace_id: str
    action: str
    job_id: str | None = None


_EVENTS = [
    {"time_seconds": second, "phase": 2, "sequence": index + 1,
     "kind": kind, "target_id": target}
    for index, (second, kind, target) in enumerate((
        (10, "pickup", "pilot-pickup"),
        (20, "depart", "pilot-vehicle"),
        (35, "arrive", "pilot-shelter"),
        (40, "admit", "pilot-shelter"),
    ))
]


@app.post("/_fixture/run")
def fixture_run(body: FixtureRun) -> dict[str, str]:
    """Commit deterministic event chunks for the local browser playback check only."""
    root = client.collection("workspaces").document(body.workspace_id)
    workspace = root.get().to_dict()
    if not workspace or workspace.get("owner_type") != "temporary":
        raise HTTPException(404, "Fixture workspace unavailable")
    actor = Actor("temporary", workspace["owner_id"])
    repository.get_workspace(actor, body.workspace_id)
    runs = FirestoreRuns(client)
    if body.action == "create":
        job_id = FirestoreJobs(client).submit(actor, body.workspace_id,
            route="playback-fixture", idempotency_key=os.urandom(12).hex(),
            stage="simulation", input_hash="a" * 64,
            estimated_units=1, required_seconds=100)["job_id"]
        fence = FirestoreLeases(client).claim(body.workspace_id, job_id)
        assert fence is not None
        runs.checkpoint(body.workspace_id, job_id, fence,
                        checkpoint_json="{}", sequence=2)
        runs.append_events(body.workspace_id, job_id, fence, _EVENTS[:2])
        return {"job_id": job_id}
    if not body.job_id:
        raise HTTPException(422, "Fixture job ID required")
    job = root.collection("jobs").document(body.job_id)
    data = job.get().to_dict()
    if not data or data.get("owner_id") != actor.owner_id:
        raise HTTPException(404, "Fixture job unavailable")
    if body.action == "finish":
        runs.append_events(body.workspace_id, body.job_id, data["fence"], _EVENTS)
        FirestoreLeases(client).publish(body.workspace_id, body.job_id, data["fence"],
            artifact_key=f"runs/{body.job_id}/fixture", result_hash=hashlib.sha256(
                repr(_EVENTS).encode()).hexdigest())
    elif body.action == "fail":
        job.update({"status": "failed"})
        root.collection("runs").document(body.job_id).update({"status": "partial"})
    else:
        raise HTTPException(422, "Unknown fixture action")
    return {"job_id": body.job_id}


class FixtureComparison(BaseModel):
    workspace_id: str
    action: str


@app.post("/_fixture/comparison")
def fixture_comparison(body: FixtureComparison) -> dict[str, object]:
    """Create a synthetic sealed case or engine-computed paired evidence for E2E only."""
    root = client.collection("workspaces").document(body.workspace_id)
    workspace = root.get().to_dict()
    if not workspace or workspace.get("owner_type") != "temporary":
        raise HTTPException(404, "Fixture workspace unavailable")
    actor = Actor("temporary", workspace["owner_id"])
    repository.get_workspace(actor, body.workspace_id)
    versions = FirestoreVersionCommands(client)
    try:
        reviewed_source = versions.read(actor, body.workspace_id, "reviews", "main")[
            "content"]["draft"]["sources"][0]["sha256"]
    except AccessDenied:
        reviewed_source = "a" * 64
    geography = pilot_geography("qc")
    review_hash = geography.scope_digest
    graph_hash = geography.graph_sha256
    if body.action == "seed":
        baseline_hash = hashlib.sha256(
            f"{body.workspace_id}:synthetic-baseline".encode()).hexdigest()
        versions.commit(actor, body.workspace_id, "baselines", "main",
            expected_revision=0, idempotency_key="comparison-baseline",
            route="fixture.baseline", seal=True, immutable=True,
            content={"baseline_hash": baseline_hash, "review_hash": review_hash,
                     "graph_hash": graph_hash,
                     "resources": {"baseline_hash": baseline_hash,
                                   "source_hashes": [reviewed_source],
                                   "water_stores": [["pickup", 100_000], ["shelter", 400_000]],
                                   "vehicle_starts": [["vehicle", "pickup"]],
                                   "shelter_ids": ["shelter"]}})
        for member in ("normal", "road_close"):
            versions.commit(actor, body.workspace_id, "scenarios", member,
                expected_revision=0, idempotency_key=f"comparison-{member}",
                route="fixture.scenario", seal=True, immutable=True,
                content={"baseline_id": "main", "baseline_hash": baseline_hash,
                         "scenario": {"id": member, "horizon_seconds": 259_200,
                                      "events": []},
                         "editor": {"demand_people": 100}})
        suite = DurableVersions(versions).seal_scenario_suite(actor,
            body.workspace_id, "main", {"scenario_ids": ["normal", "road_close"],
                                        "seed": 42}, revision=0,
            key="comparison-suite")
        return {"baseline_hash": baseline_hash,
                "suite_hash": suite["content"]["suite_hash"]}
    if body.action != "complete":
        raise HTTPException(422, "Unknown fixture action")
    baseline = versions.read(actor, body.workspace_id, "baselines", "main")["content"]
    suite = versions.read(actor, body.workspace_id, "scenario_suites", "main")["content"]
    proposal = versions.read(actor, body.workspace_id, "proposals", "main")["content"]
    if proposal["operations"] != [{"type": "add_water", "store_id": "pickup",
                                     "amount_ml": 500_000,
                                     "source_reference": "Synthetic additional supply"}]:
        raise HTTPException(422, "Fixture requires its exact tested water addition")
    sample = json.loads((ROOT / "release/validation/geography/talayan-small.json").read_text())
    graph, _ = compile_small_import(sample, CompilePolicy(30))
    proof = run_pilot_proof(graph, case="qc", start="13137612581", end="39649824",
        closed_edge="osm:107948780:13:forward", deadline=216,
        scope_hash=review_hash, graph_hash=graph_hash, source_hash=reviewed_source)
    jobs = FirestoreJobs(client)
    runs = FirestoreRuns(client)
    leases = FirestoreLeases(client)
    groups = (
        ("baseline", proof.baseline, baseline["baseline_hash"]),
        ("variant", proof.variant, proposal["variant"]["variant_hash"]),
    )
    response: dict[str, object] = {}
    for group, members, input_hash in groups:
        job_ids = []
        for index, member in enumerate(members):
            job_id = jobs.submit(actor, body.workspace_id,
                route="comparison-fixture", idempotency_key=f"{group}-{os.urandom(8).hex()}",
                stage="simulation", input_hash=input_hash,
                estimated_units=1, required_seconds=100)["job_id"]
            fence = leases.claim(body.workspace_id, job_id)
            assert fence is not None
            runs.append_events(body.workspace_id, job_id, fence,
                               list(member.result.events))
            runs.record_member_outcome(body.workspace_id, job_id, fence,
                member_id=member.member_id,
                pins={"input_hash": input_hash,
                      "source_hashes": baseline["resources"]["source_hashes"],
                      "scenario_suite_hash": suite["suite_hash"],
                      "scope_hash": review_hash, "graph_hash": graph_hash,
                      "engine_hash": hashlib.sha256(ENGINE_VERSION.encode()).hexdigest(),
                      "policy_version": POLICY_VERSION,
                      "exogenous_hash": suite["scenario_hashes"][index]},
                outcome=member.outcome, event_hash=member.result.event_hash)
            leases.publish(body.workspace_id, job_id, fence,
                artifact_key=f"runs/{job_id}/pilot-proof",
                result_hash=member.result.event_hash)
            job_ids.append(job_id)
        response[f"{group}_job_ids"] = job_ids
    return response
