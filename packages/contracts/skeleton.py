"""Versioned synthetic case contract for the local walking skeleton only."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SkeletonCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skeleton.case.v1"]
    case_id: str = Field(min_length=1)
    cohort_people: int = Field(strict=True, ge=0)
    vehicle_seats: int = Field(strict=True, ge=0)
    shelter_spaces: int = Field(strict=True, ge=0)
    travel_time_seconds: int = Field(strict=True, gt=0)
    horizon_seconds: int = Field(strict=True, gt=0)
    shelter_water_ml: int = Field(strict=True, ge=0)
    arrival_water_need_ml_per_person: int = Field(strict=True, gt=0)
    source_label: str = Field(min_length=1)
    assumption_label: str = Field(min_length=1)


class SkeletonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skeleton.result.v1"]
    case_id: str
    initial_people: int
    arrived_people: int
    unserved_people: int
    arrival_time_seconds: int | None
    water_required_ml: int
    water_used_ml: int
    water_shortfall_ml: int
    water_sufficient_people: int
    water_remaining_ml: int
    source_label: str
    assumption_label: str
