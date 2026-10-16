"""Pure cross-record validation for complete operational inputs, not document drafts."""

from datetime import date
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from typing import Any
from uuid import UUID

from packages.contracts.operational import (
    Artifact,
    Assumption,
    Contract,
    Crew,
    Evidence,
    FieldBasis,
    OperationalInputs,
    Pickup,
    Shelter,
    SupplyStore,
    Supported,
    Vehicle,
    Window,
)


def unique[T](values: tuple[T, ...] | list[T], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def in_period(start: date | None, end: date | None, day: date) -> bool:
    return start is not None and end is not None and start <= day <= end


def validate_windows(windows: tuple[Window, ...]) -> None:
    ordered = sorted(windows, key=lambda window: window.start_seconds)
    for left, right in pairwise(ordered):
        require(left.end_seconds <= right.start_seconds, "overlapping availability windows")


def unit_for(field: str) -> str | None:
    for suffix, unit in (
        ("_people", "people"), ("_seconds", "seconds"), ("_mm", "mm"),
        ("_ml", "mL"), ("_centavos", "centavos"),
    ):
        if field.endswith(suffix):
            return unit
    return {
        "people": "people", "seats": "seats", "water_ml_per_person_day": "mL/person/day",
        "assistance_priority": "rank", "seed": "integer", "edge_count": "edges",
    }.get(field)


def validate_basis(
    entity: Supported,
    basis: FieldBasis,
    evidence: dict[UUID, Evidence],
    assumptions: dict[UUID, Assumption],
    scope_id: UUID,
    day: date,
) -> None:
    value = getattr(entity, basis.field)
    for evidence_id in basis.evidence_ids:
        require(evidence_id in evidence, "unknown field evidence reference")
    sources = [evidence[evidence_id] for evidence_id in basis.evidence_ids]
    assumed = basis.assumption_id is not None
    if assumed:
        require(basis.assumption_id in assumptions, "unknown field assumption reference")
    if any(source.conflict_group is not None for source in sources):
        require(basis.resolution_note is not None, "source conflict requires explicit resolution")
    for source in sources:
        usable = (
            source.review_status == "accepted"
            and source.statement_type != "proposed_target"
            and source.scope_id == scope_id
            and in_period(source.applicable_from, source.applicable_through, day)
        )
        require(usable or assumed, "unreviewed/proposed/stale/out-of-scope fact requires assumption")

    target_unit = unit_for(basis.field)
    quantities = [source for source in sources if source.quantity is not None]
    needs_conversion = any(
        source.quantity is not None and (
            source.quantity.unit != target_unit
            or source.quantity.lower != source.quantity.upper
        ) for source in quantities
    ) if type(value) is int else False
    if needs_conversion:
        require(basis.conversion is not None, "source units/ranges require explicit conversion")
    if basis.conversion is not None:
        conversion = basis.conversion
        require(type(value) is int and target_unit is not None, "conversion requires integer field")
        require(conversion.evidence_id in basis.evidence_ids, "conversion source must be retained")
        require(conversion.assumption_id == basis.assumption_id and assumed,
                "conversion requires its accepted assumption")
        source_quantity = evidence[conversion.evidence_id].quantity
        require(source_quantity is not None, "conversion requires original source quantity")
        assert source_quantity is not None
        selected = Decimal(conversion.selected_source_value)
        require(Decimal(source_quantity.lower) <= selected <= Decimal(source_quantity.upper),
                "selected value is outside source range")
        result = Fraction(selected) * conversion.numerator / conversion.denominator
        if conversion.rounding == "exact":
            require(result.denominator == 1, "fractional people/resources require explicit rounding")
            expected = result.numerator
        elif conversion.rounding == "floor":
            expected = result.numerator // result.denominator
        else:
            expected = -(-result.numerator // result.denominator)
        require(conversion.target_unit == target_unit and conversion.result == expected == value,
                "conversion result/unit disagrees with operational value")
    elif type(value) is int and quantities:
        for source in quantities:
            assert source.quantity is not None
            matches = Decimal(source.quantity.lower) == Decimal(value)
            require(matches or (assumed and basis.resolution_note is not None),
                    "changed source quantity requires a documented assumption/resolution")
    elif type(value) is int and not assumed:
        raise ValueError("numeric operational input requires a source quantity or assumption")


def validate_operational_inputs(inputs: OperationalInputs) -> OperationalInputs:
    """Reject invalid cross references/accounting before sealing. Does not prove readiness or validity."""
    # Revalidate even instances copied with Pydantic's validation-bypassing model_copy.
    inputs = OperationalInputs.model_validate_json(inputs.model_dump_json())
    artifacts: dict[UUID, str] = {}

    def check_artifacts(value: object) -> None:
        if isinstance(value, Artifact):
            previous = artifacts.setdefault(value.artifact_id, value.sha256)
            require(previous == value.sha256, "one immutable artifact ID has conflicting hashes")
        elif isinstance(value, Contract):
            for field in type(value).model_fields:
                check_artifacts(getattr(value, field))
        elif isinstance(value, tuple):
            for child in value:
                check_artifacts(child)

    check_artifacts(inputs)
    collections = (
        inputs.documents, inputs.evidence, inputs.assumptions, inputs.barangays,
        inputs.pickups, inputs.shelters, inputs.crews, inputs.vehicles,
        inputs.supply_stores, inputs.cohorts, inputs.informational_items,
    )
    ids = [item.id for collection in collections for item in collection]
    unique(ids + [inputs.scope.id, inputs.graph.id, inputs.scenario.id], "record IDs")
    scope = inputs.scope
    unique(scope.barangay_ids, "scope barangay membership")
    unique(scope.exclusions, "scope exclusions")
    unique(scope.cross_boundary_assumptions, "cross-boundary assumptions")
    require(set(scope.barangay_ids) == {item.id for item in inputs.barangays},
            "scope barangays must exactly match included population records")
    documents = {item.id: item for item in inputs.documents}
    evidence = {item.id: item for item in inputs.evidence}
    assumptions = {item.id: item for item in inputs.assumptions}
    day = inputs.scenario.start_utc.date()
    for assumption in assumptions.values():
        require(assumption.scope_id == scope.id and in_period(
            assumption.applicable_from, assumption.applicable_through, day,
        ), "assumption does not apply to scenario date/scope")
    require(set(scope.cross_boundary_assumptions) <= set(assumptions),
            "unknown cross-boundary assumption")
    for source in evidence.values():
        if source.document_id is not None:
            require(source.document_id in documents, "unknown source document")
            require(source.physical_page is not None and source.physical_page <=
                    documents[source.document_id].page_count, "physical citation exceeds document")

    entities: list[Supported] = [scope, inputs.graph, inputs.scenario]
    for collection in (inputs.barangays, inputs.pickups, inputs.shelters, inputs.crews,
                       inputs.vehicles, inputs.supply_stores, inputs.cohorts,
                       inputs.informational_items):
        entities.extend(collection)
    for entity in entities:
        for basis in entity.basis:
            validate_basis(entity, basis, evidence, assumptions, scope.id, day)

    nodes = inputs.graph.node_ids
    unique(nodes, "graph nodes")
    unique(inputs.graph.routing_profile_hashes, "routing profile hashes")
    require(bool(nodes), "graph requires reviewed nodes")
    locations: tuple[Pickup | Shelter | SupplyStore, ...] = (
        *inputs.pickups, *inputs.shelters, *inputs.supply_stores,
    )
    for located in locations:
        require(located.location.graph_node_id in nodes, "location binds to unknown graph node")
    physical_resources: tuple[Shelter | Vehicle | SupplyStore, ...] = (
        *inputs.shelters, *inputs.vehicles, *inputs.supply_stores,
    )
    physical_keys = [item.physical_resource_key for item in physical_resources]
    unique(physical_keys, "physical resource (shared facilities must be allocated once)")
    windowed_resources: tuple[Shelter | Crew | Vehicle, ...] = (
        *inputs.shelters, *inputs.crews, *inputs.vehicles,
    )
    for resource in windowed_resources:
        validate_windows(resource.availability)
    crews = {item.id: item for item in inputs.crews}
    unique([item.crew_id for item in inputs.vehicles], "dedicated crew assignment")
    for vehicle in inputs.vehicles:
        require(vehicle.crew_id in crews, "vehicle references unknown crew")
        require(vehicle.initial_location.graph_node_id in nodes, "vehicle binds to unknown node")
        require(vehicle.routing_profile.sha256 in inputs.graph.routing_profile_hashes,
                "vehicle routing profile not pinned in graph")
        unique(vehicle.supported_needs, "vehicle assistance needs")
        for window in vehicle.availability:
            require(any(crew.start_seconds <= window.start_seconds and
                        window.end_seconds <= crew.end_seconds
                        for crew in crews[vehicle.crew_id].availability),
                    "vehicle availability exceeds its dedicated crew window")
    for shelter in inputs.shelters:
        unique(shelter.permitted_needs, "shelter assistance needs")
    barangays = {item.id: item for item in inputs.barangays}
    pickups = {item.id: item for item in inputs.pickups}
    shelters = {item.id: item for item in inputs.shelters}
    stores = {item.id for item in inputs.supply_stores}
    for pickup in inputs.pickups:
        require(pickup.barangay_id in barangays, "pickup references unknown barangay")
    unique([item.population_partition_key for item in inputs.cohorts], "population partition")
    population = dict.fromkeys(barangays, 0)
    occupants = dict.fromkeys(shelters, 0)
    for cohort in inputs.cohorts:
        require(cohort.barangay_id in barangays, "cohort references unknown barangay")
        population[cohort.barangay_id] += cohort.people
        unique(cohort.assistance_needs, "cohort assistance needs")
        if cohort.shelter_id is not None:
            require(cohort.shelter_id in shelters, "cohort references unknown shelter")
            shelter = shelters[cohort.shelter_id]
            occupants[shelter.id] += cohort.people
            require(set(cohort.assistance_needs) <= set(shelter.permitted_needs),
                    "initial occupants have unsupported shelter needs")
            require(any(window.start_seconds == 0 for window in shelter.availability),
                    "initial shelter must be available at time zero")
        if cohort.pickup_id is not None:
            require(cohort.pickup_id in pickups, "cohort references unknown pickup")
            require(pickups[cohort.pickup_id].barangay_id == cohort.barangay_id,
                    "cohort and pickup barangays differ")
        if cohort.pre_shelter_water_store_id is not None:
            require(cohort.pre_shelter_water_store_id in stores, "unknown pre-shelter water store")
    for barangay_id, total in population.items():
        require(total == barangays[barangay_id].population_people,
                "cohorts must partition included population exactly; retain unrequested people")
    for shelter_id, total in occupants.items():
        require(total <= shelters[shelter_id].capacity_people, "initial shelter occupants exceed capacity")
    return inputs


def parse_operational_inputs(payload: str | bytes | dict[str, Any]) -> OperationalInputs:
    parsed = (OperationalInputs.model_validate_json(payload) if isinstance(payload, (str, bytes))
              else OperationalInputs.model_validate(payload))
    return validate_operational_inputs(parsed)
