"""Preparatory changes preserve immutable source lineage and stock accounting."""

import pytest

from packages.domain.proposals import (
    AddVehicle,
    AddWater,
    BaselineResources,
    DeferredOperation,
    MoveVehicleStart,
    RedistributeWater,
    ShelterPreference,
    apply_variant,
)


def baseline() -> BaselineResources:
    return BaselineResources(
        "a" * 64, ("b" * 64,), (("store", 100), ("shelter", 0)),
        (("vehicle", "depot"),), ("shelter",),
    )


def test_variant_preserves_source_and_baseline_with_conserved_redistribution() -> None:
    source = baseline()
    changed = apply_variant(source, (
        RedistributeWater("store", "shelter", 30),
        MoveVehicleStart("vehicle", "pickup"), ShelterPreference("shelter", 1),
    ))
    assert changed.baseline_hash == source.baseline_hash
    assert changed.source_hashes == source.source_hashes
    assert changed.water_stores == (("shelter", 30), ("store", 70))
    assert sum(value for _, value in changed.water_stores) == 100
    assert source.water_stores == (("store", 100), ("shelter", 0))
    assert changed.variant_hash == apply_variant(source, (
        RedistributeWater("store", "shelter", 30),
        MoveVehicleStart("vehicle", "pickup"), ShelterPreference("shelter", 1),
    )).variant_hash


def test_declared_additions_are_counted_and_deferred_actions_fail() -> None:
    changed = apply_variant(baseline(), (
        AddWater("shelter", 20, "synthetic-resource"),
        AddVehicle("new", "depot", 4, "synthetic-resource"),
    ))
    assert sum(value for _, value in changed.water_stores) == 120
    assert changed.declared_added_water_ml == 20
    assert changed.added_vehicles[0].vehicle_id == "new"
    with pytest.raises(TypeError, match="deferred"):
        apply_variant(baseline(), (DeferredOperation("in_scenario_resupply"),))
    with pytest.raises(ValueError, match="redistribution"):
        apply_variant(baseline(), (RedistributeWater("store", "shelter", 101),))
    with pytest.raises(ValueError, match="new ID"):
        apply_variant(baseline(), (AddVehicle("vehicle", "depot", 4, "source"),))
