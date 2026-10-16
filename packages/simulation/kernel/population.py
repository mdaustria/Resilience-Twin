"""One population state for each uniquely identified cohort slice."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from packages.contracts.operational import Cohort


class PopulationState(StrEnum):
    NOT_REQUESTED = "not_requested"
    WAITING = "waiting"
    LOADING = "loading"
    IN_TRANSIT = "in_transit"
    UNLOADING = "unloading"
    SHELTERED = "sheltered"


@dataclass(frozen=True)
class PopulationSlice:
    id: str
    source_cohort_id: str
    people: int
    state: PopulationState
    request_time_seconds: int | None = None
    deadline_seconds: int | None = None
    arrival_time_seconds: int | None = None
    assistance_needs: tuple[str, ...] = ()
    location_id: str | None = None
    edge_id: str | None = None
    edge_elapsed_seconds: int = 0
    reservation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.source_cohort_id or type(self.people) is not int or self.people <= 0:
            raise ValueError("a slice needs unique IDs and positive integer people")
        if not isinstance(self.state, PopulationState):
            raise TypeError("invalid population state")
        if self.arrival_time_seconds is not None and self.state is not PopulationState.SHELTERED:
            raise ValueError("only sheltered people have an arrival time")
        if self.state is PopulationState.IN_TRANSIT and self.location_id is None and self.edge_id is None:
            raise ValueError("in-transit people need a node or edge position")
        if self.edge_elapsed_seconds < 0 or (self.edge_id is None and self.edge_elapsed_seconds):
            raise ValueError("invalid edge progress")


class PopulationLedger:
    def __init__(self, slices: Iterable[PopulationSlice]) -> None:
        items = tuple(slices)
        if len({item.id for item in items}) != len(items):
            raise ValueError("duplicate population slice ID")
        self._slices = {item.id: item for item in items}
        self._initial_by_source: dict[str, int] = {}
        for item in items:
            self._initial_by_source[item.source_cohort_id] = (
                self._initial_by_source.get(item.source_cohort_id, 0) + item.people
            )
        self.assert_conserved()

    @classmethod
    def from_cohorts(cls, cohorts: Iterable[Cohort]) -> "PopulationLedger":
        return cls(PopulationSlice(
            id=str(cohort.id), source_cohort_id=str(cohort.id), people=cohort.people,
            state=PopulationState(cohort.initial_state),
            request_time_seconds=cohort.request_time_seconds,
            deadline_seconds=cohort.deadline_seconds,
            assistance_needs=cohort.assistance_needs,
            location_id=str(cohort.shelter_id or cohort.pickup_id),
        ) for cohort in cohorts)

    @property
    def slices(self) -> tuple[PopulationSlice, ...]:
        return tuple(self._slices[key] for key in sorted(self._slices))

    @property
    def initial_people(self) -> int:
        return sum(self._initial_by_source.values())

    def get(self, slice_id: str) -> PopulationSlice:
        return self._slices[slice_id]

    def split(self, slice_id: str, new_id: str, people: int) -> None:
        if new_id in self._slices or not new_id or type(people) is not int:
            raise ValueError("split requires a new ID and integer people")
        source = self._slices[slice_id]
        if people <= 0 or people >= source.people:
            raise ValueError("split must retain people in both slices")
        self._slices[slice_id] = replace(source, people=source.people - people)
        self._slices[new_id] = replace(source, id=new_id, people=people)
        self.assert_conserved()

    def transition(
        self, slice_id: str, expected: PopulationState, state: PopulationState,
        time_seconds: int, *, location_id: str | None = None,
        edge_id: str | None = None, edge_elapsed_seconds: int = 0,
        reservation_id: str | None = None,
    ) -> None:
        item = self._slices[slice_id]
        if item.state is not expected or not isinstance(state, PopulationState):
            raise ValueError("population transition has stale or invalid state")
        if type(time_seconds) is not int or time_seconds < 0:
            raise ValueError("transition time must be nonnegative integer seconds")
        allowed = {
            PopulationState.NOT_REQUESTED: {PopulationState.WAITING},
            PopulationState.WAITING: {PopulationState.LOADING},
            PopulationState.LOADING: {PopulationState.WAITING, PopulationState.IN_TRANSIT},
            PopulationState.IN_TRANSIT: {PopulationState.WAITING, PopulationState.UNLOADING},
            PopulationState.UNLOADING: {PopulationState.WAITING, PopulationState.SHELTERED},
            PopulationState.SHELTERED: {PopulationState.WAITING},
        }
        if state not in allowed[expected]:
            raise ValueError("invalid population transition")
        if expected is PopulationState.NOT_REQUESTED and item.request_time_seconds != time_seconds:
            raise ValueError("demand activates only at its request time")
        if state is PopulationState.SHELTERED and location_id is None:
            raise ValueError("shelter arrival needs a shelter location")
        updated = replace(
            item, state=state, location_id=location_id or item.location_id,
            edge_id=edge_id, edge_elapsed_seconds=edge_elapsed_seconds,
            reservation_id=reservation_id,
            arrival_time_seconds=time_seconds if state is PopulationState.SHELTERED else None,
        )
        self._slices[slice_id] = updated
        self.assert_conserved()

    def assert_conserved(self) -> None:
        current: dict[str, int] = {}
        for item in self._slices.values():
            current[item.source_cohort_id] = current.get(item.source_cohort_id, 0) + item.people
        if current != self._initial_by_source:
            raise AssertionError("population conservation failed")
