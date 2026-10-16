"""Convergent, owner-scoped active-copy purge in the Firestore emulator."""

from datetime import UTC, datetime, timedelta

import pytest
from google.cloud.firestore_v1 import Client

from packages.adapters.persistence.deletion import FirestoreDeletion
from packages.adapters.persistence.firestore import (
    AccessDenied,
    Actor,
    FirestoreRepository,
)
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.adapters.storage import MemoryObjectStore
from services.worker.purge import purge_page, run_purge_cycle


class VersionedObjects:
    def __init__(self) -> None:
        self.generations: dict[tuple[str, int], bytes] = {}

    def add(self, key: str, generation: int, content: bytes) -> None:
        self.generations[key, generation] = content

    def list_workspace_versions(self, workspace_id: str, *,
                                limit: int = 100) -> list[tuple[str, int]]:
        prefix = f"workspaces/{workspace_id}/"
        return sorted((key, generation) for key, generation in self.generations
                      if key.startswith(prefix))[:limit]

    def delete(self, key: str, generation: int) -> None:
        self.generations.pop((key, generation), None)


def test_repeated_purge_catches_late_objects_without_cross_owner_deletion(
    firestore_client: Client,
) -> None:
    repository = FirestoreRepository(firestore_client)
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    alice_handle, alice_view, _ = sessions.issue()
    _, bob_view, _ = sessions.issue()
    alice = Actor("temporary", alice_view.owner_id)
    bob = Actor("temporary", bob_view.owner_id)
    workspaces = (alice_view.workspace_id, bob_view.workspace_id)
    for actor, workspace in zip((alice, bob), workspaces, strict=True):
        repository.put_artifact(actor, workspace, "same-source", sha256="a" * 64,
            object_key=f"workspaces/{workspace}/documents/source.pdf", generation=1,
            byte_count=3, kind="source", expected_revision=0)
    objects = MemoryObjectStore()
    for number in range(103):
        objects.write_once(f"workspaces/{workspaces[0]}/attempts/{number:03d}", b"derived")
    bob_object = objects.write_once(f"workspaces/{workspaces[1]}/documents/source.pdf", b"same")
    alice_root = firestore_client.collection("workspaces").document(workspaces[0])
    alice_root.collection("runs").document("run").collection(
        "event_chunks").document("0000000000").set({"events_json": "sensitive"})
    deletion = FirestoreDeletion(firestore_client)
    with pytest.raises(AccessDenied):
        purge_page(deletion, objects, workspaces[0])
    assert sessions.revoke(alice_handle) is None
    first = purge_page(deletion, objects, workspaces[0], limit=100)
    assert first["objects"] == 100 and first["documents"] >= 2
    objects.write_once(f"workspaces/{workspaces[0]}/attempts/late", b"late-output")
    second = purge_page(deletion, objects, workspaces[0], limit=100)
    assert second["objects"] == 4
    assert purge_page(deletion, objects, workspaces[0]) == {"objects": 0, "documents": 0}
    assert alice_root.get().to_dict()["tombstoned_at"] is not None
    assert list(alice_root.collection("artifacts").stream()) == []
    assert list(alice_root.collection("runs").stream()) == []
    assert not alice_root.collection("runs").document("run").collection(
        "event_chunks").document("0000000000").get().exists
    assert repository.get_record(bob, workspaces[1], "artifacts", "same-source")[
        "sha256"] == "a" * 64
    assert objects.read_all(bob_object.key, bob_object.generation) == b"same"


def test_generation_purge_and_scheduler_cycle_rehearsal(firestore_client: Client) -> None:
    sessions = FirestoreTemporarySessions(firestore_client, issuance_check=lambda: True)
    alice_handle, alice, _ = sessions.issue()
    _, bob, _ = sessions.issue()
    objects = VersionedObjects()
    alice_key = f"workspaces/{alice.workspace_id}/documents/source.pdf"
    bob_key = f"workspaces/{bob.workspace_id}/documents/source.pdf"
    objects.add(alice_key, 1, b"old generation")
    objects.add(alice_key, 2, b"new generation")
    objects.add(bob_key, 3, b"other guest")
    for index in range(121):
        objects.add(f"workspaces/{alice.workspace_id}/attempts/{index:03d}",
                    index + 10, b"synthetic")
    root = firestore_client.collection("workspaces").document(alice.workspace_id)
    batch = firestore_client.batch()
    for index in range(121):
        batch.set(root.collection("jobs").document(f"job-{index:03d}"),
                  {"payload": "content-bearing synthetic job"})
    batch.commit()
    sessions.revoke(alice_handle)
    now = datetime.now(UTC) + timedelta(minutes=1)
    first = run_purge_cycle(firestore_client, objects, clock=lambda: now,
                            page_limit=50)
    print(f"purge_rehearsal={first}")
    # The session-scoped emulator also contains tombstones from earlier tests.
    assert first["objects"] == 123 and first["documents"] >= 121
    assert first["pages"] >= 4 and first["backlog"] == 0
    assert first["elapsed_seconds"] > 0
    assert (bob_key, 3) in objects.generations
    assert all(not key.startswith(f"workspaces/{alice.workspace_id}/")
               for key, _generation in objects.generations)
    objects.add(f"workspaces/{alice.workspace_id}/attempts/late", 200, b"late")
    second = run_purge_cycle(firestore_client, objects,
                             clock=lambda: now + timedelta(hours=1, minutes=1),
                             page_limit=50)
    assert second["objects"] == 1 and second["documents"] == 0
    assert (bob_key, 3) in objects.generations
    assert root.get().to_dict()["purge_next_at"] is not None
