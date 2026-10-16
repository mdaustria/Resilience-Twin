"""Guest Firestore ownership through server repositories and HTTP cookies."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence import (
    AccessDenied,
    Actor,
    Conflict,
    FirestoreRepository,
)
from packages.adapters.persistence.commands import FirestoreVersionCommands
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.versions import DurableVersions
from services.api.documents import session_owner_resolver
from services.api.main import create_app

ORIGIN = "https://resilience.example"
KEY = b"test-only-secret-32-bytes-at-least!!"


def _expires() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


def test_same_source_checksum_does_not_join_guest_owners(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    a = Actor("temporary", "task41_a")
    b = Actor("temporary", "task41_b")
    repo.create_owner_workspace(a, "task41_wa", expires_at=_expires())
    repo.create_owner_workspace(b, "task41_wb", expires_at=_expires())
    source_hash = "a" * 64
    for actor, workspace in ((a, "task41_wa"), (b, "task41_wb")):
        repo.put_artifact(actor, workspace, "pdf", sha256=source_hash,
                          object_key=f"workspaces/{workspace}/pdf", generation=1,
                          byte_count=200, kind="source_pdf", expected_revision=0)
        assert repo.get_workspace(actor, workspace)["revision"] == 1
    with pytest.raises(AccessDenied):
        repo.get_workspace(a, "task41_wb")
    with pytest.raises(AccessDenied):
        repo.get_workspace(b, "task41_wa")
    with pytest.raises(AccessDenied):
        repo.get_record(a, "task41_wb", "artifacts", "pdf")
    assert repo.get_record(a, "task41_wa", "artifacts", "pdf")["sha256"] == source_hash
    with pytest.raises(AccessDenied):
        repo.put_artifact(a, "task41_wb", "attack", sha256=source_hash,
                          object_key="workspaces/task41_wb/attack", generation=1,
                          byte_count=1, kind="source_pdf", expected_revision=1)
    assert not firestore_client.document("workspaces/task41_wb/artifacts/attack").get().exists


def test_expired_or_tombstoned_owner_fails_closed(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_expired")
    repo.create_owner_workspace(actor, "task41_expired_ws", expires_at=_expires())
    with pytest.raises(AccessDenied):
        repo.get_workspace(actor, "task41_expired_ws", now=datetime.now(UTC) + timedelta(hours=2))
    firestore_client.document("owners/temporary:task41_expired").update(
        {"tombstoned_at": datetime.now(UTC)})
    with pytest.raises(AccessDenied):
        repo.get_workspace(actor, "task41_expired_ws")


def test_one_workspace_per_temporary_owner_and_malformed_list_denied(
    firestore_client: Client,
) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_list")
    repo.create_owner_workspace(actor, "task41_list_a", expires_at=_expires())
    assert len(repo.list_workspaces(actor)) == 1
    with pytest.raises(Conflict):
        repo.create_owner_workspace(actor, "task41_list_b", expires_at=_expires())
    firestore_client.document("workspaces/task41_list_b").set({
        "schema_version": 1, "owner_type": "temporary", "owner_id": actor.owner_id,
        "tombstoned_at": None, "created_at": datetime.now(UTC),
    })
    with pytest.raises(AccessDenied):
        repo.list_workspaces(actor)


def test_legacy_account_and_mixed_records_fail_closed(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    account = Actor("account", "task41_legacy")
    with pytest.raises(AccessDenied):
        repo.create_owner_workspace(account, "task41_legacy_ws")
    firestore_client.document("owners/account:task41_legacy").set({
        "schema_version": 1, "type": "account", "owner_id": account.owner_id,
        "tombstoned_at": None,
    })
    firestore_client.document("workspaces/task41_legacy_ws").set({
        "schema_version": 1, "owner_type": "account", "owner_id": account.owner_id,
        "tombstoned_at": None,
    })
    with pytest.raises(AccessDenied):
        repo.get_workspace(account, "task41_legacy_ws")
    with pytest.raises(AccessDenied):
        repo.list_workspaces(account)
    guest = Actor("temporary", "task41_mixed")
    repo.create_owner_workspace(guest, "task41_mixed_ws", expires_at=_expires())
    firestore_client.document("workspaces/task41_mixed_ws").update(
        {"owner_user_id": "task41_legacy"})
    with pytest.raises(AccessDenied):
        repo.get_workspace(guest, "task41_mixed_ws")
    with pytest.raises(AccessDenied):
        repo.list_workspaces(guest)


def test_two_guest_cookies_isolate_same_source_through_http(firestore_client: Client) -> None:
    temporary = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    repo = FirestoreRepository(firestore_client)
    app = create_app(local_fixture_mode=False, temporary_sessions=temporary,
        private_owner_for=session_owner_resolver(temporary, repo),
        durable_versions=DurableVersions(FirestoreVersionCommands(firestore_client)),
        session_origin=ORIGIN, session_csrf_key=KEY)
    owners: list[tuple[TestClient, Actor, str]] = []
    for _ in range(2):
        client = TestClient(app, base_url=ORIGIN)
        created = client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
        assert created.status_code == 201
        handle = client.cookies["__session"]
        owner = Actor("temporary", temporary.resolve(handle).owner_id)
        workspace = created.json()["workspace_id"]
        repo.put_artifact(owner, workspace, "same_source", sha256="a" * 64,
            object_key=f"workspaces/{workspace}/same_source", generation=1,
            byte_count=1, kind="synthetic", expected_revision=0)
        FirestoreVersionCommands(firestore_client).commit(owner, workspace, "reviews", "main",
            expected_revision=0, idempotency_key="same-source", route="/reviews/main",
            content={"source_sha256": "a" * 64})
        owners.append((client, owner, workspace))

    for client, actor, workspace in owners:
        own = client.get(f"/api/v1/workspaces/{workspace}/reviews/main")
        assert own.status_code == 200
        assert own.json()["content"]["source_sha256"] == "a" * 64
        other_workspace = next(item[2] for item in owners if item[1] != actor)
        denied = client.get(f"/api/v1/workspaces/{other_workspace}/reviews/main")
        assert denied.status_code == 404
        assert denied.headers["Cache-Control"] == "private, no-store"
        with pytest.raises(AccessDenied):
            repo.get_record(actor, other_workspace, "artifacts", "same_source")
