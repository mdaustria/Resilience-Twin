"""Typed preparatory variants over copied, immutable baseline resource facts."""

import hashlib
from dataclasses import asdict, dataclass
from typing import Literal

from packages.contracts.checkpoints import canonical_json


@dataclass(frozen=True)
class BaselineResources:
    baseline_hash: str
    source_hashes: tuple[str, ...]
    water_stores: tuple[tuple[str, int], ...]
    vehicle_starts: tuple[tuple[str, str], ...]
    shelter_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (len(self.baseline_hash) != 64 or
                any(len(item) != 64 for item in self.source_hashes)):
            raise ValueError("baseline and source hashes are required")
        for items in (self.water_stores, self.vehicle_starts):
            if len({item[0] for item in items}) != len(items):
                raise ValueError("duplicate resource ID")
        if any(type(amount) is not int or amount < 0 for _, amount in self.water_stores):
            raise ValueError("water inventory must be nonnegative integer milliliters")


@dataclass(frozen=True)
class RedistributeWater:
    from_store_id: str
    to_store_id: str
    amount_ml: int


@dataclass(frozen=True)
class AddWater:
    store_id: str
    amount_ml: int
    source_reference: str


@dataclass(frozen=True)
class MoveVehicleStart:
    vehicle_id: str
    node_id: str


@dataclass(frozen=True)
class ShelterPreference:
    shelter_id: str
    rank: int


@dataclass(frozen=True)
class AddVehicle:
    vehicle_id: str
    start_node_id: str
    seats: int
    source_reference: str


@dataclass(frozen=True)
class DeferredOperation:
    kind: Literal["in_scenario_resupply", "refuel"]


Operation = (RedistributeWater | AddWater | MoveVehicleStart | ShelterPreference
             | AddVehicle | DeferredOperation)


@dataclass(frozen=True)
class Variant:
    baseline_hash: str
    source_hashes: tuple[str, ...]
    variant_hash: str
    water_stores: tuple[tuple[str, int], ...]
    vehicle_starts: tuple[tuple[str, str], ...]
    shelter_preferences: tuple[tuple[str, int], ...]
    added_vehicles: tuple[AddVehicle, ...]
    declared_added_water_ml: int


def apply_variant(baseline: BaselineResources, operations: tuple[Operation, ...]) -> Variant:
    water = dict(baseline.water_stores)
    vehicles = dict(baseline.vehicle_starts)
    preferences: dict[str, int] = {}
    added: list[AddVehicle] = []
    declared_added_ml = 0
    original_total = sum(water.values())
    for operation in operations:
        if isinstance(operation, RedistributeWater):
            if (type(operation.amount_ml) is not int or operation.amount_ml <= 0
                    or operation.from_store_id == operation.to_store_id
                    or operation.from_store_id not in water
                    or operation.to_store_id not in water
                    or water[operation.from_store_id] < operation.amount_ml):
                raise ValueError("invalid or nonconserved water redistribution")
            water[operation.from_store_id] -= operation.amount_ml
            water[operation.to_store_id] += operation.amount_ml
        elif isinstance(operation, AddWater):
            if (operation.store_id not in water or type(operation.amount_ml) is not int
                    or operation.amount_ml <= 0 or not operation.source_reference):
                raise ValueError("water addition needs a known store and declared source")
            water[operation.store_id] += operation.amount_ml
            declared_added_ml += operation.amount_ml
        elif isinstance(operation, MoveVehicleStart):
            if operation.vehicle_id not in vehicles or not operation.node_id:
                raise ValueError("vehicle move needs a known vehicle and reviewed node")
            vehicles[operation.vehicle_id] = operation.node_id
        elif isinstance(operation, ShelterPreference):
            if (operation.shelter_id not in baseline.shelter_ids
                    or type(operation.rank) is not int or operation.rank < 0):
                raise ValueError("invalid shelter preference")
            preferences[operation.shelter_id] = operation.rank
        elif isinstance(operation, AddVehicle):
            if (not operation.vehicle_id or operation.vehicle_id in vehicles
                    or not operation.start_node_id or type(operation.seats) is not int
                    or operation.seats <= 0 or not operation.source_reference):
                raise ValueError("vehicle addition needs new ID, seats and declared source")
            vehicles[operation.vehicle_id] = operation.start_node_id
            added.append(operation)
        elif isinstance(operation, DeferredOperation):
            raise TypeError("in-scenario resupply and refueling are deferred")
        else:
            raise TypeError("unknown proposal operation")
    if sum(water.values()) != original_total + declared_added_ml:
        raise AssertionError("water inventory conservation failed")
    water_stores = tuple(sorted(water.items()))
    vehicle_starts = tuple(sorted(vehicles.items()))
    shelter_preferences = tuple(sorted(preferences.items()))
    content = {"baseline_hash": baseline.baseline_hash,
               "source_hashes": baseline.source_hashes,
               "water_stores": water_stores,
               "vehicle_starts": vehicle_starts,
               "shelter_preferences": shelter_preferences,
               "added_vehicles": tuple(asdict(item) for item in added),
               "declared_added_water_ml": declared_added_ml}
    return Variant(
        baseline.baseline_hash, baseline.source_hashes,
        hashlib.sha256(canonical_json(content)).hexdigest(),
        water_stores, vehicle_starts, shelter_preferences,
        tuple(added), declared_added_ml,
    )


__all__ = (
    "AddVehicle", "AddWater", "BaselineResources", "DeferredOperation", "MoveVehicleStart",
    "RedistributeWater", "ShelterPreference", "Variant", "apply_variant",
)
