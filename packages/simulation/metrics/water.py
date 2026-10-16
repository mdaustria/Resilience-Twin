"""Water sufficiency is independent of evacuation arrival status."""

from dataclasses import dataclass

from packages.simulation.kernel.water import WaterLedger


@dataclass(frozen=True)
class WaterMetrics:
    initial_ml: int
    consumed_ml: int
    remaining_ml: int
    unmet_ml: int
    exhaustion_by_store: dict[str, int | None]
    unmet_by_cohort: dict[str, int]

    def sufficient_for(self, cohort_id: str) -> bool:
        return self.unmet_by_cohort[cohort_id] == 0


def summarize(ledger: WaterLedger) -> WaterMetrics:
    ledger.assert_balanced()
    stores = ledger.stores
    cohorts = ledger.cohorts
    return WaterMetrics(
        initial_ml=sum(item.initial_ml for item in stores),
        consumed_ml=sum(item.consumed_ml for item in stores),
        remaining_ml=sum(item.remaining_ml for item in stores),
        unmet_ml=sum(item.unmet_ml for item in stores),
        exhaustion_by_store={item.id: item.exhaustion_time_seconds for item in stores},
        unmet_by_cohort={item.id: item.unmet_ml for item in cohorts},
    )


__all__ = ("WaterMetrics", "summarize")
