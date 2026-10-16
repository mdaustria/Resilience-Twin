"""Exclusive trip, crew, shelter and distance reservations."""

from dataclasses import dataclass, replace
from enum import StrEnum

from packages.contracts.operational import OperationalInputs
from packages.simulation.kernel.population import PopulationLedger, PopulationState
from packages.simulation.kernel.water import WaterLedger
from packages.simulation.routing.reference import RouteResult


def _count(value: int, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")


@dataclass(frozen=True)
class Window:
    start_seconds: int
    end_seconds: int

    def __post_init__(self) -> None:
        _count(self.start_seconds, "window start")
        _count(self.end_seconds, "window end")
        if self.end_seconds < self.start_seconds:
            raise ValueError("availability window is reversed")

    def covers(self, start: int, end: int) -> bool:
        return self.start_seconds <= start <= end <= self.end_seconds


@dataclass(frozen=True)
class VehicleResource:
    id: str
    crew_id: str
    seats: int
    supported_needs: tuple[str, ...]
    availability: tuple[Window, ...]
    distance_budget_mm: int
    initial_location_id: str
    return_required: bool

    def __post_init__(self) -> None:
        if not self.id or not self.crew_id or not self.initial_location_id:
            raise ValueError("vehicle, crew and location IDs are required")
        _count(self.seats, "vehicle seats", positive=True)
        _count(self.distance_budget_mm, "distance budget")
        if not self.availability:
            raise ValueError("vehicle availability is required")


@dataclass(frozen=True)
class CrewResource:
    id: str
    availability: tuple[Window, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.availability:
            raise ValueError("crew ID and availability are required")


@dataclass(frozen=True)
class ShelterResource:
    id: str
    capacity_people: int
    initial_occupancy_people: int
    permitted_needs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("shelter ID is required")
        _count(self.capacity_people, "shelter capacity")
        _count(self.initial_occupancy_people, "shelter occupancy")
        if self.initial_occupancy_people > self.capacity_people:
            raise ValueError("initial shelter occupancy exceeds capacity")


@dataclass(frozen=True)
class TripPlan:
    id: str
    cohort_id: str
    people: int
    assistance_needs: tuple[str, ...]
    vehicle_id: str
    shelter_id: str
    dispatch_seconds: int
    pickup_route: RouteResult
    loading_seconds: int
    passenger_route: RouteResult
    unloading_seconds: int
    return_route: RouteResult | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.cohort_id or not self.vehicle_id or not self.shelter_id:
            raise ValueError("trip, cohort, vehicle and shelter IDs are required")
        _count(self.people, "trip people", positive=True)
        _count(self.dispatch_seconds, "dispatch time")
        _count(self.loading_seconds, "loading seconds", positive=True)
        _count(self.unloading_seconds, "unloading seconds", positive=True)


@dataclass(frozen=True)
class TripTiming:
    pickup_seconds: int
    loaded_seconds: int
    shelter_arrival_seconds: int
    unloaded_seconds: int
    release_seconds: int
    planned_distance_mm: int


@dataclass(frozen=True)
class VehicleState:
    resource: VehicleResource
    location_id: str
    active_trip_id: str | None = None
    consumed_distance_mm: int = 0
    reserved_distance_mm: int = 0
    edge_id: str | None = None
    edge_progress_mm: int = 0
    disabled: bool = False


@dataclass(frozen=True)
class ShelterState:
    resource: ShelterResource
    capacity_people: int
    occupancy_people: int
    reserved_people: int = 0

    @property
    def forced_overload_people(self) -> int:
        return max(0, self.occupancy_people - self.capacity_people)

    @property
    def relocation_demand_people(self) -> int:
        """Occupants needing another place after a capacity reduction."""
        return self.forced_overload_people


class TripPhase(StrEnum):
    TO_PICKUP = "to_pickup"
    LOADING = "loading"
    IN_TRANSIT = "in_transit"
    UNLOADING = "unloading"
    RETURNING = "returning"
    STRANDED = "stranded"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TripRecord:
    plan: TripPlan
    timing: TripTiming
    phase: TripPhase = TripPhase.TO_PICKUP
    reserved_shelter_people: int = 0
    remaining_distance_mm: int = 0
    actual_distance_mm: int = 0


class ResourceLedger:
    """Mutations are atomic within one deterministic simulation event handler."""

    def __init__(
        self, vehicles: tuple[VehicleResource, ...], crews: tuple[CrewResource, ...],
        shelters: tuple[ShelterResource, ...],
    ) -> None:
        if len({item.id for item in vehicles}) != len(vehicles):
            raise ValueError("duplicate vehicle ID")
        if len({item.id for item in crews}) != len(crews):
            raise ValueError("duplicate crew ID")
        if len({item.id for item in shelters}) != len(shelters):
            raise ValueError("duplicate shelter ID")
        self.vehicles = {item.id: VehicleState(item, item.initial_location_id) for item in vehicles}
        self.crews = {item.id: item for item in crews}
        self.crew_trips: dict[str, str | None] = {item.id: None for item in crews}
        self.shelters = {item.id: ShelterState(
            item, item.capacity_people, item.initial_occupancy_people,
        ) for item in shelters}
        self.trips: dict[str, TripRecord] = {}
        if any(item.resource.crew_id not in self.crews for item in self.vehicles.values()):
            raise ValueError("vehicle references unknown dedicated crew")
        self.assert_invariants()

    @classmethod
    def from_operational_inputs(cls, inputs: OperationalInputs) -> "ResourceLedger":
        occupants: dict[str, int] = {}
        for cohort in inputs.cohorts:
            if cohort.initial_state == "sheltered" and cohort.shelter_id is not None:
                key = str(cohort.shelter_id)
                occupants[key] = occupants.get(key, 0) + cohort.people
        if not set(occupants) <= {str(item.id) for item in inputs.shelters}:
            raise ValueError("initial occupants reference an unknown shelter")
        return cls(
            tuple(VehicleResource(
                id=str(item.id), crew_id=str(item.crew_id), seats=item.seats,
                supported_needs=item.supported_needs,
                availability=tuple(Window(w.start_seconds, w.end_seconds)
                                   for w in item.availability),
                distance_budget_mm=item.distance_budget_mm,
                initial_location_id=item.initial_location.graph_node_id,
                return_required=item.return_required,
            ) for item in inputs.vehicles),
            tuple(CrewResource(
                id=str(item.id), availability=tuple(
                    Window(w.start_seconds, w.end_seconds) for w in item.availability
                ),
            ) for item in inputs.crews),
            tuple(ShelterResource(
                id=str(item.id), capacity_people=item.capacity_people,
                initial_occupancy_people=occupants.get(str(item.id), 0),
                permitted_needs=item.permitted_needs,
            ) for item in inputs.shelters),
        )

    def _reserve(self, plan: TripPlan, timing: TripTiming) -> TripRecord:
        """Called only after the pure feasibility check succeeds."""
        vehicle = self.vehicles[plan.vehicle_id]
        crew_id = vehicle.resource.crew_id
        shelter = self.shelters[plan.shelter_id]
        record = TripRecord(
            plan, timing, reserved_shelter_people=plan.people,
            remaining_distance_mm=timing.planned_distance_mm,
        )
        self.vehicles[plan.vehicle_id] = replace(
            vehicle, active_trip_id=plan.id,
            reserved_distance_mm=vehicle.reserved_distance_mm + timing.planned_distance_mm,
        )
        self.crew_trips[crew_id] = plan.id
        self.shelters[plan.shelter_id] = replace(
            shelter, reserved_people=shelter.reserved_people + plan.people,
        )
        self.trips[plan.id] = record
        self.assert_invariants()
        return record

    def travel_edge(
        self, trip_id: str, distance_mm: int, *, edge_id: str,
        progress_mm: int, location_id: str,
    ) -> None:
        """Spend actual distance from the reservation without creating fuel."""
        _count(distance_mm, "travel distance")
        _count(progress_mm, "edge progress")
        record = self.trips[trip_id]
        vehicle = self.vehicles[record.plan.vehicle_id]
        if record.phase not in (TripPhase.TO_PICKUP, TripPhase.IN_TRANSIT, TripPhase.RETURNING):
            raise ValueError("trip is not traveling")
        if not edge_id or not location_id or distance_mm > record.remaining_distance_mm:
            raise ValueError("actual edge travel exceeds reserved distance or has no location")
        if vehicle.consumed_distance_mm + distance_mm > vehicle.resource.distance_budget_mm:
            raise ValueError("actual edge travel exceeds distance budget")
        self.trips[trip_id] = replace(
            record, remaining_distance_mm=record.remaining_distance_mm - distance_mm,
            actual_distance_mm=record.actual_distance_mm + distance_mm,
        )
        self.vehicles[record.plan.vehicle_id] = replace(
            vehicle, consumed_distance_mm=vehicle.consumed_distance_mm + distance_mm,
            reserved_distance_mm=vehicle.reserved_distance_mm - distance_mm,
            edge_id=edge_id if progress_mm else None,
            edge_progress_mm=progress_mm, location_id=location_id,
        )
        self.assert_invariants()

    def _replace_route(
        self, trip_id: str, plan: TripPlan, timing: TripTiming,
        remaining_distance_mm: int,
    ) -> None:
        """Swap validated remaining reservations without changing passenger state."""
        record = self.trips[trip_id]
        old_shelter = self.shelters[record.plan.shelter_id]
        new_shelter = self.shelters[plan.shelter_id]
        vehicle = self.vehicles[plan.vehicle_id]
        self.shelters[old_shelter.resource.id] = replace(
            old_shelter, reserved_people=old_shelter.reserved_people - record.reserved_shelter_people,
        )
        current_new = self.shelters[new_shelter.resource.id]
        self.shelters[new_shelter.resource.id] = replace(
            current_new, reserved_people=current_new.reserved_people + plan.people,
        )
        self.vehicles[plan.vehicle_id] = replace(
            vehicle, reserved_distance_mm=(
                vehicle.reserved_distance_mm - record.remaining_distance_mm + remaining_distance_mm
            ),
        )
        self.trips[trip_id] = replace(
            record, plan=plan, timing=timing, phase=TripPhase.IN_TRANSIT,
            reserved_shelter_people=plan.people, remaining_distance_mm=remaining_distance_mm,
        )
        self.assert_invariants()

    def pickup(self, trip_id: str, time_seconds: int, population: PopulationLedger) -> None:
        record = self.trips[trip_id]
        if record.phase is not TripPhase.TO_PICKUP or time_seconds != record.timing.pickup_seconds:
            raise ValueError("pickup must finish at its planned time")
        self._assert_passengers(record, population)
        population.transition(record.plan.cohort_id, PopulationState.WAITING,
                              PopulationState.LOADING, time_seconds)
        self.trips[trip_id] = replace(record, phase=TripPhase.LOADING)

    def depart(self, trip_id: str, time_seconds: int, population: PopulationLedger) -> None:
        record = self.trips[trip_id]
        if record.phase is not TripPhase.LOADING or time_seconds != record.timing.loaded_seconds:
            raise ValueError("loading must finish at its planned time")
        self._assert_passengers(record, population)
        population.transition(record.plan.cohort_id, PopulationState.LOADING,
                              PopulationState.IN_TRANSIT, time_seconds,
                              location_id=self.vehicles[record.plan.vehicle_id].location_id,
                              reservation_id=trip_id)
        self.trips[trip_id] = replace(record, phase=TripPhase.IN_TRANSIT)

    def begin_unload(self, trip_id: str, time_seconds: int, population: PopulationLedger) -> None:
        record = self.trips[trip_id]
        if record.phase is not TripPhase.IN_TRANSIT or time_seconds != record.timing.shelter_arrival_seconds:
            raise ValueError("shelter arrival must match planned passenger travel")
        self._assert_passengers(record, population)
        population.transition(record.plan.cohort_id, PopulationState.IN_TRANSIT,
                              PopulationState.UNLOADING, time_seconds,
                              location_id=record.plan.shelter_id, reservation_id=trip_id)
        self.trips[trip_id] = replace(record, phase=TripPhase.UNLOADING)

    def admit(
        self, trip_id: str, time_seconds: int, population: PopulationLedger,
        water: WaterLedger | None = None,
    ) -> bool:
        record = self.trips[trip_id]
        if record.phase is not TripPhase.UNLOADING or time_seconds != record.timing.unloaded_seconds:
            raise ValueError("unloading must finish at its planned time")
        self._assert_passengers(record, population)
        shelter = self.shelters[record.plan.shelter_id]
        if shelter.occupancy_people + record.plan.people > shelter.capacity_people:
            self._strand(trip_id)
            return False
        if water is not None:
            water.cohort(record.plan.cohort_id)
            water.store(record.plan.shelter_id)
        population.transition(record.plan.cohort_id, PopulationState.UNLOADING,
                              PopulationState.SHELTERED, time_seconds,
                              location_id=record.plan.shelter_id)
        if water is not None:
            water.rebind(record.plan.cohort_id, record.plan.shelter_id)
        self.shelters[record.plan.shelter_id] = replace(
            shelter, occupancy_people=shelter.occupancy_people + record.plan.people,
            reserved_people=shelter.reserved_people - record.reserved_shelter_people,
        )
        self.trips[trip_id] = replace(
            record, phase=TripPhase.RETURNING, reserved_shelter_people=0,
        )
        if record.timing.release_seconds == time_seconds:
            self.finish_return(trip_id, time_seconds)
        self.assert_invariants()
        return True

    def finish_return(self, trip_id: str, time_seconds: int) -> None:
        record = self.trips[trip_id]
        if record.phase is not TripPhase.RETURNING or time_seconds != record.timing.release_seconds:
            raise ValueError("vehicle release must follow its planned return leg")
        self._release_vehicle(record)
        self.trips[trip_id] = replace(record, phase=TripPhase.COMPLETED, remaining_distance_mm=0)
        self.assert_invariants()

    def cancel(self, trip_id: str) -> None:
        record = self.trips[trip_id]
        if record.phase is TripPhase.TO_PICKUP:
            self._release_shelter(record)
            self._release_vehicle(record)
            self.trips[trip_id] = replace(
                record, phase=TripPhase.CANCELLED, reserved_shelter_people=0,
                remaining_distance_mm=0,
            )
        elif record.phase in (TripPhase.LOADING, TripPhase.IN_TRANSIT, TripPhase.UNLOADING):
            self._strand(trip_id)
        else:
            raise ValueError("trip cannot be cancelled in this phase")
        self.assert_invariants()

    def outage(self, vehicle_id: str) -> None:
        vehicle = self.vehicles[vehicle_id]
        self.vehicles[vehicle_id] = replace(vehicle, disabled=True)
        if vehicle.active_trip_id is not None:
            self.cancel(vehicle.active_trip_id)
        self.assert_invariants()

    def set_shelter_capacity(self, shelter_id: str, capacity_people: int) -> None:
        _count(capacity_people, "shelter capacity")
        shelter = self.shelters[shelter_id]
        self.shelters[shelter_id] = replace(shelter, capacity_people=capacity_people)
        # Preserve existing occupants. Inbound reservations are revalidated in
        # stable trip order and excess trips retain their passengers.
        for trip_id in sorted(self.trips):
            record = self.trips[trip_id]
            if record.plan.shelter_id != shelter_id or not record.reserved_shelter_people:
                continue
            current = self.shelters[shelter_id]
            if current.occupancy_people + current.reserved_people > capacity_people:
                if record.phase is TripPhase.TO_PICKUP:
                    self.cancel(trip_id)
                else:
                    self._strand(trip_id)
        self.assert_invariants()

    def _strand(self, trip_id: str) -> None:
        record = self.trips[trip_id]
        self._release_shelter(record)
        vehicle = self.vehicles[record.plan.vehicle_id]
        self.vehicles[record.plan.vehicle_id] = replace(
            vehicle, reserved_distance_mm=vehicle.reserved_distance_mm - record.remaining_distance_mm,
        )
        self.trips[trip_id] = replace(
            record, phase=TripPhase.STRANDED, reserved_shelter_people=0,
            remaining_distance_mm=0,
        )

    def _release_shelter(self, record: TripRecord) -> None:
        shelter = self.shelters[record.plan.shelter_id]
        self.shelters[record.plan.shelter_id] = replace(
            shelter, reserved_people=shelter.reserved_people - record.reserved_shelter_people,
        )

    @staticmethod
    def _assert_passengers(record: TripRecord, population: PopulationLedger) -> None:
        cohort = population.get(record.plan.cohort_id)
        if (cohort.people != record.plan.people
                or set(cohort.assistance_needs) != set(record.plan.assistance_needs)):
            raise ValueError("reserved passengers changed after dispatch")

    def _release_vehicle(self, record: TripRecord) -> None:
        vehicle = self.vehicles[record.plan.vehicle_id]
        self.vehicles[record.plan.vehicle_id] = replace(
            vehicle, active_trip_id=None,
            reserved_distance_mm=vehicle.reserved_distance_mm - record.remaining_distance_mm,
            edge_id=None, edge_progress_mm=0,
        )
        self.crew_trips[vehicle.resource.crew_id] = None

    def assert_invariants(self) -> None:
        for vehicle in self.vehicles.values():
            if (vehicle.consumed_distance_mm < 0 or vehicle.reserved_distance_mm < 0
                    or vehicle.consumed_distance_mm + vehicle.reserved_distance_mm
                    > vehicle.resource.distance_budget_mm):
                raise AssertionError("vehicle distance budget exceeded")
            if vehicle.active_trip_id is not None:
                record = self.trips[vehicle.active_trip_id]
                if record.plan.vehicle_id != vehicle.resource.id:
                    raise AssertionError("vehicle owns another trip")
                if self.crew_trips[vehicle.resource.crew_id] != vehicle.active_trip_id:
                    raise AssertionError("dedicated crew is not reserved with vehicle")
        for shelter in self.shelters.values():
            if shelter.occupancy_people < 0 or shelter.reserved_people < 0:
                raise AssertionError("negative shelter occupancy or reservation")
            if (shelter.occupancy_people + shelter.reserved_people > shelter.capacity_people
                    and shelter.reserved_people > 0):
                raise AssertionError("shelter overbooked")
