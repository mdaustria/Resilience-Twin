"""Settle provider charges idempotently by provider event ID."""

from typing import Any

from packages.adapters.persistence.usage import FirestoreUsage


def settle_provider_usage(usage: FirestoreUsage, workspace_id: str, job_id: str,
                          *, provider_event_id: str, units: int,
                          final: bool = False) -> dict[str, Any]:
    return usage.settle(workspace_id, job_id, provider_event_id=provider_event_id,
                        actual_units=units, final=final)


__all__ = ["settle_provider_usage"]
