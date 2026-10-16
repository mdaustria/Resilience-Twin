"""Guest-only API rejects legacy account entry points and cross-session access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.firestore import Actor, FirestoreRepository
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.versions import DurableVersions
from services.api.documents import session_owner_resolver
from services.api.main import create_app

ORIGIN = "https://resilience.example"
KEY = b"test-only-secret-32-bytes-at-least!!"


def test_guest_only_app_has_no_account_routes_or_auth_configuration(
    firestore_client: Client,
) -> None:
    temporary = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    repository = FirestoreRepository(firestore_client)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_owner_for=session_owner_resolver(temporary, repository),
        durable_versions=DurableVersions(FirestoreVersionCommands(firestore_client)),
        session_origin=ORIGIN, session_csrf_key=KEY)
    assert not any(path.startswith("/api/v1/account") for path in app.openapi()["paths"])
    owner = TestClient(app, base_url=ORIGIN)
    other = TestClient(app, base_url=ORIGIN)
    first = owner.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    second = other.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert first.status_code == second.status_code == 201
    workspace = first.json()["workspace_id"]
    actor = Actor("temporary", temporary.resolve(owner.cookies["__session"]).owner_id)
    FirestoreVersionCommands(firestore_client).commit(
        actor, workspace, "reviews", "main", expected_revision=0,
        idempotency_key="guest-only", route="/reviews/main", content={"gap_only": True})
    route = f"/api/v1/workspaces/{workspace}/reviews/main"
    assert owner.get(route).status_code == 200
    assert other.get(route).status_code == 404
    for route_method, path in (("post", "/api/v1/account/session"),
                               ("get", "/api/v1/account/session"),
                               ("post", "/api/v1/account/workspaces"),
                               ("get", "/api/v1/account/workspaces/legacy")):
        response = getattr(owner, route_method)(path)
        assert response.status_code == 404

    legacy = TestClient(app, base_url=ORIGIN)
    legacy.cookies.set("__session", "legacy-account-token")
    assert legacy.get(route).status_code == 404


def test_account_workspace_records_cannot_be_read_by_guest(firestore_client: Client) -> None:
    temporary = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    repository = FirestoreRepository(firestore_client)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_owner_for=session_owner_resolver(temporary, repository),
        durable_versions=DurableVersions(FirestoreVersionCommands(firestore_client)),
        session_origin=ORIGIN, session_csrf_key=KEY)
    guest = TestClient(app, base_url=ORIGIN)
    assert guest.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN}).status_code == 201
    firestore_client.document("owners/account:legacy").set({
        "schema_version": 1, "type": "account", "owner_id": "legacy",
        "tombstoned_at": None, "expires_at": datetime.now(UTC) + timedelta(hours=1),
    })
    firestore_client.document("workspaces/legacy-saved").set({
        "schema_version": 1, "owner_type": "account", "owner_id": "legacy",
        "tombstoned_at": None, "created_at": datetime.now(UTC),
    })
    assert guest.get("/api/v1/workspaces/legacy-saved/reviews/main").status_code == 404
