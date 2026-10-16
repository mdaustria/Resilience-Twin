# Retention and deletion runbook (local design)

Temporary access ends after two hours without deliberate activity or 24 hours
from creation, whichever comes first. Authorization checks the server clock on
every request and worker publication; the sweep is not the access gate. End
and delete tombstones the workspace first. Workers must not publish after the
tombstone.

Run the expiry sweep at least hourly. Run the active-copy purge at least hourly
for every tombstoned workspace, immediately repeating pages while either
objects or database documents were removed. Each page removes at most 100
object generations and 100 descendant documents. Keep a durable work item for
each tombstone until a zero/zero pass, then check again for late artifacts on
subsequent hourly sweeps through the 24-hour deadline. Alert before 12 hours
of backlog and escalate before 20 hours. Size worker throughput against the
largest permitted workspace before claiming the 24-hour active-copy bound.
The executable one-pass worker is `python -m services.worker.purge --project
ai-projects-250716 --database resillience-twin --bucket
ai-projects-250716-resilliencetwin`; it requires `RT_PURGE_ENABLED=1` and a
workload identity with Firestore and object-list/delete access. The exact
nonproduction command and UTC hourly schedule are recorded in
`release/validation/retention/scheduler.json`. It expires a bounded page,
processes due tombstones, drains each workspace in bounded pages, and saves the
next hourly sweep only after a zero/zero pass. A crash leaves the tombstone due.
The local emulator rehearsal in `test_purge.py` invokes two scheduled cycles,
including a late object. Phase 6.2 must provision the actual Cloud Scheduler
trigger and job identity; Task 6.4 must record provider deadline measurements
and restore behavior.

Purge is scoped to the exact `workspaces/{workspace_id}/` object prefix and
leaves a minimal root tombstone for revocation and accounting. The object
adapter enumerates generations so archived versions are included; verify
actual bucket soft-delete/version settings, object listing permissions and
provider retention before deployment. Firestore descendant records include
jobs, attempts, versions, events, reviews and upload metadata. Do not delete
another owner's copy of a source PDF even when the SHA-256 matches.

Backups containing temporary content must expire within seven days; this is
a release configuration and Task 6.4 verification requirement, not something
the local emulator proves. Provider-side retention and permitted stored AI
outputs require separate provider review. Downloaded reports remain with the
user. Do not describe temporary mode as zero-storage or physical instant
erasure.
