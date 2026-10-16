"""Provisional v1 operational inputs; incomplete documentary drafts stay outside this contract."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
Count = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
Positive = Annotated[int, Field(strict=True, gt=0, le=9007199254740991)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
DecimalText = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Artifact(Contract):
    artifact_id: UUID
    sha256: Sha256


class SourceDocument(Contract):
    id: UUID
    artifact: Artifact
    title: Text
    publication_reference: Text
    page_count: Positive


class SourceQuantity(Contract):
    lower: DecimalText
    upper: DecimalText
    unit: Text

    @model_validator(mode="after")
    def ordered(self) -> Self:
        from decimal import Decimal

        if Decimal(self.lower) > Decimal(self.upper):
            raise ValueError("source quantity range is reversed")
        return self


class Evidence(Contract):
    id: UUID
    kind: Literal["document", "external_evidence", "user_assertion"]
    document_id: UUID | None
    physical_page: Positive | None
    source_reference: Text
    fragment: Text
    statement_type: Literal["reported_existing", "proposed_target", "historical"]
    applicable_from: date | None
    applicable_through: date | None
    scope_id: UUID
    quantity: SourceQuantity | None
    review_status: Literal["unreviewed", "accepted", "contested"]
    conflict_group: Text | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.kind == "document":
            if self.document_id is None or self.physical_page is None:
                raise ValueError("document evidence requires a document and physical page")
        elif self.document_id is not None or self.physical_page is not None:
            raise ValueError("non-document evidence cannot claim a document page")
        if (self.applicable_from is not None and self.applicable_through is not None
                and self.applicable_from > self.applicable_through):
            raise ValueError("evidence applicability dates are reversed")
        return self


class Assumption(Contract):
    id: UUID
    statement: Text
    rationale: Text
    limitations: Text
    scope_id: UUID
    applicable_from: date
    applicable_through: date
    accepted: Literal[True]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.applicable_from > self.applicable_through:
            raise ValueError("assumption applicability dates are reversed")
        return self


class Conversion(Contract):
    """Explicit selection and rational conversion; never a hidden family-size default."""

    evidence_id: UUID
    selected_source_value: DecimalText
    numerator: Positive
    denominator: Positive
    rounding: Literal["exact", "floor", "ceil"]
    target_unit: Text
    result: Count
    assumption_id: UUID


class FieldBasis(Contract):
    field: Text
    evidence_ids: tuple[UUID, ...]
    assumption_id: UUID | None
    conversion: Conversion | None
    resolution_note: Text | None

    @model_validator(mode="after")
    def has_support(self) -> Self:
        if not self.evidence_ids and self.assumption_id is None:
            raise ValueError("operational field requires evidence or an explicit assumption")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate evidence references")
        return self


class Supported(Contract):
    id: UUID
    basis: tuple[FieldBasis, ...]

    @model_validator(mode="after")
    def complete_basis(self) -> Self:
        required = set(type(self).model_fields) - {"id", "basis"}
        fields = [item.field for item in self.basis]
        if len(fields) != len(set(fields)) or set(fields) != required:
            raise ValueError(f"field basis must cover each field exactly once: {sorted(required)}")
        return self


class Window(Contract):
    start_seconds: Count
    end_seconds: Positive

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start_seconds >= self.end_seconds:
            raise ValueError("availability window must have positive duration")
        return self


class AccessLocation(Contract):
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180)]
    latitude: Annotated[float, Field(strict=True, ge=-90, le=90)]
    graph_node_id: Text
    connector_distance_mm: Count
    connector_time_seconds: Count
    reviewed: Literal[True]


class StudyScope(Supported):
    label: Text
    boundary: Artifact
    barangay_ids: tuple[UUID, ...]
    exclusions: tuple[Text, ...]
    cross_boundary_assumptions: tuple[UUID, ...]


class Barangay(Supported):
    name: Text
    boundary: Artifact
    population_people: Count
    population_source_date: date


class Pickup(Supported):
    barangay_id: UUID
    location: AccessLocation
    staging_limit_people: Count | None


class Shelter(Supported):
    """Occupancy derives only from sheltered cohorts; there is no independent headcount."""

    physical_resource_key: Text
    location: AccessLocation
    capacity_people: Count
    availability: tuple[Window, ...]
    permitted_needs: tuple[Text, ...]
    initial_water_ml: Count
    cost_centavos: Count | None


class Crew(Supported):
    availability: tuple[Window, ...]


class Vehicle(Supported):
    physical_resource_key: Text
    seats: Positive
    initial_location: AccessLocation
    availability: tuple[Window, ...]
    crew_id: UUID
    distance_budget_mm: Count
    routing_profile: Artifact
    supported_needs: tuple[Text, ...]
    loading_seconds: Positive
    unloading_seconds: Positive
    return_required: bool = Field(strict=True)
    cost_centavos: Count | None


class SupplyStore(Supported):
    physical_resource_key: Text
    location: AccessLocation
    initial_water_ml: Count


class Cohort(Supported):
    barangay_id: UUID
    population_partition_key: Text
    people: Positive
    initial_state: Literal["not_requested", "waiting", "sheltered"]
    pickup_id: UUID | None
    shelter_id: UUID | None
    request_time_seconds: Count | None
    deadline_seconds: Count | None
    assistance_needs: tuple[Text, ...]
    assistance_priority: Count
    evacuation_mode: Literal["vehicle"]
    water_ml_per_person_day: Positive
    pre_shelter_water_store_id: UUID | None

    @model_validator(mode="after")
    def initial_accounting(self) -> Self:
        if self.initial_state == "sheltered":
            if self.shelter_id is None or any(value is not None for value in (
                self.pickup_id, self.request_time_seconds, self.deadline_seconds,
                self.pre_shelter_water_store_id,
            )):
                raise ValueError("initial occupants belong only to one shelter, without demand")
        else:
            if self.pickup_id is None or self.shelter_id is not None:
                raise ValueError("unsheltered cohorts require a pickup, not a shelter")
            if self.pre_shelter_water_store_id is None:
                raise ValueError("waiting/transit water provision must be explicit, including zero stock")
            if (self.request_time_seconds is None) != (self.deadline_seconds is None):
                raise ValueError("request time and deadline must both be supplied or absent")
            if self.initial_state == "waiting" and self.request_time_seconds != 0:
                raise ValueError("initial waiting demand starts at time zero")
            if self.initial_state == "not_requested" and self.request_time_seconds == 0:
                raise ValueError("time-zero demand must use waiting state")
            if (self.request_time_seconds is not None and self.deadline_seconds is not None
                    and self.deadline_seconds < self.request_time_seconds):
                raise ValueError("deadline cannot precede demand")
        return self


class InformationalItem(Supported):
    kind: Literal["critical_facility", "procedure", "bridge_context"]
    description: Text
    modeled: Literal[False]


class GraphSnapshot(Supported):
    artifact: Artifact
    source_snapshot: Artifact
    extent: Artifact
    buffer_mm: Count
    projection: Text
    compiler_version: Text
    node_ids: tuple[Text, ...]
    routing_profile_hashes: tuple[Sha256, ...]
    edge_count: Count
    review_status: Literal["reviewed"]


class ScenarioMetadata(Supported):
    schema_version: Literal["scenario.metadata.v1"]
    start_utc: datetime
    horizon_seconds: Positive
    exogenous_scenario: Artifact
    suite_member_id: UUID
    seed: Count
    rng_algorithm: Text

    @model_validator(mode="after")
    def utc_only(self) -> Self:
        if self.start_utc.utcoffset() != timedelta(0):
            raise ValueError("scenario start must be timezone-aware UTC")
        return self


class OperationalInputs(Contract):
    schema_version: Literal["operational.inputs.v1"]
    scope: StudyScope
    documents: tuple[SourceDocument, ...]
    evidence: tuple[Evidence, ...]
    assumptions: tuple[Assumption, ...]
    barangays: tuple[Barangay, ...]
    pickups: tuple[Pickup, ...]
    shelters: tuple[Shelter, ...]
    crews: tuple[Crew, ...]
    vehicles: tuple[Vehicle, ...]
    supply_stores: tuple[SupplyStore, ...]
    cohorts: tuple[Cohort, ...]
    informational_items: tuple[InformationalItem, ...]
    graph: GraphSnapshot
    scenario: ScenarioMetadata

    @model_validator(mode="after")
    def coherent(self) -> Self:
        # Contracts own structural validation; domain functions provide cross-record rules.
        # Importing domain here would reverse the intended dependency, so callers use
        # validate_operational_inputs before sealing/building a manifest.
        if not self.barangays or not self.cohorts:
            raise ValueError("operational inputs require barangays and population cohorts")
        return self
