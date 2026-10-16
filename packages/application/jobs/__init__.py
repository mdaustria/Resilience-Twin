"""Durable job submission application boundary."""

from dataclasses import dataclass
from typing import Any, Protocol

from packages.contracts.ownership import Actor


class JobStore(Protocol):
    def read(self, actor: Actor, workspace_id: str, job_id: str) -> dict[str, Any]: ...

    def submit(self, actor: Actor, workspace_id: str, *, route: str,
               idempotency_key: str, stage: str, input_hash: str,
               estimated_units: int, required_seconds: int,
               network_key: str | None = None,
               challenge_satisfied: bool = False) -> dict[str, Any]: ...


@dataclass(frozen=True)
class JobSubmission:
    store: JobStore

    def submit(self, actor: Actor, workspace_id: str, *, route: str,
               idempotency_key: str, stage: str, input_hash: str,
               estimated_units: int, required_seconds: int,
               network_key: str | None = None,
               challenge_satisfied: bool = False) -> dict[str, Any]:
        return self.store.submit(actor, workspace_id, route=route,
            idempotency_key=idempotency_key, stage=stage, input_hash=input_hash,
            estimated_units=estimated_units, required_seconds=required_seconds,
            network_key=network_key, challenge_satisfied=challenge_satisfied)


__all__ = ["JobSubmission"]
