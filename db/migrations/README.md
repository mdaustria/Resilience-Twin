# Firestore schema v1 (Task 4.1)

These are application-enforced records, not SQL migrations. Deploy rules and
indexes separately, then run versioned, idempotent data upgrades with a
dedicated migration identity. Runtime services cannot change schema or rules.
Unknown `schema_version` values fail closed; upgrades preserve sealed versions.

ADR-031 narrows operational v1 writes and reads to temporary owners. The prior
account-capable implementation may have left v1 account or mixed records in an
existing database. Do not convert, delete, relabel or expose those records in
the guest flow. The runtime rejects them; a migration identity must inventory
and quarantine them under a separately reviewed data disposition before any
production rollout. A new database starts empty. Before enabling writes against
an existing database, inspect its ID, rules, indexes and owner/workspace records.
Do not stamp unrelated or unversioned records as v1. Later upgrades must be idempotent,
checkpointed by schema version and record ID, use revision preconditions, and
leave immutable seals unchanged. The runtime continues to reject unknown
versions during a staged rollout.

## Paths and bounds

* `owners/temporary:{owner_id}`: required aware future `expires_at` and
  `tombstoned_at`. Account owner rows are inaccessible to this repository.
* `browser_sessions/{sha256_handle}` (Task 4.2): digest-only server record with
  `temporary_owner_id`/`temporary_workspace_id` references;
  `created_at`, `last_user_activity_at`,
  `expires_at`, `absolute_expires_at`, and `revoked_at`. The raw 256-bit handle
  exists only in the host-only `__session` cookie. A server transaction creates
  this record together with its temporary owner and one workspace. Reads and
  renewals check all three records and the two expiry clocks; Firestore TTL is
  cleanup only. Existing v1 records need no backfill because the collection is
  new. New guest records carry no account reference fields. Reads and renewals
  reject legacy records with a non-null account reference; issuance never copies
  such references. Legacy mixed records remain for separately reviewed
  disposition and grant no guest access.
* `workspaces/{workspace_id}`: `owner_type=temporary`, one `owner_id`, optional
  `owner_temporary_session_id` equal to that ID during transition, and no
  non-null `owner_user_id`; plus `schema_version`, `revision`, `created_at`,
  `tombstoned_at`. One workspace per temporary owner; no transfer command.
* `workspaces/{workspace_id}/artifacts/{artifact_id}`: immutable Storage key,
  generation, SHA-256, byte count, kind, optional geometry CRS and bounding box.
* `.../evidence/{evidence_id}`: source artifact ID, physical-page citation,
  bounded claim metadata and revision.
* `.../twins/{twin_id}`: mutable draft metadata and revision.
* `.../twins/{twin_id}/versions/{version_id}`: immutable seal, parent version,
  source artifact, accepted evidence IDs, input/artifact hashes and created time.
* `.../{reviews|scenarios|proposals}/{entity_id}` (Task 4.5): owner-checked
  mutable review draft or immutable scenario/proposal head, revision, content
  hash and canonical JSON content. Firestore cannot store nested arrays, so
  canonical JSON preserves the typed domain structure within the 128 KiB bound.
  `history/{zero-padded revision}` records the attributed change; `versions/`
  stores immutable seals. `.../idempotency/{scoped hash}` binds actor, workspace,
  route, key and request hash to the exact committed result. A different payload
  with the same scoped key conflicts. Review readiness remains recomputable from
  the saved draft and is stored beside it for reconnect and gap-only inspection.

Every private child carries `workspace_id`. Server transactions check path and
all references under that workspace; Firestore has no foreign keys. Large PDFs,
page text, reviewed geometry, graphs and event bundles live in immutable Storage
artifacts. The repository caps each serialized metadata document at 128 KiB and
bounded transactions below Firestore's 1 MiB document and 10 MiB request
limits. A Task 4.6 submission uses seven writes; it is capped by its fixed
document set and does not loop over unbounded members. These are application
bounds.

## Query/index coverage

List workspaces by `owner_type`, `owner_id`, `tombstoned_at == null`, ordered
by `created_at` then document ID; the composite index is in
`firestore.indexes.json`. Versions are listed under one twin path by creation
time and ID using automatic single-field indexing. Artifact/evidence/version
lookups use exact workspace-relative paths. Geometry discovery uses scoped
bounds metadata, then Python verifies geometry and CRS from the immutable
Storage artifact. Firestore is not a spatial database.

Transactions read owner, workspace and references before writes. Expected
revision is checked inside the transaction. Retry callbacks have no external
effects; contention retries are bounded and ultimately fail closed. Emulator
and nonproduction smoke evidence are required by Task 4.1 acceptance.

Job submission reads ownership, idempotency and workspace usage before writing
the command, job, attempt, run, outbox, reservation and usage tally atomically.
The outbox is the committed dispatch obligation; queue calls occur afterward.
