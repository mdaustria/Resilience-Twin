"""Emulator and HTTP checks for temporary session lifecycle."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.sessions import IssuanceDenied, SessionUnavailable, expiry_for
from services.api.main import create_app

ORIGIN = "https://resilience.example"
START = datetime(2026, 10, 14, 1, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def setup(firestore_client: Client) -> tuple[TestClient, FirestoreTemporarySessions, Clock]:
    clock = Clock()
    store = FirestoreTemporarySessions(firestore_client, clock=clock,
                                       issuance_check=lambda: True)
    app = create_app(local_fixture_mode=False, temporary_sessions=store,
                     session_origin=ORIGIN, session_csrf_key=b"test-only-secret-32-bytes-at-least!!")
    return TestClient(app, base_url=ORIGIN), store, clock


def _create(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert response.status_code == 201, response.text
    return client.cookies["__session"], response.json()


def test_atomic_creation_refresh_duplicate_and_polling(
    setup: tuple[TestClient, FirestoreTemporarySessions, Clock], firestore_client: Client,
) -> None:
    client, store, clock = setup
    before_sessions = len(list(firestore_client.collection("browser_sessions").stream()))
    before_owners = len(list(firestore_client.collection("owners").stream()))
    before_workspaces = len(list(firestore_client.collection("workspaces").stream()))
    handle, first = _create(client)
    assert len(handle) >= 43
    cookie = client.post("/api/v1/temporary-sessions", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]}).headers.get("set-cookie")
    assert cookie is None
    assert len(list(firestore_client.collection("browser_sessions").stream())) == before_sessions + 1
    assert len(list(firestore_client.collection("owners").stream())) == before_owners + 1
    assert len(list(firestore_client.collection("workspaces").stream())) == before_workspaces + 1
    digest = hashlib.sha256(handle.encode()).hexdigest()
    record = firestore_client.collection("browser_sessions").document(digest).get().to_dict()
    assert record is not None and handle not in str(record)
    assert record["temporary_workspace_id"] == first["workspace_id"]
    assert "account_owner_id" not in record
    clock.now += timedelta(hours=1)
    refreshed = TestClient(client.app, base_url=ORIGIN)
    refreshed.cookies.set("__session", handle)
    for _ in range(3):
        response = refreshed.get("/api/v1/temporary-sessions/current")
        assert response.status_code == 200
        assert response.json()["expires_at"] == first["expires_at"]
        assert response.headers["Cache-Control"] == "private, no-store"
    assert store.resolve(handle).workspace_id == first["workspace_id"]
    clock.now = START + timedelta(hours=2)
    assert refreshed.get("/api/v1/temporary-sessions/current").status_code == 401


def test_secure_cookie_activity_expiry_and_csrf(
    setup: tuple[TestClient, FirestoreTemporarySessions, Clock],
) -> None:
    client, store, clock = setup
    assert client.post("/api/v1/temporary-sessions", headers={
        "Origin": "https://evil.example"}).status_code == 403
    handle, first = _create(client)
    cookie = client.post("/api/v1/temporary-sessions", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]})
    assert cookie.status_code == 200
    creation_cookie = TestClient(client.app, base_url=ORIGIN).post(
        "/api/v1/temporary-sessions", headers={"Origin": ORIGIN}).headers["set-cookie"]
    assert "Secure" in creation_cookie and "HttpOnly" in creation_cookie
    assert "SameSite=lax" in creation_cookie and "Domain=" not in creation_cookie
    assert client.post("/api/v1/temporary-sessions/current/activity",
                       headers={"Origin": ORIGIN}).status_code == 403
    assert client.post("/api/v1/temporary-sessions/current/activity", headers={
        "Origin": "https://evil.example", "X-CSRF-Token": first["csrf_token"]}).status_code == 403
    clock.now += timedelta(hours=1)
    response = client.post("/api/v1/temporary-sessions/current/activity", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]})
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["expires_at"]) == START + timedelta(hours=3)
    assert store.resolve(handle).last_user_activity_at == clock.now
    assert expiry_for(START, START + timedelta(hours=23)) == START + timedelta(hours=24)
    clock.now = START + timedelta(hours=24)
    assert client.post("/api/v1/temporary-sessions/current/activity", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]}).status_code == 401


def test_revoked_owner_and_mixed_legacy_reference_cannot_be_revived(
    setup: tuple[TestClient, FirestoreTemporarySessions, Clock], firestore_client: Client,
) -> None:
    client, store, clock = setup
    handle, first = _create(client)
    session_ref = firestore_client.collection("browser_sessions").document(
        hashlib.sha256(handle.encode()).hexdigest())
    session_ref.update({"account_owner_id": "independent-account",
                        "account_auth_time": 100,
                        "account_expires_at": clock.now + timedelta(hours=24)})
    clock.now += timedelta(minutes=30)
    with pytest.raises(SessionUnavailable):
        store.renew(handle)
    with pytest.raises(SessionUnavailable):
        store.resolve(handle)
    assert client.get("/api/v1/temporary-sessions/current").status_code == 401
    assert client.delete("/api/v1/temporary-sessions/current", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]}).status_code == 401
    assert session_ref.get().to_dict()["account_owner_id"] == "independent-account"

    # A new guest session never imports the legacy account reference.
    replacement = client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN})
    assert replacement.status_code == 201
    replacement_handle = client.cookies["__session"]
    assert replacement_handle != handle
    assert "account_owner_id" not in firestore_client.collection("browser_sessions").document(
        hashlib.sha256(replacement_handle.encode()).hexdigest()).get().to_dict()
    response = client.delete("/api/v1/temporary-sessions/current", headers={
        "Origin": ORIGIN, "X-CSRF-Token": replacement.json()["csrf_token"]})
    assert response.status_code == 204
    assert "__session" not in client.cookies
    with pytest.raises(SessionUnavailable):
        store.renew(replacement_handle)
    assert firestore_client.collection("workspaces").document(
        replacement.json()["workspace_id"]).get(
    ).to_dict()["tombstoned_at"] == clock.now
    assert client.get("/api/v1/temporary-sessions/current").status_code == 401


def test_late_renewal_cannot_revive_expired_or_revoked_session(
    setup: tuple[TestClient, FirestoreTemporarySessions, Clock],
) -> None:
    client, store, clock = setup
    handle, first = _create(client)
    clock.now = START + timedelta(hours=2)
    with pytest.raises(SessionUnavailable):
        store.renew(handle)
    with pytest.raises(SessionUnavailable):
        store.resolve(handle)
    assert client.post("/api/v1/temporary-sessions/current/activity", headers={
        "Origin": ORIGIN, "X-CSRF-Token": first["csrf_token"]}).status_code == 401

    # Concurrent late requests must each observe the persisted expiry.
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda _: _late_renewal_rejected(store, handle), range(2)))
    assert attempts == [True, True]


def _late_renewal_rejected(store: FirestoreTemporarySessions, handle: str) -> bool:
    try:
        store.renew(handle)
    except SessionUnavailable:
        return True
    return False


def test_expired_or_tombstoned_owner_and_issuance_hook(
    setup: tuple[TestClient, FirestoreTemporarySessions, Clock], firestore_client: Client,
) -> None:
    client, store, clock = setup
    handle, _ = _create(client)
    owner_id = store.resolve(handle).owner_id
    firestore_client.collection("owners").document(f"temporary:{owner_id}").update({
        "tombstoned_at": clock.now})
    with pytest.raises(SessionUnavailable):
        store.renew(handle)
    denied = FirestoreTemporarySessions(firestore_client, clock=clock,
                                        issuance_check=lambda: False)
    with pytest.raises(IssuanceDenied):
        denied.issue()
    assert client.post("/api/v1/temporary-sessions", headers={"Origin": ORIGIN}).status_code == 201
