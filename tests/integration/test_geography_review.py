"""Pinned pilot extents, connectors and optional suggestion contract."""

import json
from pathlib import Path

import pytest

from packages.adapters.geo.geocoding import parse_saved_suggestions
from packages.application.review import ReviewService, default_assumptions
from packages.domain.versions import RevisionConflict
from services.api.geography import pilot_geography

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case,expected_seconds,expected_connectors", [
    ("qc", 211, (219, 11)),
    ("guiguinto", 64, (24, 25)),
])
def test_pilot_area_has_route_boundary_and_explicit_scope(
    case: str, expected_seconds: int, expected_connectors: tuple[int, int],
) -> None:
    snapshot = pilot_geography(case)  # type: ignore[arg-type]
    pinned = json.loads((ROOT / "release/validation/geography/pilot-areas.json").read_text())
    assert snapshot.model_dump(mode="json") == {
        key: value for key, value in pinned["cases"][case].items() if key != "coordinate_basis"}
    assert snapshot.blockers == ()
    assert snapshot.route_status == "found" and snapshot.route_seconds == expected_seconds
    assert tuple(item.distance_m for item in snapshot.area.connectors) == expected_connectors
    assert snapshot.area.boundary_lon_lat[0] == snapshot.area.boundary_lon_lat[-1]
    assert snapshot.area.members[0].population == 100
    assert snapshot.area.members[1].included is False
    assert all("assumed" in item.source for item in snapshot.area.connectors)
    assert "not an administrative barangay boundary" in snapshot.area.cross_boundary_assumptions[2]


def test_area_confirmation_replaces_pending_scope_and_invalidates_assumptions() -> None:
    service = ReviewService()
    initial, _ = service.get("fixture", "qc")
    draft, _ = service.declare_bundle("fixture", initial.revision, default_assumptions(initial),
                                      "local-review-defaults.v1", "qc")
    assert draft.assumptions and not draft.scenario_reviewed
    geography = pilot_geography("qc")
    reviewed, readiness = service.confirm_geography("fixture", draft.revision,
                                                    geography.scope_id, "qc")
    assert reviewed.scope_id == geography.scope_id and reviewed.scenario_reviewed
    assert reviewed.assumptions == () and reviewed.sealed_hash is None
    assert len(readiness.gaps) == 4 and not readiness.ready_to_run
    with pytest.raises(ValueError, match="differs"):
        service.confirm_geography("fixture", reviewed.revision,
                                  pilot_geography("guiguinto").scope_id, "qc")


def test_changed_scope_hash_reopens_review_and_rejects_stale_revision() -> None:
    scope = [pilot_geography("qc").scope_id]
    service = ReviewService(scope_resolver=lambda case: scope[0])
    reviewed, _ = service.confirm_geography("fixture", 0, scope[0], "qc")
    reviewed, _ = service.declare_bundle("fixture", reviewed.revision,
                                          default_assumptions(reviewed),
                                          "local-review-defaults.v1", "qc")
    scope[0] = "qc-talayan-pilot-cell:" + "f" * 16
    changed, readiness = service.get("fixture", "qc")
    assert changed.scope_id == scope[0] and not changed.scenario_reviewed
    assert changed.assumptions == () and changed.revision == reviewed.revision + 1
    assert not readiness.ready_to_run
    with pytest.raises(RevisionConflict):
        service.declare_bundle("fixture", reviewed.revision, default_assumptions(reviewed),
                               "local-review-defaults.v1", "qc")


def test_saved_geoapify_suggestions_need_manual_review_and_finite_coordinates() -> None:
    payload = json.loads((ROOT / "tests/fixtures/geocoding/talayan-suggestions.json").read_text())
    suggestions = parse_saved_suggestions(payload)
    assert [item.label for item in suggestions] == [
        "Talayan, Quezon City, Philippines", "Nearby Quezon City result"]
    payload["features"][0]["geometry"]["coordinates"][0] = float("nan")
    with pytest.raises(ValueError, match="coordinate"):
        parse_saved_suggestions(payload)
