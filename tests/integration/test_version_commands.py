"""Owner-checked durable review, scenario and proposal HTTP commands."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.review import default_assumptions, synthetic_review
from packages.application.versions import DurableVersions
from services.api.documents import session_owner_resolver
from services.api.main import create_app

ORIGIN = "https://resilience.example"
KEY = b"test-only-secret-32-bytes-at-least!!"


def app_for(client: Client, *, clock: Callable[[], datetime] | None = None) -> TestClient:
    temporary = FirestoreTemporarySessions(client, clock=clock or (lambda: datetime.now(UTC)),
                                           issuance_check=lambda: True)
    repository = FirestoreRepository(client)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_owner_for=session_owner_resolver(temporary, repository),
        durable_versions=DurableVersions(FirestoreVersionCommands(client)),
        session_origin=ORIGIN, session_csrf_key=KEY)
    return TestClient(app, base_url=ORIGIN)


def start_guest(client: TestClient) -> dict[str, str]:
    result = client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert result.status_code == 201, result.text
    return result.json()


def headers(csrf: str, revision: int, key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf,
            "If-Match": str(revision), "Idempotency-Key": key}


def linked_baseline(client: TestClient, firestore_client: Client,
                    guest: dict[str, str]) -> tuple[str, str]:
    csrf, workspace = guest["csrf_token"], guest["workspace_id"]
    owner_id = firestore_client.document(f"workspaces/{workspace}").get().to_dict()["owner_id"]
    repository = FirestoreRepository(firestore_client)
    actor = Actor("temporary", owner_id)
    draft = synthetic_review("alice").model_copy(update={"workspace_id": workspace,
        "assumptions": default_assumptions(synthetic_review("alice"))})
    repository.put_artifact(actor, workspace, draft.sources[0].source_id,
        sha256=draft.sources[0].sha256,
        object_key=f"workspaces/{workspace}/documents/source.pdf", generation=1,
        byte_count=1, kind="source_pdf", expected_revision=0)
    graph_hash = hashlib.sha256(b"pinned compiled synthetic graph").hexdigest()
    repository.put_artifact(actor, workspace, "graph-one", sha256=graph_hash,
        object_key=f"workspaces/{workspace}/graphs/graph-one.json", generation=1,
        byte_count=1, kind="compiled_graph", expected_revision=1)
    review_url = f"/api/v1/workspaces/{workspace}/reviews/main"
    saved = client.put(review_url, json=draft.model_dump(mode="json"),
                       headers=headers(csrf, 0, "review-ready"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"]["readiness"]["computable"] is True
    sealed = client.post(f"{review_url}/seal", headers=headers(csrf, 1, "seal-ready"))
    assert sealed.status_code == 200, sealed.text
    assert client.post(f"{review_url}/seal", headers=headers(csrf, 1, "seal-ready")).json() == sealed.json()
    assert client.post(f"{review_url}/seal", headers=headers(csrf, 1, "stale-seal")).status_code == 409
    acknowledged = client.post(f"{review_url}/acknowledge",
                               headers=headers(csrf, 2, "ack-ready"))
    assert acknowledged.status_code == 200, acknowledged.text
    assert client.post(f"{review_url}/acknowledge",
                       headers=headers(csrf, 2, "ack-ready")).json() == acknowledged.json()
    assert acknowledged.json()["content"]["readiness"]["ready_to_run"] is True
    baseline_url = f"/api/v1/workspaces/{workspace}/baselines/base"
    baseline_command = {
        "review_id": "main", "review_revision": 3, "graph_artifact_id": "graph-one",
        "resources": {"water_stores": [["a", 100], ["b", 0]],
                      "vehicle_starts": [["v", "node"]], "shelter_ids": ["s"]},
    }
    baseline = client.put(baseline_url, json=baseline_command,
                          headers=headers(csrf, 0, "baseline-one"))
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["sealed"] is True
    assert baseline.json()["content"]["graph_hash"] == graph_hash
    assert client.put(baseline_url, json=baseline_command,
                      headers=headers(csrf, 0, "baseline-one")).json() == baseline.json()
    altered = {**baseline_command, "resources": {**baseline_command["resources"],
               "water_stores": [["a", 99], ["b", 0]]}}
    assert client.put(baseline_url, json=altered,
                      headers=headers(csrf, 0, "baseline-one")).status_code == 409
    assert client.put(baseline_url, json=baseline_command,
                      headers=headers(csrf, 1, "baseline-two")).status_code == 409
    return baseline_url, baseline.json()["content"]["baseline_hash"]


def test_review_conflicts_history_restart_and_gap_only_save(firestore_client: Client) -> None:
    alice = app_for(firestore_client)
    guest = start_guest(alice)
    csrf, workspace = guest["csrf_token"], guest["workspace_id"]
    owner_id = firestore_client.document(f"workspaces/{workspace}").get().to_dict()["owner_id"]
    draft = synthetic_review("alice").model_copy(update={"workspace_id": workspace})
    FirestoreRepository(firestore_client).put_artifact(Actor("temporary", owner_id),
        workspace, draft.sources[0].source_id, sha256=draft.sources[0].sha256,
        object_key=f"workspaces/{workspace}/documents/source.pdf", generation=1,
        byte_count=1, kind="synthetic", expected_revision=0)
    route = f"/api/v1/workspaces/{workspace}/reviews/main"
    first = alice.put(route, json=draft.model_dump(mode="json"),
                      headers=headers(csrf, 0, "review-one"))
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1
    assert first.json()["content"]["readiness"]["computable"] is False
    assert alice.put(route, json=draft.model_dump(mode="json"),
                     headers=headers(csrf, 0, "review-one")).json() == first.json()
    altered = draft.model_copy(update={"pending_annexes": ("new gap",)})
    mismatch = alice.put(route, json=altered.model_dump(mode="json"),
                         headers=headers(csrf, 0, "review-one"))
    assert mismatch.status_code == 409
    assert mismatch.headers["content-type"].startswith("application/problem+json")
    assert mismatch.json()["code"] == "version_conflict"
    assert alice.put(route, json=altered.model_dump(mode="json"),
                     headers=headers(csrf, 0, "review-two")).status_code == 409
    sealed = alice.post(f"{route}/seal", headers=headers(csrf, 1, "seal-one"))
    assert sealed.status_code == 200, sealed.text
    assert sealed.json()["sealed"] is True
    assert sealed.json()["content"]["readiness"]["ready_to_run"] is False
    history = alice.get(f"{route}/history?limit=1").json()
    assert [item["revision"] for item in history["items"]] == [1]
    assert [item["revision"] for item in alice.get(
        f"{route}/history?after_revision=1&limit=1").json()["items"]] == [2]
    restarted = app_for(firestore_client)
    restarted.cookies.set("__session", alice.cookies["__session"])
    assert restarted.get(f"{route}/versions/2").json()["content_hash"] == sealed.json()["content_hash"]
    bob = app_for(firestore_client)
    start_guest(bob)
    assert bob.get(route).status_code == 404


def test_scenario_and_proposal_are_immutable(firestore_client: Client) -> None:
    alice = app_for(firestore_client)
    guest = start_guest(alice)
    csrf, workspace = guest["csrf_token"], guest["workspace_id"]
    baseline_url, baseline_hash = linked_baseline(alice, firestore_client, guest)
    baseline_ref = {"baseline_id": "base", "baseline_hash": baseline_hash}
    assert alice.get(baseline_url).json()["content"]["review_id"] == "main"
    assert [item["revision"] for item in alice.get(
        f"{baseline_url}/history?limit=1").json()["items"]] == [1]
    scenario = {**baseline_ref, "horizon_seconds": 3600, "events": [{"id": "closure",
        "effect": "edge_closed", "target_id": "road-1", "effective_seconds": 60,
        "known_seconds": 120, "hazard_reference": "reviewed flood notice"}]}
    url = f"/api/v1/workspaces/{workspace}/scenarios/flood"
    assert alice.put(url, json=scenario, headers=headers(csrf, 0, "scenario-one")).status_code == 200
    assert alice.put(url, json=scenario, headers=headers(csrf, 1, "scenario-two")).status_code == 409
    proposal = {**baseline_ref,
        "operations": [{"type": "redistribute_water", "from_store_id": "a",
                        "to_store_id": "b", "amount_ml": 40}]}
    proposal_url = f"/api/v1/workspaces/{workspace}/proposals/move-water"
    saved = alice.put(proposal_url, json=proposal,
                      headers=headers(csrf, 0, "proposal-one"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"]["variant"]["water_stores"] == [["a", 60], ["b", 40]]
    assert saved.json()["content"]["status"] == "untested"
    assert saved.json()["content"]["baseline_id"] == "base"
    assert alice.put(proposal_url, json={**proposal, "baseline_hash": "0" * 64},
                     headers=headers(csrf, 0, "proposal-two")).status_code == 422
    bob = app_for(firestore_client)
    start_guest(bob)
    assert bob.get(baseline_url).status_code == 404
    assert bob.get(url).status_code == 404
    assert bob.get(proposal_url).status_code == 404


def test_linkage_survives_restart_only_until_expiry(firestore_client: Client) -> None:
    current = [datetime.now(UTC)]
    alice = app_for(firestore_client, clock=lambda: current[0])
    guest = start_guest(alice)
    baseline_url, baseline_hash = linked_baseline(alice, firestore_client, guest)
    restarted = app_for(firestore_client, clock=lambda: current[0])
    restarted.cookies.set("__session", alice.cookies["__session"])
    assert restarted.get(baseline_url).json()["content"]["baseline_hash"] == baseline_hash
    current[0] += timedelta(hours=3)
    assert restarted.get(baseline_url).status_code == 404
