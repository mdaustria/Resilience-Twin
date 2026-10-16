"""Versioned, checksummed JSON checkpoint envelope."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class RunCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: str = "checkpoint_v1"
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence: int = Field(ge=0)
    state: dict[str, Any]
    events: list[dict[str, Any]]
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> "RunCheckpoint":
        if self.version != "checkpoint_v1":
            raise ValueError("unsupported checkpoint version")
        contents = self.model_dump(exclude={"checksum"})
        if hashlib.sha256(canonical_json(contents)).hexdigest() != self.checksum:
            raise ValueError("checkpoint checksum mismatch")
        return self


def seal_checkpoint(
    manifest_hash: str, sequence: int, state: dict[str, Any],
    events: list[dict[str, Any]],
) -> RunCheckpoint:
    contents = {"version": "checkpoint_v1", "manifest_hash": manifest_hash,
                "sequence": sequence, "state": state, "events": events}
    checksum = hashlib.sha256(canonical_json(contents)).hexdigest()
    return RunCheckpoint.model_validate({**contents, "checksum": checksum})


__all__ = ("RunCheckpoint", "canonical_json", "seal_checkpoint")
