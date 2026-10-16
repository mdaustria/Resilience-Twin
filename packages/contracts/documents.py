"""Local PDF intake policy and immutable artifact metadata for Task 3.2."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OwnershipMode = Literal["temporary", "saved"]


class IntakePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_bytes_per_file: int = Field(gt=0)
    max_physical_pages_per_file: int = Field(gt=0)


# Pilot per-file limits are the same for both modes until measured throughput
# and session-lifetime budgets justify different published limits.
INTAKE_POLICIES: dict[OwnershipMode, IntakePolicy] = {
    "temporary": IntakePolicy(max_bytes_per_file=10_000_000, max_physical_pages_per_file=200),
    "saved": IntakePolicy(max_bytes_per_file=10_000_000, max_physical_pages_per_file=200),
}


class DocumentPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    physical_page: int = Field(ge=1)
    coverage_status: Literal["unresolved", "processed", "failed"] = "unresolved"
    extraction_method: Literal["none", "text", "visual", "manual", "mixed"] = "none"
    recovery_reason: str = "Awaiting page and visual-region extraction/review"


class DocumentArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str
    ownership_mode: OwnershipMode
    storage_key: str
    sha256: str
    byte_size: int = Field(gt=0)
    media_type: Literal["application/pdf"] = "application/pdf"
    physical_page_count: int = Field(gt=0)
    pages: tuple[DocumentPage, ...]


__all__ = ["INTAKE_POLICIES", "DocumentArtifact", "DocumentPage", "IntakePolicy", "OwnershipMode"]
