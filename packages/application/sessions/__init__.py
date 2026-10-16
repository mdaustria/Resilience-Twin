"""Temporary ownership lifetimes and transport-independent session contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

IDLE_LIFETIME = timedelta(hours=2)
ABSOLUTE_LIFETIME = timedelta(hours=24)


class SessionUnavailable(Exception):
    """The temporary credential no longer authorizes its owner."""


class IssuanceDenied(Exception):
    """An issuance budget or abuse check denied a new session."""


def expiry_for(created_at: datetime, last_user_activity_at: datetime) -> datetime:
    if created_at.tzinfo is None or last_user_activity_at.tzinfo is None:
        raise ValueError("Session times must be timezone aware")
    if last_user_activity_at < created_at:
        raise ValueError("Activity cannot predate creation")
    return min(last_user_activity_at + IDLE_LIFETIME, created_at + ABSOLUTE_LIFETIME)


@dataclass(frozen=True)
class TemporarySession:
    owner_id: str
    workspace_id: str
    created_at: datetime
    last_user_activity_at: datetime
    expires_at: datetime
    absolute_expires_at: datetime


__all__ = ["ABSOLUTE_LIFETIME", "IDLE_LIFETIME", "IssuanceDenied",
           "SessionUnavailable", "TemporarySession", "expiry_for"]
