"""Revision, reference and immutable-seal behavior against Firestore."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence import (
    AccessDenied,
    Actor,
    Conflict,
    FirestoreRepository,
    InvalidRecord,
)


def test_stale_revision_and_seal_are_fail_closed(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_version")
    workspace = "task41_version_ws"
    repo.create_owner_workspace(actor, workspace,
                                expires_at=datetime.now(UTC) + timedelta(hours=1))
    repo.put_artifact(actor, workspace, "source", sha256="b" * 64,
                      object_key=f"workspaces/{workspace}/source", generation=7,
                      byte_count=100, kind="source_pdf", expected_revision=0)
    with pytest.raises(Conflict):
        repo.put_evidence(actor, workspace, "claim", source_artifact_id="source",
                          physical_page=1, claim="cited", expected_revision=0)
    repo.put_evidence(actor, workspace, "claim", source_artifact_id="source",
                      physical_page=1, claim="cited", expected_revision=1)
    repo.create_twin(actor, workspace, "twin", source_artifact_id="source",
                     expected_revision=2)
    with pytest.raises(InvalidRecord):
        repo.seal_version(actor, workspace, "twin", "too_many_references",
                          artifact_id="source",
                          evidence_ids=[f"e{number}" for number in range(101)],
                          input_hash="c" * 64, expected_revision=0)
    with pytest.raises(InvalidRecord):
        repo.seal_version(actor, workspace, "twin", "seal_bad",
                          artifact_id="absent", evidence_ids=["claim"],
                          input_hash="c" * 64, expected_revision=0)
    repo.seal_version(actor, workspace, "twin", "seal",
                      artifact_id="source", evidence_ids=["claim"],
                      input_hash="c" * 64, expected_revision=0)
    with pytest.raises(Conflict):
        repo.seal_version(actor, workspace, "twin", "seal",
                          artifact_id="source", evidence_ids=["claim"],
                          input_hash="d" * 64, expected_revision=1)
    sealed = firestore_client.document(
        f"workspaces/{workspace}/twins/twin/versions/seal"
    ).get().to_dict()
    assert sealed["input_hash"] == "c" * 64
    assert sealed["evidence_ids"] == ["claim"]
    assert not firestore_client.document(
        f"workspaces/{workspace}/twins/twin/versions/seal_bad"
    ).get().exists
    assert not firestore_client.document(
        f"workspaces/{workspace}/twins/twin/versions/too_many_references"
    ).get().exists


def test_metadata_bound_and_scoped_object_path(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_bounds")
    repo.create_owner_workspace(actor, "task41_bounds_ws",
                                expires_at=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(InvalidRecord):
        repo.put_artifact(actor, "task41_bounds_ws", "wrong", sha256="e" * 64,
                          object_key="workspaces/other/source", generation=1,
                          byte_count=1, kind="source_pdf", expected_revision=0)
    with pytest.raises(InvalidRecord):
        repo.put_artifact(actor, "task41_bounds_ws", "huge", sha256="e" * 64,
                          object_key="workspaces/task41_bounds_ws/source", generation=1,
                          byte_count=1, kind="x" * (129 * 1024), expected_revision=0)
    with pytest.raises(InvalidRecord):
        repo.put_artifact(actor, "task41_bounds_ws", "geometry", sha256="e" * 64,
                          object_key="workspaces/task41_bounds_ws/geometry", generation=1,
                          byte_count=1, kind="reviewed_geometry", expected_revision=0)
    repo.put_artifact(actor, "task41_bounds_ws", "geometry", sha256="e" * 64,
                      object_key="workspaces/task41_bounds_ws/geometry", generation=1,
                      byte_count=1, kind="reviewed_geometry", expected_revision=0,
                      crs="EPSG:32651", bounds=[120.0, 14.0, 121.0, 15.0])
    saved = repo.get_record(actor, "task41_bounds_ws", "artifacts", "geometry")
    assert saved["crs"] == "EPSG:32651"
    assert saved["bounds"] == [120.0, 14.0, 121.0, 15.0]


def test_unknown_schema_version_fails_closed(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_schema")
    workspace = "task41_schema_ws"
    repo.create_owner_workspace(actor, workspace,
                                expires_at=datetime.now(UTC) + timedelta(hours=1))
    firestore_client.document(f"workspaces/{workspace}").update({"schema_version": 2})
    with pytest.raises(AccessDenied):
        repo.get_workspace(actor, workspace)
    with pytest.raises(AccessDenied):
        repo.put_artifact(actor, workspace, "source", sha256="a" * 64,
                          object_key=f"workspaces/{workspace}/source", generation=1,
                          byte_count=1, kind="synthetic", expected_revision=0)
    assert not firestore_client.document(f"workspaces/{workspace}/artifacts/source").get().exists


def test_contending_seals_publish_only_one_version(firestore_client: Client) -> None:
    repo = FirestoreRepository(firestore_client)
    actor = Actor("temporary", "task41_race")
    workspace = "task41_race_ws"
    repo.create_owner_workspace(actor, workspace,
                                expires_at=datetime.now(UTC) + timedelta(hours=1))
    repo.put_artifact(actor, workspace, "source", sha256="a" * 64,
                      object_key=f"workspaces/{workspace}/source", generation=1,
                      byte_count=1, kind="synthetic", expected_revision=0)
    repo.create_twin(actor, workspace, "twin", source_artifact_id="source",
                     expected_revision=1)

    def seal(version_id: str) -> str:
        try:
            repo.seal_version(actor, workspace, "twin", version_id,
                              artifact_id="source", evidence_ids=[],
                              input_hash="b" * 64, expected_revision=0)
            return "sealed"
        except Conflict:
            return "conflict"
        except ValueError as error:
            if "Failed to commit transaction in 5 attempts" not in str(error):
                raise
            return "contention_exhausted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(seal, ("one", "two")))
    assert sorted(results) in (
        ["conflict", "sealed"],
        ["contention_exhausted", "sealed"],
        ["contention_exhausted", "contention_exhausted"],
    )
    if results.count("sealed") == 0:
        repo.seal_version(actor, workspace, "twin", "recovery",
                          artifact_id="source", evidence_ids=[],
                          input_hash="b" * 64, expected_revision=0)
    versions = list(firestore_client.collection(
        f"workspaces/{workspace}/twins/twin/versions"
    ).stream())
    assert len(versions) == 1
    assert all(version.to_dict()["input_hash"] == "b" * 64 for version in versions)
    assert firestore_client.document(f"workspaces/{workspace}/twins/twin").get().to_dict()[
        "revision"
    ] == 1


def test_authorized_nonproduction_firestore_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    project = os.getenv("RT_FIRESTORE_SMOKE_PROJECT")
    database = os.getenv("RT_FIRESTORE_SMOKE_DATABASE")
    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    approved = os.getenv("RT_FIRESTORE_SMOKE_APPROVED")
    if not project or not database or not credential_path or approved != "1":
        pytest.fail(
            "Required cloud smoke missing: set RT_FIRESTORE_SMOKE_PROJECT, "
            "RT_FIRESTORE_SMOKE_DATABASE, GOOGLE_APPLICATION_CREDENTIALS, "
            "and RT_FIRESTORE_SMOKE_APPROVED=1 "
            "for an authorized nonproduction Firestore project"
        )
    if project.startswith("demo-") or not os.path.isfile(credential_path):
        pytest.fail("Cloud smoke needs a real project and readable credentials")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    client = firestore.Client(project=project, database=database)
    suffix = uuid4().hex[:16]
    actor = Actor("temporary", f"rt41_{suffix}")
    other = Actor("temporary", f"rt41_other_{suffix}")
    workspace = f"rt41_ws_{suffix}"
    other_workspace = f"rt41_other_ws_{suffix}"
    repo = FirestoreRepository(client)
    created: list[tuple[Actor, str]] = []
    try:
        repo.create_owner_workspace(actor, workspace,
                                    expires_at=datetime.now(UTC) + timedelta(hours=1))
        created.append((actor, workspace))
        repo.create_owner_workspace(other, other_workspace,
                                    expires_at=datetime.now(UTC) + timedelta(hours=1))
        created.append((other, other_workspace))
        for current_actor, current_workspace in created:
            repo.put_artifact(
                current_actor, current_workspace, "same_source", sha256="f" * 64,
                object_key=f"workspaces/{current_workspace}/same_source",
                generation=1, byte_count=1, kind="synthetic", expected_revision=0,
            )
        assert repo.get_workspace(actor, workspace)["revision"] == 1
        assert len(repo.list_workspaces(actor)) == 1
        with pytest.raises(AccessDenied, match="Workspace unavailable"):
            repo.get_workspace(actor, other_workspace)
    finally:
        try:
            for current_actor, current_workspace in ((actor, workspace), (other, other_workspace)):
                artifact = client.document(
                    f"workspaces/{current_workspace}/artifacts/same_source"
                )
                workspace_ref = client.document(f"workspaces/{current_workspace}")
                owner_ref = client.document(
                    f"owners/{current_actor.kind}:{current_actor.owner_id}"
                )
                artifact.delete()
                workspace_ref.delete()
                owner_ref.delete()
                assert not artifact.get().exists
                assert not workspace_ref.get().exists
                assert not owner_ref.get().exists
        finally:
            client.close()
