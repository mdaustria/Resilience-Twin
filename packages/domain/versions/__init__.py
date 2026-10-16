"""Revision checking, immutable sealing and personal acknowledgment hashes."""

from __future__ import annotations

import hashlib
import json

from packages.domain.evidence import ReviewDraft


class RevisionConflict(Exception):
    pass


def material_hash(draft: ReviewDraft) -> str:
    material = draft.model_dump(mode="json", exclude={"revision", "sealed_hash", "acknowledged_hash"})
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def require_revision(draft: ReviewDraft, expected: int) -> None:
    if draft.revision != expected:
        raise RevisionConflict("Review changed; reload before editing")


def seal(draft: ReviewDraft, expected: int) -> ReviewDraft:
    require_revision(draft, expected)
    return draft.model_copy(update={"revision": expected + 1, "sealed_hash": material_hash(draft),
                                    "acknowledged_hash": None})


def acknowledge(draft: ReviewDraft, expected: int) -> ReviewDraft:
    require_revision(draft, expected)
    digest = material_hash(draft)
    if draft.sealed_hash != digest:
        raise ValueError("Seal the current evidence and assumptions first")
    return draft.model_copy(update={"revision": expected + 1, "acknowledged_hash": digest})


__all__ = ["RevisionConflict", "acknowledge", "material_hash", "require_revision", "seal"]
