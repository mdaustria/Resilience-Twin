"""Local API bootstrap and development-only synthetic case routes."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from packages.application.skeleton import (
    CaseNotFound,
    FixtureMismatch,
    get_case,
    run_case,
)
from packages.contracts.skeleton import SkeletonCase, SkeletonResult

if TYPE_CHECKING:
    from packages.adapters.persistence.runs import FirestoreRuns
    from packages.adapters.persistence.sessions import FirestoreTemporarySessions
    from packages.application.deletion import DeleteWorkspace
    from packages.application.documents import PrivateDocuments
    from packages.application.jobs import JobSubmission
    from packages.application.usage import UsagePolicy
    from packages.application.versions import DurableVersions
    from services.api.documents import OwnerResolver


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


def create_app(local_fixture_mode: bool | None = None, *,
               temporary_sessions: FirestoreTemporarySessions | None = None,
               session_network_secret: bytes | None = None,
               private_documents: PrivateDocuments | None = None,
               private_owner_for: OwnerResolver | None = None,
               durable_versions: DurableVersions | None = None,
               job_submission: JobSubmission | None = None,
               job_network_secret: bytes | None = None,
               job_challenge_verifier: Callable[[Request], bool] | None = None,
               usage_policy: UsagePolicy | None = None,
               workspace_deletion: DeleteWorkspace | None = None,
               durable_runs: FirestoreRuns | None = None,
               session_origin: str | None = None,
               session_csrf_key: bytes | None = None) -> FastAPI:
    api = FastAPI(title="Resilience Twin local API", version="bootstrap.v1")
    api.get("/api/v1/bootstrap", response_model=BootstrapStatus)(bootstrap_status)
    if usage_policy is not None:
        from services.api.limits import limits_router
        api.include_router(limits_router(usage_policy))

    if temporary_sessions is not None:
        if session_origin is None or session_csrf_key is None:
            raise ValueError("Temporary sessions require origin and CSRF configuration")
        from services.api.sessions import sessions_router
        api.include_router(sessions_router(temporary_sessions, origin=session_origin,
                                           csrf_key=session_csrf_key,
                                           network_secret=session_network_secret))

    if private_documents is not None:
        if private_owner_for is None or session_origin is None or session_csrf_key is None:
            raise ValueError("Private documents require owner, origin and CSRF configuration")
        from services.api.artifacts import artifacts_router
        from services.api.documents import documents_router
        api.include_router(documents_router(private_documents, private_owner_for,
                                            origin=session_origin, csrf_key=session_csrf_key))
        api.include_router(artifacts_router(private_documents, private_owner_for))

    if durable_versions is not None:
        if private_owner_for is None or session_origin is None or session_csrf_key is None:
            raise ValueError("Durable versions require owner, origin and CSRF configuration")
        from services.api.proposals import proposals_router
        from services.api.review import (
            Problem,
            VersionHttp,
            baselines_router,
            durable_review_router,
            problem_response,
        )
        from services.api.scenarios import scenario_suites_router, scenarios_router
        http = VersionHttp(durable_versions, private_owner_for,
                           origin=session_origin, csrf_key=session_csrf_key)
        api.add_exception_handler(Problem, lambda _request, error: problem_response(error))
        api.include_router(durable_review_router(http))
        api.include_router(baselines_router(http))
        if private_documents is not None:
            from services.api.geography import private_pilot_geography_router
            api.include_router(private_pilot_geography_router(http, private_documents))
        api.include_router(scenarios_router(http, private_documents))
        api.include_router(scenario_suites_router(http))
        api.include_router(proposals_router(http))

    if job_submission is not None:
        if private_owner_for is None or session_origin is None or session_csrf_key is None:
            raise ValueError("Jobs require owner, origin and CSRF configuration")
        from services.api.jobs import jobs_router
        from services.api.review import Problem, problem_response
        api.add_exception_handler(Problem, lambda _request, error: problem_response(error))
        api.include_router(jobs_router(job_submission, private_owner_for,
                                       origin=session_origin, csrf_key=session_csrf_key,
                                       network_secret=job_network_secret,
                                       challenge_verifier=job_challenge_verifier))

    if durable_runs is not None:
        if private_owner_for is None or session_origin is None or session_csrf_key is None:
            raise ValueError("Runs require owner, origin and CSRF configuration")
        from services.api.review import Problem, problem_response
        from services.api.runs import runs_router
        api.add_exception_handler(Problem, lambda _request, error: problem_response(error))
        api.include_router(runs_router(durable_runs, private_owner_for,
                                       origin=session_origin, csrf_key=session_csrf_key))

    if durable_runs is not None and durable_versions is not None:
        assert private_owner_for is not None
        from packages.application.comparisons import PrivateComparisons
        from services.api.comparisons import comparisons_router
        api.include_router(comparisons_router(
            PrivateComparisons(durable_versions.store, durable_runs), private_owner_for))

    if (durable_versions is not None and durable_runs is not None
            and private_documents is not None and job_submission is not None):
        assert private_owner_for is not None and session_origin is not None
        assert session_csrf_key is not None
        from services.api.reports import reports_router
        api.include_router(reports_router(durable_versions.store, job_submission,
            private_documents, PrivateComparisons(durable_versions.store, durable_runs),
            private_owner_for, origin=session_origin, csrf_key=session_csrf_key))

    if workspace_deletion is not None:
        if private_owner_for is None or session_origin is None or session_csrf_key is None:
            raise ValueError("Workspace deletion requires owner, origin and CSRF configuration")
        from services.api.review import Problem, problem_response
        from services.api.workspaces import workspaces_router
        api.add_exception_handler(Problem, lambda _request, error: problem_response(error))
        api.include_router(workspaces_router(workspace_deletion, private_owner_for,
                                             origin=session_origin, csrf_key=session_csrf_key))

    enabled = local_fixture_enabled() if local_fixture_mode is None else local_fixture_mode
    if enabled:
        from packages.adapters.local.fixtures import FixtureCaseRepository
        from packages.application.review import ReviewService
        from services.api.geography import geography_router, pilot_geography
        from services.api.review import review_router

        repository = FixtureCaseRepository()
        review_service = ReviewService(scope_resolver=lambda case: pilot_geography(case).scope_id)
        api.include_router(review_router(review_service))
        api.include_router(geography_router(review_service))

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
