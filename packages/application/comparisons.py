"""Owner-scoped evaluation of sealed proposals against completed paired run evidence."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from packages.contracts.outcomes import Outcome
from packages.domain.comparisons import MemberResult, PairedRun, compare_pairs
from packages.domain.findings import Occurrence, derive_findings


class VersionReader(Protocol):
    def read(self, actor: Any, workspace_id: str, kind: str,
             entity_id: str) -> dict[str, Any]: ...


class RunReader(Protocol):
    def read_member_outcome(self, actor: Any, workspace_id: str,
                            job_id: str) -> dict[str, Any] | None: ...


class PrivateComparisons:
    def __init__(self, versions: VersionReader, runs: RunReader) -> None:
        self.versions = versions
        self.runs = runs

    def evaluate(self, actor: Any, workspace_id: str, proposal_id: str,
                 baseline_job_ids: list[str], variant_job_ids: list[str]) -> dict[str, Any]:
        proposal = self.versions.read(actor, workspace_id, "proposals", proposal_id)
        if not proposal["sealed"]:
            raise ValueError("Proposal must be sealed")
        content = proposal["content"]
        baseline = self.versions.read(actor, workspace_id, "baselines", content["baseline_id"])
        suite = self.versions.read(actor, workspace_id, "scenario_suites", "main")
        base = baseline["content"]
        plan = suite["content"]
        member_ids = plan["scenario_ids"]
        if (not 1 <= len(member_ids) <= 50 or len(baseline_job_ids) != len(member_ids)
                or (variant_job_ids and len(variant_job_ids) != len(member_ids))
                or len(set(baseline_job_ids + variant_job_ids)) !=
                len(baseline_job_ids + variant_job_ids)
                or content["baseline"]["baseline_hash"] != base["baseline_hash"]
                or plan["baseline_hash"] != base["baseline_hash"]):
            raise ValueError("Pair members or immutable baseline differ")
        source_hashes = tuple(base["resources"]["source_hashes"])
        expected = {"source_hashes": source_hashes,
                    "scenario_suite_hash": plan["suite_hash"],
                    "scope_hash": base["review_hash"],
                    "graph_hash": base["graph_hash"]}

        def members(job_ids: list[str], input_hash: str) -> tuple[tuple[MemberResult, ...],
                                                                  tuple[dict[str, Any], ...]]:
            rows = []
            records = []
            for member_id, exogenous_hash, job_id in zip(
                member_ids, plan["scenario_hashes"], job_ids, strict=True
            ):
                record = self.runs.read_member_outcome(actor, workspace_id, job_id)
                records.append(record or {})
                if record is None:
                    rows.append(MemberResult(member_id, exogenous_hash, "failed", None))
                    continue
                pins = record["pins"]
                if (pins.get("input_hash") != input_hash
                        or tuple(pins.get("source_hashes", ())) != expected["source_hashes"]
                        or pins.get("scenario_suite_hash") != expected["scenario_suite_hash"]
                        or pins.get("scope_hash") != expected["scope_hash"]
                        or pins.get("graph_hash") != expected["graph_hash"]
                        or pins.get("exogenous_hash") != exogenous_hash
                        or record["member_id"] != member_id):
                    raise ValueError("Completed member pins differ from sealed inputs")
                raw = record["outcome"]
                numbers = (raw["on_time_people"], raw["vulnerable_on_time_people"],
                           raw["water_unmet_ml"], raw["stranded_people"])
                if any(type(value) is not int or value < 0 for value in numbers):
                    raise ValueError("Run outcome quantities are invalid")
                outcome = Outcome(*numbers, tuple(raw["evidence_event_ids"]))
                rows.append(MemberResult(member_id, exogenous_hash, "completed", outcome))
            return tuple(rows), tuple(records)

        before_members, before_records = members(baseline_job_ids, base["baseline_hash"])
        after_members, after_records = (members(variant_job_ids,
            content["variant"]["variant_hash"]) if variant_job_ids else ((), ()))
        first_complete = next((record for record in before_records if record), None)
        if first_complete is None:
            return {"status": "untested", "reason": "No completed baseline member outcomes",
                    "measured_improvement": False, "deltas": [], "findings": [],
                    "planned_members": len(member_ids), "completed_baseline_members": 0,
                    "operations": content["operations"], "variant": content["variant"]}
        engine_hash = first_complete["pins"]["engine_hash"]
        policy_version = first_complete["pins"]["policy_version"]

        def paired(input_hash: str, rows: tuple[MemberResult, ...],
                   records: tuple[dict[str, Any], ...]) -> PairedRun:
            for record in records:
                if record and (record["pins"]["engine_hash"] != engine_hash
                               or record["pins"]["policy_version"] != policy_version):
                    raise ValueError("Engine or policy pins differ within the pair")
            return PairedRun(input_hash, source_hashes, plan["suite_hash"],
                base["review_hash"], base["graph_hash"], engine_hash,
                policy_version, rows)

        before = paired(base["baseline_hash"], before_members, before_records)
        after = (paired(content["variant"]["variant_hash"], after_members, after_records)
                 if variant_job_ids else None)
        comparison = compare_pairs(before, after,
                                   variant_baseline_hash=base["baseline_hash"])
        occurrences = []
        cohort_people: dict[str, int] = {}
        for member_id, member in zip(member_ids, before_members, strict=True):
            if member.outcome is None:
                continue
            scenario = self.versions.read(actor, workspace_id, "scenarios", member_id)
            demand = scenario["content"].get("editor", {}).get("demand_people")
            if type(demand) is not int or demand <= 0:
                continue
            cohort = "modeled_cohort"
            if cohort in cohort_people and cohort_people[cohort] != demand:
                raise ValueError("Paired members use different modeled cohort sizes")
            cohort_people[cohort] = demand
            missed = max(0, demand - member.outcome.on_time_people)
            if missed and member.outcome.evidence_event_ids:
                occurrences.append(Occurrence(member_id, "not_on_time", "modeled_cohort",
                    cohort, missed, member.outcome.evidence_event_ids[-1]))
        completed = tuple(item.member_id for item in before_members if item.outcome is not None)
        findings = derive_findings(tuple(occurrences), completed,
                                   tuple(member_ids), cohort_people)
        return {"status": comparison.status, "reason": comparison.reason,
                "measured_improvement": comparison.measured_improvement,
                "priority_label": comparison.priority_label,
                "paired_member_ids": comparison.paired_member_ids,
                "excluded_member_ids": comparison.excluded_member_ids,
                "deltas": [asdict(item) for item in comparison.deltas],
                "findings": [asdict(item) for item in findings],
                "planned_members": len(member_ids),
                "completed_baseline_members": len(completed),
                "operations": content["operations"], "variant": content["variant"],
                "policy_version": policy_version,
                "source_hashes": source_hashes,
                "baseline_hash": base["baseline_hash"],
                "variant_hash": content["variant"]["variant_hash"]}


__all__ = ["PrivateComparisons"]
