"""Synthetic evidence review, revision and run-readiness proof."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from packages.application.review import (
    DEFAULTS_VERSION,
    ReviewService,
    default_assumptions,
    pilot_review,
    synthetic_review,
)
from packages.domain.evidence import (
    ReviewAssumption,
    ReviewClaim,
    ReviewConversion,
    ReviewDraft,
    ReviewSource,
)
from packages.domain.readiness import evaluate
from packages.domain.versions import RevisionConflict


def assumption(value: str = "5000") -> ReviewAssumption:
    return ReviewAssumption(assumption_id="declared-water", field="opening_water_ml", value=value,
                            unit="ML", rationale="Exploratory opening stock", limitations="Not confirmed inventory",
                            scope_id="training-area", applicable_from=date(2026, 10, 14),
                            applicable_through=date(2026, 10, 14), usable=True)


def checked(draft: ReviewDraft, **changes: object) -> ReviewDraft:
    return ReviewDraft.model_validate({**draft.model_dump(), **changes})


def test_source_only_gap_remains_reviewable_and_specific() -> None:
    result = evaluate(synthetic_review("owner-a"))
    assert result.document_review_available and not result.computable
    assert [gap.field for gap in result.source_only_gaps] == ["opening_water_ml"]
    gap = result.gaps[0]
    assert "proposed" in gap.reason.lower()
    assert gap.engine_reason and gap.remedy
    assert gap.dependent_conclusions == ("water sufficiency", "water shortfall")
    assert "Missing annex: water inventory annex" in result.documentation_gaps
    assert "Procedure not modeled: walking" in result.documentation_gaps


def test_assumption_seal_and_acknowledgment_enable_readiness() -> None:
    service = ReviewService()
    draft, result = service.declare_assumption("owner-a", 0, assumption())
    assert result.computable and not result.ready_to_run
    assert [gap.field for gap in result.source_only_gaps] == ["opening_water_ml"]
    draft, result = service.seal("owner-a", draft.revision)
    assert not result.ready_to_run
    draft, result = service.acknowledge("owner-a", draft.revision)
    assert result.ready_to_run
    assert draft.sealed_hash == draft.acknowledged_hash == result.material_hash


def test_material_edit_invalidates_personal_acknowledgment() -> None:
    service = ReviewService()
    draft, _ = service.declare_assumption("owner-a", 0, assumption())
    draft, _ = service.seal("owner-a", draft.revision)
    draft, ready = service.acknowledge("owner-a", draft.revision)
    changed, result = service.declare_assumption("owner-a", draft.revision, assumption("6000"))
    assert changed.acknowledged_hash is None and changed.sealed_hash is None
    assert result.computable and not result.ready_to_run
    assert result.material_hash != ready.material_hash


def test_revision_conflict_and_owner_isolation() -> None:
    service = ReviewService()
    service.declare_assumption("owner-a", 0, assumption())
    with pytest.raises(RevisionConflict):
        service.declare_assumption("owner-a", 0, assumption("6000"))
    other, result = service.get("owner-b")
    assert other.revision == 0 and not other.assumptions and not result.computable


def test_correction_keeps_source_and_reopens_review() -> None:
    service = ReviewService()
    draft, _ = service.declare_assumption("owner-a", 0, assumption())
    draft, _ = service.seal("owner-a", draft.revision)
    draft, _ = service.acknowledge("owner-a", draft.revision)
    correction = ReviewClaim(claim_id="corrected-population", field="evacuee_people", value="13",
                             unit="PERSON", kind="correction", fragment="User corrected the count",
                             statement_type="reported_existing", scope_id="training-area", status="accepted")
    changed, result = service.correct("owner-a", draft.revision, correction)
    assert changed.claims[0].status == "contested" and changed.claims[-1].kind == "correction"
    assert not result.ready_to_run
    assert result.source_only_gaps[0].field == "evacuee_people"


def test_family_range_requires_explicit_conversion_or_assumption() -> None:
    draft = synthetic_review("owner-a")
    family = ReviewClaim(claim_id="families", field="evacuee_people", value="5-6", unit="FAMILY",
                         kind="document", source_id="training-plan", physical_page=1,
                         fragment="5-6 FAMILY", statement_type="reported_existing",
                         scope_id="training-area", status="accepted")
    draft = checked(draft, claims=(family, draft.claims[1]))
    assert evaluate(draft).gaps[0].reason.startswith("Source units")
    converted = ReviewAssumption(assumption_id="family-conversion", field="evacuee_people",
        value="30", unit="PERSON", rationale="Select upper family count and five persons per family",
        limitations="Household size is assumed", scope_id="training-area",
        applicable_from=date(2026, 10, 14), applicable_through=date(2026, 10, 14), usable=True,
        conversion=ReviewConversion(source_claim_id="families", selected_source_value="6",
                                    numerator=5, denominator=1, rounding="exact", result=30))
    draft = checked(draft, assumptions=(converted,))
    assert [gap.field for gap in evaluate(draft).gaps] == ["opening_water_ml"]
    with pytest.raises(ValidationError):
        checked(draft, assumptions=(converted.model_copy(update={"value": "35"}),))


def test_historical_date_and_proposed_values_never_silently_become_current() -> None:
    draft = synthetic_review("owner-a")
    historic = ReviewClaim(claim_id="historic-water", field="opening_water_ml", value="8000", unit="ML",
                           kind="document", source_id="training-plan", physical_page=2,
                           fragment="Historic water opening stock", statement_type="historical",
                           applicable_from=date(2024, 1, 1), applicable_through=date(2024, 12, 31),
                           scope_id="training-area", status="accepted")
    draft = checked(draft, claims=(draft.claims[0], historic))
    assert not evaluate(draft).computable
    assert evaluate(checked(draft, scenario_date=date(2024, 6, 1))).computable


def test_supplement_keeps_distinct_source_identity_and_source_only_gap() -> None:
    draft = synthetic_review("owner-a")
    supplement = ReviewSource(source_id="inventory-annex", title="Fictional inventory annex",
                              sha256="b" * 64, physical_page_count=1, role="supplement",
                              publication_reference="Local synthetic fixture")
    stock = ReviewClaim(claim_id="annex-water", field="opening_water_ml", value="9000", unit="ML",
                        kind="external_evidence", source_id="inventory-annex", physical_page=1,
                        fragment="Opening stock 9,000 mL", statement_type="reported_existing",
                        scope_id="training-area", status="accepted")
    result = evaluate(checked(draft, sources=draft.sources + (supplement,), claims=draft.claims + (stock,)))
    assert result.computable
    assert [gap.field for gap in result.source_only_gaps] == ["opening_water_ml"]


def test_blank_is_unknown_but_explicit_zero_can_be_reviewed() -> None:
    draft = synthetic_review("owner-a")
    zero = ReviewClaim(claim_id="zero-water", field="opening_water_ml", value="0", unit="ML",
                       kind="document", source_id="training-plan", physical_page=2,
                       fragment="No opening water stock", statement_type="reported_existing",
                       scope_id="training-area", status="accepted")
    assert not evaluate(draft).computable
    assert evaluate(checked(draft, claims=draft.claims + (zero,))).computable


def test_source_range_cannot_silently_become_one_operational_value() -> None:
    draft = synthetic_review("owner-a")
    ranged = draft.claims[0].model_copy(update={"value": "5-6", "fragment": "5-6 people"})
    result = evaluate(checked(draft, claims=(ranged, draft.claims[1])))
    assert result.gaps[0].field == "evacuee_people"
    assert "range" in result.gaps[0].reason.lower()


def test_competing_values_require_resolution_and_are_not_summed() -> None:
    draft = synthetic_review("owner-a")
    first = ReviewClaim(claim_id="count-a", field="evacuee_people", entity_id="shared-center",
                        value="3987", unit="PERSON", kind="document", source_id="training-plan",
                        physical_page=1, fragment="Subtotal 3,987", statement_type="reported_existing",
                        scope_id="training-area", status="accepted")
    second = first.model_copy(update={"claim_id": "count-b", "value": "4087", "fragment": "Total 4,087"})
    result = evaluate(checked(draft, claims=(first, second, draft.claims[1])))
    assert result.gaps[0].field == "evacuee_people" and "Competing" in result.gaps[0].reason
    assert not result.computable


def test_unreviewed_competing_candidate_cannot_be_ignored() -> None:
    draft = synthetic_review("owner-a")
    competing = draft.claims[0].model_copy(update={"claim_id": "other-population", "value": "13",
                                           "status": "candidate"})
    result = evaluate(checked(draft, claims=draft.claims + (competing,)))
    assert result.gaps[0].field == "evacuee_people"
    assert "Competing" in result.gaps[0].reason


def test_missing_document_and_invalid_citation_are_rejected() -> None:
    draft = synthetic_review("owner-a")
    with pytest.raises(ValidationError):
        checked(draft, claims=(draft.claims[0].model_copy(update={"physical_page": 99}),))
    with pytest.raises(ValidationError):
        ReviewClaim(claim_id="blank", field="x", value="", unit="PERSON", kind="user_assertion",
                    fragment="blank", statement_type="reported_existing", scope_id="training-area")


def test_unreviewed_scenario_stays_nonready() -> None:
    draft, _ = ReviewService().declare_assumption("owner-a", 0, assumption())
    result = evaluate(checked(draft, scenario_reviewed=False))
    assert result.computable and not result.ready_to_run


def test_unusable_numeric_assumption_cannot_enable_a_run() -> None:
    with pytest.raises(ValidationError):
        assumption("unknown")


def test_pilot_source_only_cases_keep_distinct_pages_and_operational_gaps() -> None:
    qc = pilot_review("reviewer", "qc")
    guiguinto = pilot_review("reviewer", "guiguinto")
    assert qc.sources[0].physical_page_count == 112
    assert guiguinto.sources[0].physical_page_count == 191
    assert qc.sources[0].sha256 != guiguinto.sources[0].sha256
    assert {claim.physical_page for claim in qc.claims} >= {36, 39, 82, 84}
    assert {claim.physical_page for claim in guiguinto.claims} >= {38, 80, 121, 122, 136, 164}
    assert len(qc.pending_annexes) == 4
    assert all(gap.engine_reason and gap.remedy and gap.dependent_conclusions
               for gap in evaluate(qc).source_only_gaps)
    assert {gap.field for gap in evaluate(qc).source_only_gaps} == {
        "evacuee_people", "shelter_capacity_people", "vehicle_seats", "opening_water_ml"
    }
    assert {gap.field for gap in evaluate(guiguinto).source_only_gaps} == {
        "evacuee_people", "shelter_capacity_people", "vehicle_seats", "opening_water_ml"
    }
    assert not evaluate(qc).computable and not evaluate(guiguinto).computable
    assert {claim.value for claim in guiguinto.claims if claim.conflict_group == "capacity-grand-total"} == {
        "3987", "4087"
    }


def test_pilot_review_isolated_from_training_and_needs_location_review() -> None:
    service = ReviewService()
    qc, _ = service.get("same-owner", "qc")
    guiguinto, _ = service.get("same-owner", "guiguinto")
    synthetic, _ = service.get("same-owner")
    assert len({qc.workspace_id, guiguinto.workspace_id, synthetic.workspace_id}) == 3
    pilot_assumption = ReviewAssumption(
        assumption_id="qc-opening-water", field="opening_water_ml", value="5000", unit="ML",
        rationale="Exploratory stock", limitations="Not observed inventory", scope_id=qc.scope_id,
        applicable_from=qc.scenario_date, applicable_through=qc.scenario_date, usable=True,
    )
    changed, readiness = service.declare_assumption("same-owner", 0, pilot_assumption, "qc")
    assert changed.revision == 1 and not readiness.ready_to_run
    assert len(readiness.source_only_gaps) == 4 and len(readiness.gaps) == 3
    assert service.get("same-owner", "guiguinto")[0].revision == 0
    assert service.get("same-owner")[0].revision == 0


def test_versioned_defaults_apply_atomically_and_preserve_source_only_gaps() -> None:
    service = ReviewService()
    draft, _ = service.get("owner", "qc")
    defaults = default_assumptions(draft)
    assert {item.field for item in defaults} == {item.field for item in draft.required_fields}
    assert not draft.assumptions
    edited = tuple(item.model_copy(update={"value": "200"}) if item.field == "evacuee_people"
                   else item for item in defaults)
    with pytest.raises(ValueError, match="Review every required"):
        service.declare_bundle("owner", 0, edited[:-1], DEFAULTS_VERSION, "qc")
    with pytest.raises(ValueError, match="version changed"):
        service.declare_bundle("owner", 0, edited, "old-version", "qc")
    changed, result = service.declare_bundle("owner", 0, edited, DEFAULTS_VERSION, "qc")
    assert changed.revision == 1
    assert {item.field: item.value for item in changed.assumptions}["evacuee_people"] == "200"
    assert result.computable and not result.ready_to_run
    assert len(result.source_only_gaps) == 4
    assert service.get("owner", "guiguinto")[0].revision == 0
