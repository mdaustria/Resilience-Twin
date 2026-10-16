"""Durable simulation checkpoint, recovery and paged event verification."""

import hashlib
import json
import multiprocessing
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from google.cloud.firestore_v1 import Client

from packages.adapters.ai import SavedResponseAdapter
from packages.adapters.geo.compiler import CompilePolicy
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.runs import FirestoreRuns
from packages.adapters.storage import MemoryObjectStore
from packages.reports import ReportSpec
from packages.simulation.runner import run_simulation
from services.worker.handlers import (
    extraction_stage,
    graph_stage,
    report_stage,
    run_bounded_stage,
    run_simulation_stage,
)
from services.worker.leases import FirestoreLeases
from tests.contracts.test_extraction import DOCUMENT, FIXTURE, group
from tests.engine.test_replay import MANIFEST, handler, setup_run


def _exit_mid_simulation(workspace_id: str, job_id: str) -> None:
    """Run in a separate process so abrupt termination cannot unwind the worker."""
    from google.cloud import firestore

    client = firestore.Client(project="demo-resilience-twin")
    run_simulation_stage(FirestoreRuns(client), FirestoreLeases(client, lease_seconds=10),
                         workspace_id, job_id, MANIFEST, handler,
                         initial_state=setup_run,
                         checkpoint_hook=lambda: os._exit(37))
    os._exit(38)


def test_checkpoint_recovery_replays_identically(firestore_client: Client) -> None:
    actor = Actor("temporary", "stage-owner")
    workspace_id = "stage-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    job_id = FirestoreJobs(firestore_client).submit(
        actor, workspace_id, route="runs", idempotency_key="one", stage="simulation",
        input_hash=MANIFEST, estimated_units=1, required_seconds=100)["job_id"]
    runs = FirestoreRuns(firestore_client)
    now = datetime.now(UTC)
    process = multiprocessing.get_context("spawn").Process(
        target=_exit_mid_simulation, args=(workspace_id, job_id))
    process.start()
    process.join(timeout=30)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("worker did not reach a durable mid-computation checkpoint")
    assert process.exitcode == 37, "worker did not terminate at the checkpoint"
    assert runs.read_checkpoint(workspace_id, job_id)
    assert firestore_client.collection("workspaces").document(workspace_id).collection(
        "jobs").document(job_id).get().to_dict()["status"] == "running"
    resumed_lease = FirestoreLeases(firestore_client,
        clock=lambda: now + timedelta(seconds=60))
    resumed = run_simulation_stage(runs, resumed_lease, workspace_id, job_id,
                                   MANIFEST, handler, initial_state=setup_run)
    full = run_simulation(MANIFEST, handler, state=setup_run())
    assert (resumed.event_hash, resumed.metric_hash, resumed.events) == (
        full.event_hash, full.metric_hash, full.events)
    page = runs.event_page(actor, workspace_id, job_id, limit=2)
    assert page["items"] == list(full.events[:2])
    assert runs.event_page(actor, workspace_id, job_id, after=page["next"])[
        "items"] == list(full.events[2:])
    assert resumed_lease.claim(workspace_id, job_id) is None


def test_report_stage_publishes_immutable_attempt_bytes(
    tmp_path: Path, firestore_client: Client,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"synthetic immutable source")
    spec = ReportSpec(kind="gap_only", source_title="Synthetic source",
                      source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      scope="Fictional study", exclusions=(), evidence=(),
                      gaps=("No reviewed water inventory",), assumptions=(),
                      metrics=(), regressions=(), attribution=())
    store = MemoryObjectStore()
    key = "workspaces/stage-workspace/runs/job/attempt-1/report.html"
    result = report_stage(spec, source, write_once=store.write_once, artifact_key=key)
    assert result["artifact_key"] == key
    assert result["hash"] == hashlib.sha256(store.read_all(key, 1)).hexdigest()
    assert b"No reviewed water inventory" in store.read_all(key, 1)
    actor = Actor("temporary", "report-stage-owner")
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, "report-stage-workspace",
        expires_at=datetime.now(UTC) + timedelta(hours=1))
    job_id = FirestoreJobs(firestore_client).submit(
        actor, "report-stage-workspace", route="reports", idempotency_key="one",
        stage="report", input_hash=spec.source_sha256, estimated_units=1,
        required_seconds=100)["job_id"]
    attempt_key = f"workspaces/report-stage-workspace/runs/{job_id}/attempt-1/report.html"
    published = run_bounded_stage(FirestoreLeases(firestore_client),
        "report-stage-workspace", job_id, "report", {},
        {"report": lambda _input: report_stage(
            spec, source, write_once=store.write_once, artifact_key=attempt_key)})
    stored_run = firestore_client.collection("workspaces").document(
        "report-stage-workspace").collection("runs").document(job_id).get().to_dict()
    assert stored_run["artifact_key"] == attempt_key
    assert stored_run["result_hash"] == published["hash"]


def test_bounded_extraction_and_graph_publish_actual_artifacts(firestore_client: Client) -> None:
    actor = Actor("temporary", "bounded-stage-owner")
    workspace_id = "bounded-stage-workspace"
    FirestoreRepository(firestore_client).create_owner_workspace(
        actor, workspace_id, expires_at=datetime.now(UTC) + timedelta(hours=1))
    small_import_path = Path("release/validation/geography/utrecht-small.json")
    small_import = json.loads(small_import_path.read_text(encoding="utf-8"))
    store = MemoryObjectStore()
    jobs = FirestoreJobs(firestore_client)
    leases = FirestoreLeases(firestore_client)
    stages = (
        ("extraction", DOCUMENT, lambda key: extraction_stage(
            group(120, 121), SavedResponseAdapter(FIXTURE,
                expected_document_sha256=DOCUMENT), extractor_version="saved-v1",
            write_once=store.write_once, artifact_key=key)),
        ("graph", small_import["source_sha256"], lambda key: graph_stage(
            small_import, CompilePolicy(30), write_once=store.write_once,
            artifact_key=key)),
    )
    for stage, input_hash, execute in stages:
        job_id = jobs.submit(actor, workspace_id, route=f"stages/{stage}",
            idempotency_key=stage, stage=stage, input_hash=input_hash,
            estimated_units=1, required_seconds=100)["job_id"]
        key = f"workspaces/{workspace_id}/runs/{job_id}/attempt-1/{stage}.json"
        result = run_bounded_stage(leases, workspace_id, job_id, stage, {},
                                   {stage: lambda _input, run=execute, path=key: run(path)})
        payload = store.read_all(key, store.objects[key][0])
        assert result["hash"] == hashlib.sha256(payload).hexdigest()
        run = firestore_client.collection("workspaces").document(workspace_id).collection(
            "runs").document(job_id).get().to_dict()
        assert (run["artifact_key"], run["result_hash"], run["status"]) == (
            key, result["hash"], "complete")
        parsed = json.loads(payload)
        if stage == "extraction":
            assert parsed["document_sha256"] == DOCUMENT
            assert parsed["coverage"]
        else:
            assert parsed["graph"]["edges"]
            assert parsed["record"]["source_sha256"] == input_hash
