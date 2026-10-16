"""Operational inputs reject silent assumptions, duplicated resources and impossible accounting."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from packages.domain.inputs import parse_operational_inputs

FIXTURE = Path(__file__).parents[1] / "fixtures/inputs/operational.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def capacity_source(data, *, lower="80", upper="80", unit="people"):
    evidence_id = str(UUID(int=200))
    evidence = {
        "id": evidence_id, "kind": "user_assertion", "document_id": None,
        "physical_page": None, "source_reference": "Synthetic test assertion",
        "fragment": f"Capacity {lower}–{upper} {unit}", "statement_type": "reported_existing",
        "applicable_from": "2026-10-01", "applicable_through": "2026-10-31",
        "scope_id": data["scope"]["id"], "quantity": {"lower": lower, "upper": upper, "unit": unit},
        "review_status": "accepted", "conflict_group": None,
    }
    data["evidence"].append(evidence)
    basis = next(item for item in data["shelters"][0]["basis"] if item["field"] == "capacity_people")
    basis.update(evidence_ids=[evidence_id], assumption_id=None)
    return evidence, basis


def test_complete_synthetic_case_and_explicit_zero_unknown_distinction():
    result = parse_operational_inputs(FIXTURE.read_bytes())
    assert sum(cohort.people for cohort in result.cohorts) == 100
    assert sum(c.people for c in result.cohorts if c.initial_state == "sheltered") == 20
    assert result.supply_stores[0].initial_water_ml == 0
    assert result.shelters[0].cost_centavos is None
    assert result.pickups[0].staging_limit_people is None
    assert result.cohorts[1].deadline_seconds > result.scenario.horizon_seconds


@pytest.mark.parametrize("value", [None, -1, 1.5, True, "100", float("nan"), float("inf"), 2**53])
def test_quantities_are_required_safe_nonnegative_integers(value):
    data = fixture()
    data["barangays"][0]["population_people"] = value
    with pytest.raises(ValueError):
        parse_operational_inputs(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -181, 181])
def test_coordinates_are_finite_and_bounded(value):
    data = fixture()
    data["pickups"][0]["location"]["longitude"] = value
    with pytest.raises(ValueError):
        parse_operational_inputs(data)


@pytest.mark.parametrize("field", ["crew_id", "distance_budget_mm", "loading_seconds", "availability"])
def test_required_vehicle_resources_are_not_defaulted(field):
    data = fixture()
    del data["vehicles"][0][field]
    with pytest.raises(ValueError):
        parse_operational_inputs(data)


def test_duplicate_population_and_shared_shelters_fail():
    data = fixture()
    duplicate = deepcopy(data["cohorts"][0])
    data["cohorts"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate record IDs"):
        parse_operational_inputs(data)
    duplicate["id"] = str(UUID(int=210))
    with pytest.raises(ValueError, match="population partition"):
        parse_operational_inputs(data)
    data = fixture()
    duplicate = deepcopy(data["shelters"][0])
    duplicate["id"] = str(UUID(int=211))
    data["shelters"].append(duplicate)
    with pytest.raises(ValueError, match="physical resource"):
        parse_operational_inputs(data)


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["cohorts"][1].update(people=41), "partition included population"),
    (lambda d: d["shelters"][0].update(capacity_people=19), "occupants exceed capacity"),
    (lambda d: d["cohorts"][0].update(pickup_id=d["pickups"][0]["id"]), "initial occupants"),
    (lambda d: d["cohorts"][1].update(pickup_id=str(UUID(int=999))), "unknown pickup"),
    (lambda d: d["cohorts"][1].update(pre_shelter_water_store_id=None), "water provision"),
    (lambda d: d["vehicles"][0].update(crew_id=str(UUID(int=999))), "unknown crew"),
    (lambda d: d["crews"][0]["availability"][0].update(end_seconds=3600), "crew window"),
    (lambda d: d["vehicles"][0]["availability"].append({"start_seconds":1,"end_seconds":2}), "overlapping"),
    (lambda d: d["pickups"][0]["location"].update(graph_node_id="missing"), "unknown graph node"),
    (lambda d: d["scope"].update(barangay_ids=[]), "scope barangays"),
    (lambda d: d["cohorts"][1].update(evacuation_mode="walking"), "vehicle"),
    (lambda d: d["scenario"].update(start_utc="2026-10-13T08:00:00+08:00"), "UTC"),
    (lambda d: d["scenario"].update(start_utc="2026-10-13T00:00:00"), "UTC"),
    (lambda d: d["assumptions"][0].update(applicable_through="2026-10-12"), "date/scope"),
])
def test_cross_record_constraints(mutate, message):
    data = fixture()
    mutate(data)
    with pytest.raises(ValueError, match=message):
        parse_operational_inputs(data)


def test_missing_field_basis_or_unknown_support_is_rejected():
    data = fixture()
    data["shelters"][0]["basis"].pop()
    with pytest.raises(ValueError, match="each field exactly once"):
        parse_operational_inputs(data)
    data = fixture()
    data["shelters"][0]["basis"][0]["assumption_id"] = str(UUID(int=999))
    with pytest.raises(ValueError, match="unknown field assumption"):
        parse_operational_inputs(data)


def test_source_quantity_and_historical_date_are_reviewed_not_automatically_current():
    data = fixture()
    source, _ = capacity_source(data)
    parse_operational_inputs(data)
    source["statement_type"] = "historical"
    parse_operational_inputs(data)  # Historical facts can apply to a historical scenario.
    source["applicable_through"] = "2026-10-12"
    with pytest.raises(ValueError, match="stale"):
        parse_operational_inputs(data)


@pytest.mark.parametrize("changes", [
    {"statement_type": "proposed_target"}, {"applicable_from": None},
    {"scope_id": str(UUID(int=999))}, {"review_status": "unreviewed"},
])
def test_proposed_unknown_or_out_of_scope_sources_require_explicit_assumption(changes):
    data = fixture()
    source, basis = capacity_source(data)
    source.update(changes)
    with pytest.raises(ValueError, match="requires assumption"):
        parse_operational_inputs(data)
    basis["assumption_id"] = data["assumptions"][0]["id"]
    parse_operational_inputs(data)


def test_family_range_conversion_is_explicit_and_retains_original_source():
    data = fixture()
    source, basis = capacity_source(data, lower="5", upper="6", unit="families")
    basis["assumption_id"] = data["assumptions"][0]["id"]
    with pytest.raises(ValueError, match="explicit conversion"):
        parse_operational_inputs(data)
    data["shelters"][0]["capacity_people"] = 25
    basis["conversion"] = {
        "evidence_id": source["id"], "selected_source_value": "5", "numerator": 5,
        "denominator": 1, "rounding": "exact", "target_unit": "people", "result": 25,
        "assumption_id": basis["assumption_id"],
    }
    result = parse_operational_inputs(data)
    assert result.evidence[0].quantity.unit == "families"
    assert result.evidence[0].quantity.upper == "6"
    assert result.shelters[0].capacity_people == 25
    basis["conversion"]["selected_source_value"] = "7"
    with pytest.raises(ValueError, match="outside source range"):
        parse_operational_inputs(data)
    basis["conversion"]["selected_source_value"] = "6"
    with pytest.raises(ValueError, match="disagrees"):
        parse_operational_inputs(data)


def test_conflicting_totals_remain_visible_after_explicit_resolution():
    data = fixture()
    source, basis = capacity_source(data, lower="3987", upper="3987")
    source["conflict_group"] = "printed-total"
    second = deepcopy(source)
    second.update(id=str(UUID(int=201)), quantity={"lower":"4087","upper":"4087","unit":"people"})
    data["evidence"].append(second)
    basis["evidence_ids"].append(second["id"])
    basis["assumption_id"] = data["assumptions"][0]["id"]
    with pytest.raises(ValueError, match="conflict requires explicit resolution"):
        parse_operational_inputs(data)
    basis["resolution_note"] = "Retain both conflicting source totals; assume 80 for this synthetic allocation."
    result = parse_operational_inputs(data)
    assert [item.quantity.lower for item in result.evidence] == ["3987", "4087"]
    assert result.shelters[0].capacity_people == 80


def test_physical_page_must_belong_to_immutable_source():
    data = fixture()
    source, _ = capacity_source(data)
    source.update(kind="document", document_id=str(UUID(int=202)), physical_page=3)
    with pytest.raises(ValueError, match="unknown source document"):
        parse_operational_inputs(data)
    data["documents"] = [{
        "id": source["document_id"], "artifact": {"artifact_id":str(UUID(int=203)),"sha256":"a"*64},
        "title":"Synthetic source", "publication_reference":"Local synthetic fixture", "page_count":2,
    }]
    with pytest.raises(ValueError, match="citation exceeds"):
        parse_operational_inputs(data)
    source["physical_page"] = 2
    parse_operational_inputs(data)


def test_artifact_identity_cannot_pin_conflicting_bytes():
    data = fixture()
    data["graph"]["source_snapshot"]["artifact_id"] = data["graph"]["artifact"]["artifact_id"]
    with pytest.raises(ValueError, match="immutable artifact ID has conflicting hashes"):
        parse_operational_inputs(data)


def test_crews_cannot_be_silently_shared_between_vehicles():
    data = fixture()
    second = deepcopy(data["vehicles"][0])
    second.update(id=str(UUID(int=212)), physical_resource_key="another-vehicle")
    data["vehicles"].append(second)
    with pytest.raises(ValueError, match="dedicated crew assignment"):
        parse_operational_inputs(data)


def test_fractional_conversion_requires_explicit_integer_rounding():
    data = fixture()
    source, basis = capacity_source(data, lower="5", upper="6", unit="families")
    basis["assumption_id"] = data["assumptions"][0]["id"]
    data["shelters"][0]["capacity_people"] = 27
    basis["conversion"] = {
        "evidence_id":source["id"], "selected_source_value":"5.5", "numerator":5,
        "denominator":1, "rounding":"exact", "target_unit":"people", "result":27,
        "assumption_id":basis["assumption_id"],
    }
    with pytest.raises(ValueError, match="explicit rounding"):
        parse_operational_inputs(data)
    basis["conversion"]["rounding"] = "floor"
    assert parse_operational_inputs(data).shelters[0].capacity_people == 27
    basis["conversion"].update(rounding="ceil", result=28)
    data["shelters"][0]["capacity_people"] = 28
    assert parse_operational_inputs(data).shelters[0].capacity_people == 28
