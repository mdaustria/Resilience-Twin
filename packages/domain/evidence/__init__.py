"""Independent, immutable review records for sources and declared assumptions."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewSource(Record):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    physical_page_count: int = Field(strict=True, gt=0)
    role: Literal["primary", "supplement"]
    publication_reference: str = Field(min_length=1)


class ReviewClaim(Record):
    claim_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    entity_id: str | None = None
    value: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    kind: Literal["document", "external_evidence", "user_assertion", "correction"]
    source_id: str | None = None
    physical_page: int | None = Field(default=None, ge=1)
    fragment: str = Field(min_length=1)
    statement_type: Literal["reported_existing", "proposed_target", "historical"]
    applicable_from: date | None = None
    applicable_through: date | None = None
    scope_id: str = Field(min_length=1)
    status: Literal["candidate", "accepted", "contested"] = "candidate"
    conflict_group: str | None = None
    resolution_note: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.kind in ("document", "external_evidence"):
            if self.source_id is None or self.physical_page is None:
                raise ValueError("documentary claim needs its own source and physical page")
        elif self.source_id is not None or self.physical_page is not None:
            raise ValueError("assertion or correction cannot claim a document page")
        if self.applicable_from and self.applicable_through and self.applicable_from > self.applicable_through:
            raise ValueError("claim applicability is reversed")
        if self.status == "accepted" and self.conflict_group and not self.resolution_note:
            raise ValueError("accepting a competing claim needs a resolution note")
        return self


class ReviewAssumption(Record):
    assumption_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    applicable_from: date
    applicable_through: date
    usable: bool
    conversion: ReviewConversion | None = None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.applicable_from > self.applicable_through:
            raise ValueError("assumption applicability is reversed")
        if self.usable and (not self.value.isascii() or not self.value.isdigit()):
            raise ValueError("usable numeric assumption must be a nonnegative integer")
        return self


class ReviewConversion(Record):
    source_claim_id: str = Field(min_length=1)
    selected_source_value: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
    numerator: int = Field(strict=True, gt=0)
    denominator: int = Field(strict=True, gt=0)
    rounding: Literal["exact", "floor", "ceil"]
    result: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def arithmetic(self) -> Self:
        value = Decimal(self.selected_source_value) * self.numerator / self.denominator
        calculated = {
            "exact": value,
            "floor": value.to_integral_value(rounding=ROUND_FLOOR),
            "ceil": value.to_integral_value(rounding=ROUND_CEILING),
        }[self.rounding]
        if calculated != self.result:
            raise ValueError("conversion result differs from selected source value and rule")
        return self


class RequiredField(Record):
    field: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    engine_reason: str = Field(min_length=1)
    remedy: str = Field(min_length=1)
    dependent_conclusions: tuple[str, ...] = Field(min_length=1)


class ReviewDraft(Record):
    workspace_id: str = Field(min_length=1)
    revision: int = Field(strict=True, ge=0)
    sources: tuple[ReviewSource, ...]
    claims: tuple[ReviewClaim, ...]
    assumptions: tuple[ReviewAssumption, ...]
    required_fields: tuple[RequiredField, ...]
    scope_id: str = Field(min_length=1)
    scenario_date: date
    scenario_reviewed: bool
    pending_annexes: tuple[str, ...] = ()
    unsupported_procedures: tuple[str, ...] = ()
    sealed_hash: str | None = None
    acknowledged_hash: str | None = None

    @model_validator(mode="after")
    def source_citations(self) -> Self:
        source_by_id = {source.source_id: source for source in self.sources}
        if len(source_by_id) != len(self.sources):
            raise ValueError("duplicate source identity")
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate claim identity")
        for claim in self.claims:
            if claim.source_id is not None:
                source = source_by_id.get(claim.source_id)
                if source is None or claim.physical_page is None or claim.physical_page > source.physical_page_count:
                    raise ValueError("claim citation is outside its source")
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        for assumption in self.assumptions:
            if assumption.conversion is None:
                continue
            origin = claims_by_id.get(assumption.conversion.source_claim_id)
            if origin is None:
                raise ValueError("conversion references a missing source claim")
            try:
                bounds = [Decimal(part.strip()) for part in origin.value.split("-")]
            except InvalidOperation as exc:
                raise ValueError("source range is not numeric") from exc
            selected = Decimal(assumption.conversion.selected_source_value)
            if len(bounds) not in (1, 2) or not min(bounds) <= selected <= max(bounds):
                raise ValueError("selected value lies outside the source range")
            if assumption.value != str(assumption.conversion.result):
                raise ValueError("assumption value differs from conversion result")
        return self


__all__ = ["RequiredField", "ReviewAssumption", "ReviewClaim", "ReviewConversion", "ReviewDraft", "ReviewSource"]
