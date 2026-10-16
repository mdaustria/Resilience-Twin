"""Visible provisional compute and session limits."""

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Response

from packages.application.usage import STAGE_UNITS, UsagePolicy


def load_usage_policy(path: Path) -> UsagePolicy:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("stage_units") != STAGE_UNITS:
        raise ValueError("Published stage costs differ from enforced stage costs")

    def limit(name: str) -> int:
        value = data.get(name)
        if type(value) is not int:
            raise ValueError(f"Invalid {name} limit")
        return value

    return UsagePolicy(
        guest_daily_units=limit("guest_daily_units"),
        network_daily_units=limit("network_daily_units"),
        global_daily_units=limit("global_daily_units"),
        global_active_jobs=limit("global_active_jobs"),
        challenge_after_network_units=limit("challenge_after_network_units"),
        network_daily_sessions=limit("network_daily_sessions"),
        global_daily_sessions=limit("global_daily_sessions"),
    )


def limits_router(policy: UsagePolicy) -> APIRouter:
    router = APIRouter(prefix="/api/v1/limits")

    @router.get("")
    def read(response: Response) -> dict[str, object]:
        response.headers["Cache-Control"] = "private, no-store"
        return {"status": "provisional", "units": "estimated compute units",
                "limits": asdict(policy),
                "note": "Shared networks can reach a limit before an individual user."}

    return router


__all__ = ["limits_router", "load_usage_policy"]
