"""Pure, deterministic one-trip calculation for the synthetic walking skeleton."""

from packages.contracts.skeleton import SkeletonCase, SkeletonResult


def calculate_skeleton(case: SkeletonCase) -> SkeletonResult:
    """Count one direct trip; future engine tasks replace this bounded POC model."""
    arrived = (
        min(case.cohort_people, case.vehicle_seats, case.shelter_spaces)
        if case.travel_time_seconds <= case.horizon_seconds
        else 0
    )
    water_required = arrived * case.arrival_water_need_ml_per_person
    water_used = min(water_required, case.shelter_water_ml)
    result = SkeletonResult(
        schema_version="skeleton.result.v1",
        case_id=case.case_id,
        initial_people=case.cohort_people,
        arrived_people=arrived,
        unserved_people=case.cohort_people - arrived,
        arrival_time_seconds=case.travel_time_seconds if arrived else None,
        water_required_ml=water_required,
        water_used_ml=water_used,
        water_shortfall_ml=water_required - water_used,
        water_sufficient_people=min(
            arrived, case.shelter_water_ml // case.arrival_water_need_ml_per_person
        ),
        water_remaining_ml=case.shelter_water_ml - water_used,
        source_label=case.source_label,
        assumption_label=case.assumption_label,
    )
    assert result.arrived_people + result.unserved_people == result.initial_people
    return result
