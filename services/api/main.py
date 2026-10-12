"""Local API bootstrap and development-only synthetic case routes."""

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from packages.application.skeleton import (
    CaseNotFound,
    FixtureMismatch,
    get_case,
    run_case,
)
from packages.contracts.skeleton import SkeletonCase, SkeletonResult


class BootstrapStatus(BaseModel):
    status: str
    schema_version: str


def local_fixture_enabled() -> bool:
    return (
        os.environ.get("RESILIENCE_TWIN_ENV") == "development"
        and os.environ.get("RESILIENCE_TWIN_LOCAL_FIXTURES") == "1"
    )


def bootstrap_status() -> BootstrapStatus:
    return BootstrapStatus(status="ready", schema_version="bootstrap.v1")


def create_app(local_fixture_mode: bool | None = None) -> FastAPI:
    api = FastAPI(title="Resilience Twin local API", version="bootstrap.v1")
    api.get("/api/v1/bootstrap", response_model=BootstrapStatus)(bootstrap_status)

    enabled = local_fixture_enabled() if local_fixture_mode is None else local_fixture_mode
    if enabled:
        from packages.adapters.local.fixtures import FixtureCaseRepository

        repository = FixtureCaseRepository()

        @api.get("/api/v1/local/cases/{case_id}", response_model=SkeletonCase)
        async def read_fixture(case_id: str, x_fixture_owner: str = Header()) -> SkeletonCase:
            # The header selects an isolated synthetic fixture; it is not production auth.
            try:
                return get_case(x_fixture_owner, case_id, repository)
            except CaseNotFound:
                raise HTTPException(status_code=404, detail="Case not found") from None

        @api.post("/api/v1/local/cases/{case_id}/run", response_model=SkeletonResult)
        async def run_fixture(
            case_id: str, submitted: SkeletonCase, x_fixture_owner: str = Header()
        ) -> SkeletonResult:
            try:
                return run_case(x_fixture_owner, case_id, submitted, repository)
            except CaseNotFound:
                raise HTTPException(status_code=404, detail="Case not found") from None
            except FixtureMismatch:
                raise HTTPException(status_code=409, detail="Fixture differs from reviewed input") from None

    return api


app = create_app()
