"""Milestone A rejects missing/altered engineering evidence without external signoff.

The legacy filename is retained for existing task/check references; these tests
verify the evidence manifest, not blind held-out or empirical model outcomes.
"""

import hashlib
import json
from pathlib import Path

from packages.simulation.kernel.events import Event, EventQueue, Phase
from packages.simulation.kernel.population import (
    PopulationLedger,
    PopulationSlice,
    PopulationState,
)
from packages.simulation.kernel.resources import (
    CrewResource,
    ResourceLedger,
    ShelterResource,
    TripPlan,
    VehicleResource,
    Window,
)
from packages.simulation.kernel.water import WaterCohort, WaterLedger, WaterStore
from packages.simulation.metrics.population import at_horizon
from packages.simulation.policies.feasibility import check_trip, dispatch
from packages.simulation.routing.reference import RouteResult
from scripts.verify_release import REQUIRED_A, verify_a

ROOT = Path(__file__).resolve().parents[2]


def score_reference_case(row: dict[str, object]) -> dict[str, int | None]:
    """Score the frozen arithmetic fixture with real resource/population/water ledgers.

    The fixture defines a separate one-day water quota *after arrival*. This
    check applies that quota to admitted people, not to waiting people.
    """
    values = row["inputs"]
    assert isinstance(values, dict)
    people = int(values["cohort_people"])
    seats = int(values["vehicle_seats"])
    spaces = int(values["shelter_spaces"])
    travel = int(values["travel_time_seconds"])
    horizon = int(values["horizon_seconds"])
    stock = int(values["shelter_water_ml"])
    quota = int(values["arrival_water_need_ml_per_person"])

    def resources() -> ResourceLedger:
        return ResourceLedger(
            (VehicleResource("vehicle", "crew", seats, (), (Window(0, horizon + travel + 2),),
                             1_000, "pickup", False),),
            (CrewResource("crew", (Window(0, horizon + travel + 2),)),),
            (ShelterResource("shelter", spaces, 0, ()),),
        )

    selected = 0
    for count in range(people, 0, -1):
        candidate_population = PopulationLedger((PopulationSlice(
            "trip", "source", count, PopulationState.WAITING, location_id="pickup",
        ),))
        plan = TripPlan("trip", "trip", count, (), "vehicle", "shelter", 0,
                        RouteResult("found", (), 0, 0), 1,
                        RouteResult("found", ("edge",), travel - 2, 100), 1)
        if check_trip(plan, resources(), candidate_population).feasible:
            selected = count
            break
    assert selected > 0
    slices = [PopulationSlice("trip", "source", selected, PopulationState.WAITING,
                              location_id="pickup")]
    if people > selected:
        slices.append(PopulationSlice("waiting", "source", people - selected,
                                      PopulationState.WAITING, location_id="pickup"))
    population = PopulationLedger(slices)
    ledger = resources()
    plan = TripPlan("trip", "trip", selected, (), "vehicle", "shelter", 0,
                    RouteResult("found", (), 0, 0), 1,
                    RouteResult("found", ("edge",), travel - 2, 100), 1)
    dispatch(plan, ledger, population)
    ledger.pickup("trip", 0, population)
    queue = EventQueue(horizon)
    queue.schedule(1, Phase.COMPLETION, "depart")
    queue.schedule(travel - 1, Phase.COMPLETION, "arrive")
    queue.schedule(travel, Phase.COMPLETION, "admit")

    def handle(event: Event, _: EventQueue) -> None:
        if event.kind == "depart":
            ledger.depart("trip", event.time_seconds, population)
        elif event.kind == "arrive":
            ledger.travel_edge("trip", 100, edge_id="edge", progress_mm=0,
                               location_id="shelter")
            ledger.begin_unload("trip", event.time_seconds, population)
        elif event.kind == "admit":
            assert ledger.admit("trip", event.time_seconds, population)
        population.assert_conserved()
        ledger.assert_invariants()

    queue.run(handle)
    metrics = at_horizon(population, horizon)
    admitted = metrics.on_time_arrivals
    if admitted:
        water = WaterLedger((WaterStore("shelter", stock),),
                            (WaterCohort("admitted", admitted, quota, "shelter"),))
        water.advance(86_400)
        balance = water.store("shelter")
        required = water.cohort("admitted").demand_ml
        used = balance.consumed_ml
        shortfall = balance.unmet_ml
    else:
        required = used = shortfall = 0
    return {"arrival_time_seconds": travel if admitted else None,
            "evacuated_people": admitted, "unserved_people": metrics.unserved_demand,
            "water_required_ml": required, "water_used_ml": used,
            "water_shortfall_ml": shortfall}


def test_frozen_arithmetic_references_score_exactly() -> None:
    fixture = ROOT / "tests/fixtures/validation/cases.json"
    protocol = json.loads((ROOT / "release/validation/protocol.json").read_text())
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
        protocol["benchmark_classes"][0]["fixture_sha256"])
    cases = json.loads(fixture.read_text())["cases"]
    scored = {row["id"]: score_reference_case(row) for row in cases}
    assert all(scored[row["id"]] == row["reference"] for row in cases)
    artifact = json.loads((ROOT / "release/validation/milestone-a/reference-scores.json").read_text())
    assert artifact["fixture_sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert artifact["scores"] == scored
    assert artifact["tolerances"] == protocol["benchmark_classes"][0]["tolerances"]


def test_current_milestone_a_manifest_is_complete_and_coherent() -> None:
    manifest = json.loads((ROOT / "release/acceptance.json").read_text(encoding="utf-8"))
    assert manifest["milestone_a"]["status"] == "accepted"
    assert verify_a(manifest, ROOT) == []


def test_missing_evidence_does_not_accept() -> None:
    issues = verify_a({"milestone_a": {"status": "incomplete", "evidence": {}}})
    assert len(issues) == len(REQUIRED_A) + 1
    assert "missing evidence: reference_scores" in issues
    assert "missing evidence: engineering_discrepancies" in issues
    assert "independent_review" not in REQUIRED_A


def test_checksums_and_discrepancy_record_are_required(tmp_path: Path) -> None:
    records = {}
    for key in REQUIRED_A:
        evidence = tmp_path / f"{key}.json"
        evidence.write_text('{"status":"example"}')
        records[key] = {"path": evidence.name,
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    issues = verify_a({"milestone_a": {"status": "accepted", "evidence": records}}, tmp_path)
    assert issues == ["engineering evidence needs dated scope and no unresolved critical issues"]
    evidence = tmp_path / "engineering_discrepancies.json"
    evidence.write_text(json.dumps({
        "scope": "input_based_engineering", "checked_on": "2026-10-14",
        "unresolved_critical": [],
    }))
    records["engineering_discrepancies"]["sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    # No reviewer identity, credentials, field observation or participant record.
    assert verify_a({"milestone_a": {"status": "accepted", "evidence": records}}, tmp_path) == []
    (tmp_path / "reference_scores.json").write_text("changed")
    issues = verify_a({"milestone_a": {"status": "accepted", "evidence": records}}, tmp_path)
    assert "evidence checksum mismatch: reference_scores" in issues


def test_unresolved_critical_issue_blocks_acceptance(tmp_path: Path) -> None:
    evidence = tmp_path / "discrepancies.json"
    evidence.write_text(json.dumps({
        "scope": "input_based_engineering", "checked_on": "2026-10-14",
        "unresolved_critical": ["Population is not conserved"],
    }))
    record = {"path": evidence.name, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    issues = verify_a({"milestone_a": {"status": "accepted", "evidence": {
        "engineering_discrepancies": record,
    }}}, tmp_path)
    assert "engineering evidence needs dated scope and no unresolved critical issues" in issues
