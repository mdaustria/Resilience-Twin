"""Transactional account, guest, network and global usage counters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import Client, Transaction

from packages.adapters.persistence.firestore import Actor, InvalidRecord
from packages.application.usage import UsagePolicy


class BudgetExceeded(Exception):
    pass


class ChallengeRequired(Exception):
    pass


class FirestoreUsage:
    def __init__(self, client: Client, policy: UsagePolicy) -> None:
        self.client = client
        self.policy = policy

    def _refs(self, actor: Actor, network_key: str, now: datetime) -> tuple[Any, Any, Any]:
        day = now.astimezone(UTC).strftime("%Y%m%d")
        root = self.client.collection("usage_days").document(day)
        return (root.collection("buckets").document("global"),
                root.collection("buckets").document(f"owner-{actor.kind}-{actor.owner_id}"),
                root.collection("buckets").document(f"network-{network_key}"))

    def reserve_in_transaction(self, tx: Transaction, actor: Actor,
                               workspace_id: str, job_id: str, *, network_key: str,
                               estimated_units: int, now: datetime,
                               challenge_satisfied: bool = False) -> dict[str, Any]:
        if actor.kind != "temporary":
            raise InvalidRecord("Only temporary sessions can reserve compute")
        if len(network_key) != 64 or any(c not in "0123456789abcdef" for c in network_key):
            raise InvalidRecord("Invalid network bucket")
        refs = self._refs(actor, network_key, now)
        rows = [ref.get(transaction=tx).to_dict() or {} for ref in refs]
        limits = (self.policy.global_daily_units,
                  self.policy.guest_daily_units,
                  self.policy.network_daily_units)
        for row, limit in zip(rows, limits, strict=True):
            if row.get("units", 0) + estimated_units > limit:
                raise BudgetExceeded("Daily compute budget exhausted")
        if rows[0].get("active_jobs", 0) >= self.policy.global_active_jobs:
            raise BudgetExceeded("Global concurrent job limit reached")
        if (rows[2].get("units", 0) + estimated_units > self.policy.challenge_after_network_units
                and not challenge_satisfied):
            raise ChallengeRequired("Network challenge required")
        for index, (ref, row) in enumerate(zip(refs, rows, strict=True)):
            values = {"schema_version": 1, "units": row.get("units", 0) + estimated_units,
                      "updated_at": now}
            if index == 0:
                values["active_jobs"] = row.get("active_jobs", 0) + 1
            tx.set(ref, values, merge=True)
        return {"counter_day": now.astimezone(UTC).strftime("%Y%m%d"),
                "network_key": network_key, "actor_kind": actor.kind,
                "actor_id": actor.owner_id, "workspace_id": workspace_id,
                "job_id": job_id}

    def reserve_issuance_in_transaction(self, tx: Transaction, *,
                                        network_key: str, now: datetime) -> None:
        day = now.astimezone(UTC).strftime("%Y%m%d")
        root = self.client.collection("usage_days").document(day)
        refs = (root.collection("buckets").document("global"),
                root.collection("buckets").document(f"network-{network_key}"))
        rows = [ref.get(transaction=tx).to_dict() or {} for ref in refs]
        for row, limit in zip(rows, (self.policy.global_daily_sessions,
                                     self.policy.network_daily_sessions), strict=True):
            if row.get("issued_sessions", 0) >= limit:
                raise BudgetExceeded("Temporary session issuance exhausted")
        for ref, row in zip(refs, rows, strict=True):
            tx.set(ref, {"schema_version": 1,
                         "issued_sessions": row.get("issued_sessions", 0) + 1,
                         "updated_at": now}, merge=True)

    def settle(self, workspace_id: str, job_id: str, *, provider_event_id: str,
               actual_units: int, final: bool = False) -> dict[str, Any]:
        if not 1 <= len(provider_event_id) <= 96 or type(actual_units) is not int or actual_units < 0:
            raise InvalidRecord("Invalid usage settlement")
        reservation = self.client.collection("workspaces").document(
            workspace_id).collection("usage_reservations").document(job_id)
        workspace_usage = self.client.collection("workspaces").document(
            workspace_id).collection("usage").document("total")

        @firestore.transactional
        def write(tx: Transaction) -> dict[str, Any]:
            data = reservation.get(transaction=tx).to_dict()
            if not data or not data.get("counter_day"):
                raise InvalidRecord("Budget reservation unavailable")
            events = cast(dict[str, int], data.get("provider_events", {}))
            if provider_event_id in events and events[provider_event_id] != actual_units:
                raise InvalidRecord("Provider event reused with different usage")
            if provider_event_id in events and not final:
                return cast(dict[str, Any], data)
            if provider_event_id in events and data.get("status") == "settled":
                return cast(dict[str, Any], data)
            if data.get("status") == "settled" or len(events) >= 32:
                raise InvalidRecord("Reservation closed or event cap reached")
            refs = self._refs(Actor(data["actor_kind"], data["actor_id"]),
                              data["network_key"],
                              datetime.strptime(data["counter_day"], "%Y%m%d").replace(tzinfo=UTC))
            rows = [ref.get(transaction=tx).to_dict() or {} for ref in refs]
            workspace_row = workspace_usage.get(transaction=tx).to_dict() or {}
            previous_charge = data.get("charged_units", data["estimated_units"])
            new_events = {**events, provider_event_id: actual_units}
            actual = sum(new_events.values())
            charge = actual if final else max(actual, data["estimated_units"])
            delta = charge - previous_charge
            for index, (ref, row) in enumerate(zip(refs, rows, strict=True)):
                update = {"units": max(0, row.get("units", 0) + delta)}
                if index == 0 and final:
                    update["active_jobs"] = max(0, row.get("active_jobs", 0) - 1)
                tx.update(ref, update)
            tx.update(workspace_usage, {"reserved_units": max(
                0, workspace_row.get("reserved_units", 0) + delta)})
            update = {"provider_events": new_events, "actual_units": actual,
                      "charged_units": charge, "status": "settled" if final else "reserved",
                      "updated_at": datetime.now(UTC)}
            tx.update(reservation, update)
            return {**data, **update}

        return cast(dict[str, Any], write(self.client.transaction(max_attempts=5)))


__all__ = ["BudgetExceeded", "ChallengeRequired", "FirestoreUsage"]
