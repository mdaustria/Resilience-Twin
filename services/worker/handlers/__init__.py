"""Bounded stage execution with durable checkpoints and fenced publication."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from packages.adapters.geo.compiler import CompilePolicy, compile_small_import
from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.jobs import FirestoreJobs
from packages.adapters.persistence.runs import FirestoreRuns
from packages.application.extraction import ExtractionPort, extract_group
from packages.application.reports import render_verified_html
from packages.contracts.checkpoints import RunCheckpoint
from packages.contracts.evidence import PageGroup
from packages.contracts.outcomes import Outcome
from packages.reports import ReportSpec, spec_from_record
from packages.simulation.runner import Handler, RunResult, RunState, run_simulation
from services.worker.leases import FirestoreLeases


def run_simulation_stage(runs: FirestoreRuns, leases: FirestoreLeases,
                         workspace_id: str, job_id: str, manifest_hash: str,
                         handler: Handler, *, initial_state: Callable[[], RunState],
                         checkpoint_after_events: int = 2,
                         interrupt_after_checkpoint: bool = False,
                         checkpoint_hook: Callable[[], None] | None = None,
                         member_evidence: Callable[[RunResult],
                                                   tuple[str, dict[str, Any], Outcome]] | None = None,
                         ) -> RunResult:
    fence = leases.claim(workspace_id, job_id)
    if fence is None:
        raise ValueError("Job already completed or cancelled")
    saved = runs.read_checkpoint(workspace_id, job_id)
    def persist_checkpoint(checkpoint: RunCheckpoint) -> None:
        runs.checkpoint(workspace_id, job_id, fence,
                        checkpoint_json=checkpoint.model_dump_json(),
                        sequence=checkpoint.sequence)
        if checkpoint_hook is not None:
            checkpoint_hook()
        if interrupt_after_checkpoint:
            raise RuntimeError("Injected worker termination after checkpoint")

    if saved:
        restored = RunCheckpoint.model_validate_json(saved)
        result = run_simulation(manifest_hash, handler, checkpoint=restored,
                                checkpoint_after_events=(
                                    restored.sequence + checkpoint_after_events),
                                on_checkpoint=persist_checkpoint)
    else:
        result = run_simulation(manifest_hash, handler, state=initial_state(),
                                checkpoint_after_events=checkpoint_after_events,
                                on_checkpoint=persist_checkpoint)
    runs.append_events(workspace_id, job_id, fence, list(result.events))
    if member_evidence is not None:
        member_id, pins, outcome = member_evidence(result)
        runs.record_member_outcome(workspace_id, job_id, fence,
                                   member_id=member_id, pins=pins,
                                   outcome=outcome, event_hash=result.event_hash)
    leases.publish(workspace_id, job_id, fence,
                   artifact_key=f"runs/{job_id}/attempt-{fence}/result",
                   result_hash=result.event_hash)
    return result


Stage = Callable[[dict[str, Any]], dict[str, Any]]


def extraction_stage(group: PageGroup, provider: ExtractionPort, *,
                     extractor_version: str, write_once: Callable[[str, bytes], Any],
                     artifact_key: str) -> dict[str, str]:
    batch = extract_group(group, provider, extractor_version=extractor_version)
    payload = batch.model_dump_json().encode()
    write_once(artifact_key, payload)
    return {"artifact_key": artifact_key, "hash": hashlib.sha256(payload).hexdigest()}


def graph_stage(small_import: dict[str, Any], policy: CompilePolicy, *,
                write_once: Callable[[str, bytes], Any], artifact_key: str) -> dict[str, str]:
    graph, record = compile_small_import(small_import, policy)
    payload = json.dumps({"graph": asdict(graph), "record": asdict(record)},
                         sort_keys=True, separators=(",", ":")).encode()
    write_once(artifact_key, payload)
    return {"artifact_key": artifact_key, "hash": hashlib.sha256(payload).hexdigest()}


def report_stage(spec: ReportSpec, source_pdf: Path, *,
                 write_once: Callable[[str, bytes], Any], artifact_key: str) -> dict[str, str]:
    payload = render_verified_html(spec, source_pdf)
    write_once(artifact_key, payload)
    return {"artifact_key": artifact_key, "hash": hashlib.sha256(payload).hexdigest()}


def run_report_job(jobs: FirestoreJobs, versions: FirestoreVersionCommands,
                   repository: FirestoreRepository, objects: Any, leases: FirestoreLeases,
                   workspace_id: str, job_id: str, *, node: str = "node") -> dict[str, str]:
    """Render a pinned snapshot to PDF and fence the immutable object publication."""
    fence = leases.claim(workspace_id, job_id)
    if fence is None:
        raise ValueError("Report job already completed or cancelled")
    raw = jobs.client.collection("workspaces").document(workspace_id).collection(
        "jobs").document(job_id).get().to_dict()
    if not raw or raw.get("stage") != "report":
        raise ValueError("Report job unavailable")
    actor = Actor(raw["owner_type"], raw["owner_id"])
    job = jobs.read(actor, workspace_id, job_id)
    version = versions.read(actor, workspace_id, "reports", job["input_hash"][:40])
    if not version["sealed"] or version["content_hash"] != job["input_hash"]:
        raise ValueError("Report snapshot differs from queued input")
    content = version["content"]
    spec = spec_from_record(content["spec"])
    source = repository.get_record(actor, workspace_id, "artifacts",
                                   content["source_artifact_id"])
    if source["sha256"] != spec.source_sha256 or source["kind"] != "source_pdf":
        raise ValueError("Report source differs from immutable PDF")
    source_bytes = objects.read_all(source["object_key"], source["generation"])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_path = root / "source.pdf"
        html_path = root / "report.html"
        pdf_path = root / "report.pdf"
        source_path.write_bytes(source_bytes)
        html_path.write_bytes(render_verified_html(spec, source_path))
        script = Path(__file__).resolve().parents[3] / "packages/reports/render_pdf.mjs"
        subprocess.run([node, str(script), str(html_path), str(pdf_path)], check=True,
                       timeout=120, cwd=script.parents[2])
        payload = pdf_path.read_bytes()
    if not payload.startswith(b"%PDF-"):
        raise ValueError("Report renderer did not produce a PDF")
    key = f"workspaces/{workspace_id}/reports/{job_id}/attempt-{fence}.pdf"
    stored = objects.write_once(key, payload)
    leases.publish(workspace_id, job_id, fence, artifact_key=key,
                   result_hash=stored.sha256, artifact_generation=stored.generation,
                   artifact_byte_count=stored.byte_count)
    return {"artifact_key": key, "hash": stored.sha256}


def run_bounded_stage(leases: FirestoreLeases, workspace_id: str,
                      job_id: str, stage: str, input_data: dict[str, Any],
                      handlers: dict[str, Stage]) -> dict[str, Any]:
    if stage not in {"extraction", "graph", "report"} or stage not in handlers:
        raise ValueError("Unsupported stage")
    fence = leases.claim(workspace_id, job_id)
    if fence is None:
        raise ValueError("Job already completed or cancelled")
    result = handlers[stage](input_data)
    if not isinstance(result.get("artifact_key"), str) or not isinstance(result.get("hash"), str):
        raise TypeError("Stage did not publish an attempt artifact")
    leases.publish(workspace_id, job_id, fence,
                   artifact_key=result["artifact_key"], result_hash=result["hash"])
    return result


__all__ = ["extraction_stage", "graph_stage", "report_stage", "run_bounded_stage", "run_report_job",
           "run_simulation_stage"]
