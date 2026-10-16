"""Synthetic review transactions with owner isolation and revision checks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from threading import RLock
from typing import Literal

from packages.domain.evidence import (
    RequiredField,
    ReviewAssumption,
    ReviewClaim,
    ReviewDraft,
    ReviewSource,
)
from packages.domain.readiness import Readiness, evaluate
from packages.domain.versions import acknowledge, require_revision, seal

ReviewCase = Literal["synthetic", "qc", "guiguinto"]
DEFAULTS_VERSION = "local-review-defaults.v1"


def synthetic_review(owner: str) -> ReviewDraft:
    """Fictional source-only gap case; never represents a supplied plan."""
    return ReviewDraft(
        workspace_id=f"local-{owner}", revision=0,
        sources=(ReviewSource(source_id="training-plan", title="Fictional training plan",
                              sha256="a" * 64, physical_page_count=2, role="primary",
                              publication_reference="Local synthetic fixture"),),
        claims=(
            ReviewClaim(claim_id="population-12", field="evacuee_people", value="12", unit="PERSON",
                        kind="document", source_id="training-plan", physical_page=1,
                        fragment="12 people in the study area", statement_type="reported_existing",
                        scope_id="training-area", status="accepted"),
            ReviewClaim(claim_id="proposed-water", field="opening_water_ml", value="5000", unit="ML",
                        kind="document", source_id="training-plan", physical_page=2,
                        fragment="Proposed 5,000 mL water purchase", statement_type="proposed_target",
                        scope_id="training-area"),
        ),
        assumptions=(),
        required_fields=(
            RequiredField(field="evacuee_people", unit="PERSON", engine_reason="Population demand is required",
                          remedy="Review a source count or declare a scoped usable assumption",
                          dependent_conclusions=("arrival population",)),
            RequiredField(field="opening_water_ml", unit="ML", engine_reason="Opening water stock is required",
                          remedy="Supply current stock evidence or declare a scoped usable assumption",
                          dependent_conclusions=("water sufficiency", "water shortfall")),
        ),
        scope_id="training-area", scenario_date=date(2026, 10, 14), scenario_reviewed=True,
        pending_annexes=("water inventory annex",),
        unsupported_procedures=("walking", "staged transfers", "resupply"),
    )


def pilot_review(owner: str, case: Literal["qc", "guiguinto"]) -> ReviewDraft:
    """Local, source-only pilot review; source-specific facts were checked in 3.3."""
    qc = case == "qc"
    scope = "qc-study-area-pending" if qc else "guiguinto-extent-pending"
    source_id = "qc-volume-1" if qc else "guiguinto-plan"
    source = ReviewSource(
        source_id=source_id,
        title="Quezon City DRRMP 2021-2027 Volume 1" if qc else "Guiguinto MDRRM Plan 2023-2025",
        sha256=("95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b" if qc
                else "b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95"),
        physical_page_count=112 if qc else 191,
        role="primary", publication_reference="Public supplied plan; Task 3.3 critical-fact review",
    )

    def claim(identifier: str, field: str, value: str, unit: str, page: int, fragment: str,
              statement: Literal["reported_existing", "proposed_target", "historical"],
              *, status: Literal["candidate", "accepted", "contested"] = "accepted",
              conflict: str | None = None) -> ReviewClaim:
        return ReviewClaim(claim_id=identifier, field=field, value=value, unit=unit,
                           kind="document", source_id=source_id, physical_page=page,
                           fragment=fragment, statement_type=statement, scope_id=scope,
                           status=status, conflict_group=conflict,
                           resolution_note="Documentary context only" if status == "accepted" and conflict else None)

    claims: tuple[ReviewClaim, ...]
    annexes: tuple[str, ...]
    if qc:
        claims = (
            claim("qc-historical-population", "city_population_context", "2.86 million", "PERSON", 36,
                  "estimated population of 2.86 million", "historical"),
            claim("qc-flood-priority", "flood_priority_barangays", "Talayan; Damayang Lagi; Roxas; St. Peter; Dona Imelda",
                  "TEXT", 39, "top barangays to prioritize for flood impacts", "reported_existing"),
            claim("qc-proposed-district-shelter", "shelter_capacity_people", "1", "COUNT", 82,
                  "One (1) Permanent Evacuation Area per District", "proposed_target", status="candidate"),
            claim("qc-proposed-water", "opening_water_ml", "unknown", "ML", 84,
                  "portable drinking water stations in designated evacuation centers", "proposed_target",
                  status="candidate"),
        )
        annexes = ("Annex A contingency plans", "Annex B operations center manual",
                   "Annex C prior-plan evaluation", "Annex D capacity building")
    else:
        claims = (
            claim("gui-2020-population", "municipal_population_context", "112889", "PERSON", 38,
                  "total of 112,889 inhabitants", "historical"),
            claim("gui-flood-exposure", "flood_exposed_people", "56516", "PERSON", 80,
                  "A total population of 56,516 and 11,300 households are affected", "reported_existing"),
            claim("gui-flood-households", "flood_exposed_households", "11300", "FAMILY", 80,
                  "A total population of 56,516 and 11,300 households are affected", "reported_existing"),
            claim("gui-family-subtotals", "shelter_capacity_people", "3987", "FAMILY", 121,
                  "2753 84 400 500 50 200", "reported_existing", status="contested",
                  conflict="capacity-grand-total"),
            claim("gui-printed-grand-total", "shelter_capacity_people", "4087", "FAMILY", 121,
                  "TOTAL 4,087", "reported_existing", status="contested",
                  conflict="capacity-grand-total"),
            claim("gui-barangay-hall-pickup", "pickup_policy", "barangay halls", "TEXT", 122,
                  "PICK UP POINTS will be on their Respective Barangay Halls", "reported_existing"),
            claim("gui-gmacc-primary", "primary_center_context", "GMACC", "TEXT", 164,
                  "GMACC is our primary evacuation center", "reported_existing"),
            claim("gui-proposed-rescue-boat", "vehicle_seats", "600000", "PESO", 136,
                  "Procurement of Rescue Boat ... 600,000.00", "proposed_target", status="candidate"),
        )
        annexes = ()
    required = (
        RequiredField(field="evacuee_people", unit="PERSON", engine_reason="Scoped evacuation demand is required",
                      remedy="Review a scoped cohort count or declare a bounded modeling assumption",
                      dependent_conclusions=("evacuated population", "arrival time")),
        RequiredField(field="shelter_capacity_people", unit="PERSON", engine_reason="Usable shelter capacity in people is required",
                      remedy="Resolve facility identity and FAMILY units, or declare a reviewed capacity assumption",
                      dependent_conclusions=("shelter feasibility", "unserved population")),
        RequiredField(field="vehicle_seats", unit="PERSON", engine_reason="Operational transport capacity is required",
                      remedy="Supply current fleet seats or declare a scenario assumption",
                      dependent_conclusions=("trip feasibility", "arrival time")),
        RequiredField(field="opening_water_ml", unit="ML", engine_reason="Opening potable-water stock is required",
                      remedy="Supply dated stock evidence or declare a scoped water assumption",
                      dependent_conclusions=("water sufficiency", "water shortfall")),
    )
    return ReviewDraft(workspace_id=f"local-{owner}-{case}", revision=0,
                       sources=(source,), claims=claims, assumptions=(), required_fields=required,
                       scope_id=scope, scenario_date=date(2026, 10, 14), scenario_reviewed=False,
                       pending_annexes=annexes,
                       unsupported_procedures=("walking", "staged transfers", "resupply"))


def default_assumptions(draft: ReviewDraft) -> tuple[ReviewAssumption, ...]:
    """Visible, illustrative defaults; never applied without a review action."""
    values = {"opening_water_ml": "5000"} if draft.scope_id == "training-area" else {
        "evacuee_people": "100", "shelter_capacity_people": "150",
        "vehicle_seats": "20", "opening_water_ml": "500000",
    }
    return tuple(ReviewAssumption(
        assumption_id=f"{DEFAULTS_VERSION}-{field}", field=field, value=values[field], unit=requirement.unit,
        rationale="Illustrative local modeling default; review or edit before use",
        limitations="Not a measured or documented current input; scope and date require review",
        scope_id=draft.scope_id, applicable_from=draft.scenario_date,
        applicable_through=draft.scenario_date, usable=True,
    ) for requirement in draft.required_fields if (field := requirement.field) in values)


class ReviewService:
    def __init__(self, scope_resolver: Callable[[Literal["qc", "guiguinto"]], str] | None = None) -> None:
        self._drafts: dict[tuple[str, ReviewCase], ReviewDraft] = {}
        self._lock = RLock()
        self._scope_resolver = scope_resolver

    def _initial(self, owner: str, case: ReviewCase) -> ReviewDraft:
        return synthetic_review(owner) if case == "synthetic" else pilot_review(owner, case)

    def _current(self, owner: str, case: ReviewCase) -> ReviewDraft:
        current = self._drafts.setdefault((owner, case), self._initial(owner, case))
        if (case != "synthetic" and self._scope_resolver is not None
                and current.scenario_reviewed):
            latest = self._scope_resolver(case)
            if current.scope_id != latest:
                current = ReviewDraft.model_validate(current.model_copy(update={
                    "revision": current.revision + 1, "scope_id": latest,
                    "scenario_reviewed": False, "assumptions": (), "sealed_hash": None,
                    "acknowledged_hash": None,
                }).model_dump())
                self._drafts[(owner, case)] = current
        return current

    def get(self, owner: str, case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        with self._lock:
            draft = self._current(owner, case)
            return draft, evaluate(draft)

    def _commit(self, owner: str, expected: int,
                change: Callable[[ReviewDraft], ReviewDraft],
                case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        with self._lock:
            current = self._current(owner, case)
            require_revision(current, expected)
            updated = ReviewDraft.model_validate(change(current).model_dump())
            self._drafts[(owner, case)] = updated
            return updated, evaluate(updated)

    def declare_assumption(self, owner: str, expected: int,
                           assumption: ReviewAssumption,
                           case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        def change(current: ReviewDraft) -> ReviewDraft:
            if assumption.scope_id != current.scope_id:
                raise ValueError("Assumption scope differs from the reviewed scenario")
            if assumption.field not in {item.field for item in current.required_fields}:
                raise ValueError("Assumption field is not a required input")
            retained = tuple(item for item in current.assumptions if item.field != assumption.field)
            return current.model_copy(update={"revision": expected + 1,
                "assumptions": retained + (assumption,), "sealed_hash": None, "acknowledged_hash": None})
        return self._commit(owner, expected, change, case)

    def declare_bundle(self, owner: str, expected: int, assumptions: tuple[ReviewAssumption, ...],
                       version: str, case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        if version != DEFAULTS_VERSION:
            raise ValueError("Default version changed; reload before accepting")

        def change(current: ReviewDraft) -> ReviewDraft:
            required = {field.field: field.unit for field in current.required_fields}
            if {item.field for item in assumptions} != set(required) or len(assumptions) != len(required):
                raise ValueError("Review every required default together")
            if any(item.scope_id != current.scope_id or item.unit != required[item.field]
                   or item.applicable_from > current.scenario_date
                   or item.applicable_through < current.scenario_date for item in assumptions):
                raise ValueError("Default scope, date or unit differs from the reviewed case")
            return current.model_copy(update={"revision": expected + 1, "assumptions": assumptions,
                                              "sealed_hash": None, "acknowledged_hash": None})
        return self._commit(owner, expected, change, case)

    def confirm_geography(self, owner: str, expected: int, scope_id: str,
                          case: Literal["qc", "guiguinto"]) -> tuple[ReviewDraft, Readiness]:
        """Bind a server-verified pilot scope and invalidate assumptions for the prior scope."""
        if not scope_id or not scope_id.startswith(("qc-talayan-pilot-cell:",
                                                    "guiguinto-poblacion-pilot-cell:")):
            raise ValueError("Unknown reviewed pilot scope")
        if (case == "qc") != scope_id.startswith("qc-talayan-pilot-cell:"):
            raise ValueError("Geography differs from the selected plan")

        def change(current: ReviewDraft) -> ReviewDraft:
            if current.scope_id == scope_id and current.scenario_reviewed:
                raise ValueError("Geography is already reviewed")
            return current.model_copy(update={
                "revision": expected + 1, "scope_id": scope_id, "scenario_reviewed": True,
                "assumptions": (), "sealed_hash": None, "acknowledged_hash": None,
            })
        return self._commit(owner, expected, change, case)

    def correct(self, owner: str, expected: int, correction: ReviewClaim,
                case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        def change(current: ReviewDraft) -> ReviewDraft:
            if correction.kind != "correction" or correction.status != "accepted":
                raise ValueError("Correction must be a labeled accepted user correction")
            if correction.scope_id != current.scope_id:
                raise ValueError("Correction scope differs from the reviewed scenario")
            claims = tuple(item.model_copy(update={"status": "contested"})
                           if item.field == correction.field and item.status == "accepted" else item
                           for item in current.claims)
            return current.model_copy(update={"revision": expected + 1,
                "claims": claims + (correction,), "sealed_hash": None, "acknowledged_hash": None})
        return self._commit(owner, expected, change, case)

    def seal(self, owner: str, expected: int,
             case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        return self._commit(owner, expected, lambda current: seal(current, expected), case)

    def acknowledge(self, owner: str, expected: int,
                    case: ReviewCase = "synthetic") -> tuple[ReviewDraft, Readiness]:
        def change(current: ReviewDraft) -> ReviewDraft:
            if not evaluate(current).computable or not current.scenario_reviewed:
                raise ValueError("Resolve run inputs and review the scenario before acknowledgment")
            return acknowledge(current, expected)
        return self._commit(owner, expected, change, case)


__all__ = ["DEFAULTS_VERSION", "ReviewCase", "ReviewService", "default_assumptions",
           "pilot_review", "synthetic_review"]
