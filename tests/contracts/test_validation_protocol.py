"""Check that the proposed validation split and hand-calculated references are coherent."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "release/validation/protocol.json"
CASES = ROOT / "tests/fixtures/validation/cases.json"
DOCUMENT = ROOT / "docs/validation-protocol.md"


def read_json(path: Path) -> dict[str, object]:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    return result


def test_protocol_prespecifies_metrics_and_separates_splits() -> None:
    protocol = read_json(PROTOCOL)
    fixtures = read_json(CASES)
    assert protocol["schema_version"] == "validation.protocol.v2"
    assert protocol["protocol_version"] == "0.2.0"
    assert fixtures["schema_version"] == "validation.synthetic_cases.v1"

    benchmark = protocol["benchmark_classes"][0]
    assert benchmark["fixture_path"] == CASES.relative_to(ROOT).as_posix()
    assert benchmark["tolerance_status"] == "exact_synthetic_arithmetic"
    assert benchmark["tolerances"] == {
        "arrival_time_seconds": 0,
        "evacuated_people": 0,
        "water_shortfall_ml": 0,
    }

    cases = fixtures["cases"]
    by_id = {case["id"]: case for case in cases}
    assert len(by_id) == len(cases)
    calibration = set(benchmark["calibration_case_ids"])
    references = set(benchmark["reference_case_ids"])
    assert calibration and references and calibration.isdisjoint(references)
    assert calibration | references == set(by_id)
    assert all(by_id[case_id]["split"] == "calibration" for case_id in calibration)
    assert all(by_id[case_id]["split"] == "reference" for case_id in references)

    document = DOCUMENT.read_text(encoding="utf-8")
    for term in ("Arrival time", "Evacuated population", "Water shortfall", "held-out", "critical"):
        assert term in document


def test_synthetic_references_are_hand_calculable_and_conservative() -> None:
    cases = read_json(CASES)["cases"]
    for case in cases:
        inputs = case["inputs"]
        reference = case["reference"]
        assert case["derivation"]
        assert all(type(value) is int and value >= 0 for value in inputs.values())
        arrivals = min(
            inputs["cohort_people"],
            inputs["vehicle_seats"],
            inputs["shelter_spaces"],
        ) if inputs["travel_time_seconds"] <= inputs["horizon_seconds"] else 0
        expected_time = inputs["travel_time_seconds"] if arrivals else None
        required = arrivals * inputs["arrival_water_need_ml_per_person"]
        used = min(required, inputs["shelter_water_ml"])
        assert reference == {
            "arrival_time_seconds": expected_time,
            "evacuated_people": arrivals,
            "unserved_people": inputs["cohort_people"] - arrivals,
            "water_required_ml": required,
            "water_used_ml": used,
            "water_shortfall_ml": required - used,
        }
        assert reference["evacuated_people"] + reference["unserved_people"] == inputs["cohort_people"]
        assert reference["water_used_ml"] <= inputs["shelter_water_ml"]


def test_frozen_protocol_pins_inputs_and_requires_no_external_approval() -> None:
    protocol = read_json(PROTOCOL)
    assert protocol["freeze_status"] == "frozen"
    assert protocol["frozen_on"] == "2026-10-14"
    assert protocol["reference_scoring"] == "not_started"
    assert protocol["missing_results"] == "unscored_not_passed"
    assert protocol["required_external_inputs"] == ["pdf", "textual_location_for_osm"]
    assert not {"approval_requirements", "candidate_field_evidence",
                "representative_reference"} & protocol.keys()
    assert protocol["benchmark_classes"][0]["fixture_sha256"] == (
        hashlib.sha256(CASES.read_bytes()).hexdigest()
    )
    expected_hash = protocol.pop("content_sha256")
    canonical = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == expected_hash
