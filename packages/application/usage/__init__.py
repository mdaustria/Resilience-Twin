"""Integer usage policy and privacy-preserving network bucket identity."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class UsagePolicy:
    guest_daily_units: int
    network_daily_units: int
    global_daily_units: int
    global_active_jobs: int
    challenge_after_network_units: int
    network_daily_sessions: int
    global_daily_sessions: int

    def __post_init__(self) -> None:
        values = tuple(vars(self).values())
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Usage limits must be positive integers")
        if self.challenge_after_network_units > self.network_daily_units:
            raise ValueError("Challenge threshold exceeds network cap")


STAGE_UNITS = {"extraction": 1, "graph": 2, "simulation": 3, "report": 1}
STAGE_SECONDS = {"extraction": 300, "graph": 300, "simulation": 600, "report": 300}


def stage_budget(stage: str) -> tuple[int, int]:
    try:
        return STAGE_UNITS[stage], STAGE_SECONDS[stage]
    except KeyError:
        raise ValueError("Unsupported processing stage") from None


def network_bucket(address: str, secret: bytes) -> str:
    if len(secret) < 32:
        raise ValueError("Network bucket needs a 32-byte secret")
    ip = ipaddress.ip_address(address)
    prefix = 24 if ip.version == 4 else 64
    network = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    return hmac.new(secret, str(network).encode(), hashlib.sha256).hexdigest()


__all__ = ["UsagePolicy", "network_bucket", "stage_budget"]
