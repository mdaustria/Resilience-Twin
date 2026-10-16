"""Integer milliliter water accounting at one-second simulation resolution."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from packages.contracts.operational import OperationalInputs
from packages.simulation.kernel.events import Event, EventQueue

SECONDS_PER_DAY = 86_400


def _integer(value: int, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")


@dataclass(frozen=True)
class WaterStore:
    id: str
    initial_ml: int

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("water store ID is required")
        _integer(self.initial_ml, "initial_ml")


@dataclass(frozen=True)
class WaterCohort:
    id: str
    people: int
    ml_per_person_day: int
    supply_id: str

    def __post_init__(self) -> None:
        if not self.id or not self.supply_id:
            raise ValueError("water cohort and supply IDs are required")
        _integer(self.people, "people", positive=True)
        _integer(self.ml_per_person_day, "ml_per_person_day", positive=True)


@dataclass(frozen=True)
class StoreBalance:
    id: str
    initial_ml: int
    remaining_ml: int
    consumed_ml: int = 0
    unmet_ml: int = 0
    exhaustion_time_seconds: int | None = None


@dataclass(frozen=True)
class CohortBalance:
    id: str
    people: int
    ml_per_person_day: int
    supply_id: str
    remainder_numerator: int = 0
    demand_ml: int = 0
    consumed_ml: int = 0
    unmet_ml: int = 0


class WaterLedger:
    """Consume known supply; assign shortages by stable cohort ID within a store.

    Each cohort retains its fraction of a milliliter on rebind. An exhaustion
    timestamp is the first whole simulation second at which accrued integer
    demand reaches the available stock. It is exact at the engine's second
    resolution and is found without floating-point arithmetic.
    """

    def __init__(self, stores: Iterable[WaterStore], cohorts: Iterable[WaterCohort]) -> None:
        store_list, cohort_list = tuple(stores), tuple(cohorts)
        if len({store.id for store in store_list}) != len(store_list):
            raise ValueError("duplicate water store ID")
        if len({cohort.id for cohort in cohort_list}) != len(cohort_list):
            raise ValueError("duplicate water cohort ID")
        self._stores = {
            store.id: StoreBalance(store.id, store.initial_ml, store.initial_ml)
            for store in store_list
        }
        self._cohorts = {}
        for cohort in cohort_list:
            if cohort.supply_id not in self._stores:
                raise ValueError(f"unknown water supply: {cohort.supply_id}")
            self._cohorts[cohort.id] = CohortBalance(
                cohort.id, cohort.people, cohort.ml_per_person_day, cohort.supply_id,
            )
        self.time_seconds = 0
        self.assert_balanced()

    @classmethod
    def from_operational_inputs(cls, inputs: OperationalInputs) -> "WaterLedger":
        stores = (
            *(WaterStore(str(item.id), item.initial_water_ml) for item in inputs.shelters),
            *(WaterStore(str(item.id), item.initial_water_ml) for item in inputs.supply_stores),
        )
        cohorts = (WaterCohort(
            id=str(item.id), people=item.people,
            ml_per_person_day=item.water_ml_per_person_day,
            supply_id=str(item.shelter_id or item.pre_shelter_water_store_id),
        ) for item in inputs.cohorts)
        return cls(stores, cohorts)

    @property
    def stores(self) -> tuple[StoreBalance, ...]:
        return tuple(self._stores[key] for key in sorted(self._stores))

    @property
    def cohorts(self) -> tuple[CohortBalance, ...]:
        return tuple(self._cohorts[key] for key in sorted(self._cohorts))

    def store(self, store_id: str) -> StoreBalance:
        return self._stores[store_id]

    def cohort(self, cohort_id: str) -> CohortBalance:
        return self._cohorts[cohort_id]

    def rebind(self, cohort_id: str, supply_id: str) -> None:
        """Change the cohort's supply after integrating to its movement event."""
        if supply_id not in self._stores:
            raise ValueError("unknown water supply")
        item = self._cohorts[cohort_id]
        self._cohorts[cohort_id] = replace(item, supply_id=supply_id)
        self.assert_balanced()

    def advance(self, to_seconds: int) -> None:
        _integer(to_seconds, "to_seconds")
        if to_seconds < self.time_seconds:
            raise ValueError("water time cannot go backwards")
        interval = to_seconds - self.time_seconds
        if interval == 0:
            return
        by_store: dict[str, list[tuple[str, int, int, int]]] = {}
        for cohort_id in sorted(self._cohorts):
            item = self._cohorts[cohort_id]
            numerator = item.remainder_numerator + (
                item.people * item.ml_per_person_day * interval
            )
            demand_ml, remainder = divmod(numerator, SECONDS_PER_DAY)
            by_store.setdefault(item.supply_id, []).append((
                cohort_id, demand_ml, item.remainder_numerator,
                item.people * item.ml_per_person_day,
            ))
            self._cohorts[cohort_id] = replace(
                item, remainder_numerator=remainder, demand_ml=item.demand_ml + demand_ml,
            )
        for store_id in sorted(self._stores):
            store = self._stores[store_id]
            entries = by_store.get(store_id, [])
            interval_demand = sum(entry[1] for entry in entries)
            crossing = store.exhaustion_time_seconds
            if crossing is None:
                if store.remaining_ml == 0 and entries:
                    crossing = self.time_seconds
                elif interval_demand >= store.remaining_ml and interval_demand > 0:
                    crossing = self._crossing_time(entries, store.remaining_ml, interval)
            available = store.remaining_ml
            for cohort_id, demand, _, _ in entries:
                supplied = min(available, demand)
                available -= supplied
                item = self._cohorts[cohort_id]
                self._cohorts[cohort_id] = replace(
                    item, consumed_ml=item.consumed_ml + supplied,
                    unmet_ml=item.unmet_ml + demand - supplied,
                )
            self._stores[store_id] = replace(
                store, remaining_ml=available,
                consumed_ml=store.consumed_ml + store.remaining_ml - available,
                unmet_ml=store.unmet_ml + interval_demand - (store.remaining_ml - available),
                exhaustion_time_seconds=crossing,
            )
        self.time_seconds = to_seconds
        self.assert_balanced()

    def _crossing_time(
        self, entries: list[tuple[str, int, int, int]], stock_ml: int, interval: int,
    ) -> int:
        if stock_ml == 0:
            return self.time_seconds
        low, high = 1, interval
        while low < high:
            middle = (low + high) // 2
            accrued = sum(
                (remainder + rate * middle) // SECONDS_PER_DAY
                for _, _, remainder, rate in entries
            )
            if accrued >= stock_ml:
                high = middle
            else:
                low = middle + 1
        return self.time_seconds + low

    def assert_balanced(self) -> None:
        for store in self._stores.values():
            if store.remaining_ml < 0 or store.initial_ml != store.remaining_ml + store.consumed_ml:
                raise AssertionError("water stock conservation failed")
        for cohort in self._cohorts.values():
            if cohort.demand_ml != cohort.consumed_ml + cohort.unmet_ml:
                raise AssertionError("cohort water demand accounting failed")
            if not 0 <= cohort.remainder_numerator < SECONDS_PER_DAY:
                raise AssertionError("water remainder is outside one milliliter")
        if sum(store.unmet_ml for store in self._stores.values()) != sum(
            cohort.unmet_ml for cohort in self._cohorts.values()
        ):
            raise AssertionError("water shortage accounting failed")


def run_with_water(
    queue: EventQueue, water: WaterLedger, handler: Callable[[Event, EventQueue], None],
) -> None:
    """Integrate the preceding interval before every event, including terminal H."""

    def handle(event: Event, scheduler: EventQueue) -> None:
        water.advance(event.time_seconds)
        handler(event, scheduler)
        water.assert_balanced()

    queue.run(handle)


__all__ = (
    "CohortBalance", "StoreBalance", "WaterCohort", "WaterLedger", "WaterStore",
    "run_with_water",
)
