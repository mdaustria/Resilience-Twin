# Resilience Twin: implementation plan

Planning baseline: 12 October 2026. Target: production public self-service application, beginning with a local POC. The repository contains documentation and an empty structural scaffold; all implementation tasks below remain unstarted.

Authority: [PRD.md](PRD.md) governs scope and acceptance; [architecture.md](architecture.md) governs design; read [architecture-essentials.md](architecture-essentials.md) before editing. Follow the root [agent guide](../AGENTS.md) and the latest [progress entry](progress.md).

## How to use this plan

- Choose one unchecked task whose dependencies are done. Each task is one bounded deliverable for a fresh session. If inspection reveals more work than fits, split it here before implementation and preserve its acceptance criteria.
- Every task also includes `docs/plan.md` and `docs/progress.md` in its file scope. A directory path permits only files needed for the named task, not unrelated changes. Explain additional file changes in the handoff.
- Commands run from the repository root. These are planned command contracts: the task introducing a command/test must implement it. Missing files, zero collected tests, skipped mandatory integration checks, missing credentials, and absent review evidence cannot count as passing.
- Task 1.1 establishes approved runtime versions and lockfiles. Ask before adding any dependency, including development tools and dependencies already suggested by the architecture. Documentation work does not grant dependency approval.
- After a task's check and observable behavior pass, mark it `[x]` and log exact results/artifact paths. Otherwise leave `[ ]`, record partial/blocked status and the next action. Run the combined check once available for implementation changes; documentation-only edits can use the current check in `AGENTS.md` plus link/plan inspection.
- Human gates require actual named reviewers, dated decisions, and versioned evidence. A validator checks that evidence; it does not provide independent judgment. Do not relax prespecified tolerances after seeing held-out results.

## User-requested structural preparation

- [x] 0.1 Reserve the complete planned structure without implementation
  - Goal: Create every explicitly named file and directory in phases 1–6, plus the architecture folder map, with purpose/task/uses/TODO headers and empty module exports only. Structure is ready for review; the requested working build/test startup remains blocked on Task 1.1.
  - Files: All file and directory entries in phases 1–6; architecture §4 directory placeholders; `docs/scaffold-tree.md`, `docs/architecture.md`, `docs/architecture-essentials.md`, `docs/plan.md`, `docs/progress.md`. Preserve existing document content. This explicit user request overrides Task 1.1's instruction against broad scaffolding for this preparation only.
  - Depends on: none for structure; approved runtimes/dependencies and Task 1.1 configuration for build/test startup.
  - Conventions: Python files export an empty `__all__`; TypeScript/JavaScript modules export nothing (configuration modules have empty default exports). Directory-only scopes receive an initializer, index, or comment-only README so Git preserves them. JSON uses a `_comment` array because JSON has no comments. Generated client and deferred search locations contain README placeholders only. Uses names intended future file dependencies, not executable imports; README references identify locations awaiting concrete files.
  - **Done when:** The PowerShell path/header audit described in `docs/progress.md` passes, `tree /F /A` matches `docs/scaffold-tree.md`, and Task 1.1 establishes a real build and test-runner startup. Do not count empty tests or no-op scripts as passing checks. Keep unchecked until the runnable portion is verified.
  - Review: Commit only after the user approves the tree, using `scaffold: empty structure`. No dependency installation, generated contracts, data-model implementation, fixtures, infrastructure, or milestone signoff is authorized by this scaffold.

## Phase 1: Walking skeleton

Day-one integration target: complete 1.1–1.3 as the first vertical slice, subject to dependency approval. One synthetic case travels from browser to generated client to API to pure engine and back with computed results. Keep it local, small, and visibly provisional. Full geography, AI extraction, cloud infrastructure, and public onboarding come after this path works.

- [x] 1.1 Bootstrap the smallest runnable workspace
  - Goal: Propose exact compatible runtimes and minimal dependencies, obtain approval, then create the Python/web workspaces and local launch scripts. Select the client generator through one tiny schema fixture. Do not scaffold every future package.
  - Files: `release/dependencies.md`, `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.gitignore`, `apps/web/package.json`, `apps/web/index.html`, `apps/web/src/main.tsx`, `apps/web/src/generated/bootstrap.ts`, `apps/web/tsconfig.json`, `apps/web/vite.config.ts`, `apps/web/eslint.config.js`, `services/api/`, `scripts/dev.mjs`, `scripts/check_bootstrap.mjs`, `scripts/generate_client.py`, `tests/contracts/test_bootstrap.py`, `AGENTS.md`. The generated client file is required to type-check the Python-derived response; ignored `.runtime/` holds only local approved tools.
  - Depends on: none; dependency approval is required before installing or adding packages.
  - **Done when:** `pnpm check:bootstrap` passes and frozen installs resolve, the web/API launch locally, a generated tiny client type-checks, and the guide's install/run/test/lint commands match actual scripts.

- [x] 1.2 Connect a synthetic case through the real API and pure engine
  - Goal: Define a minimal versioned input/result schema and compute one hand-calculated evacuation/water case through an application use case. Return validation errors for missing inputs. Use an isolated local fixture owner and synthetic in-memory adapters, explicitly disabled outside development.
  - Files: `packages/contracts/`, `packages/application/`, `packages/simulation/`, `packages/adapters/local/`, `packages/client-generated/`, `services/api/`, `tests/fixtures/skeleton/`, `tests/integration/test_skeleton_api.py`, `tests/contracts/test_skeleton_contract.py`, `scripts/dev.mjs`, `scripts/generate_client.py`, `apps/web/eslint.config.js`. The two scripts are needed to enable the isolated fixture only under the local dev launch and regenerate its Python-derived browser contract. The ESLint config excludes the prior build output so repeat checks remain valid.
  - Depends on: 1.1.
  - **Done when:** `uv run pytest tests/integration/test_skeleton_api.py tests/contracts/test_skeleton_contract.py` passes and an HTTP request computes the expected result through the engine, rejects invalid data, and cannot read a second fixture owner's case. This tiny synchronous fixture endpoint must not accept production workloads.

- [ ] 1.3 Add a browser-to-engine smoke flow
  - Goal: Add one minimal review/run/result surface using the generated client. Show source/assumption labels, computed arrivals and water shortfall, and a recoverable API error. Keep the smoke flow within the future four-screen structure.
  - Files: `apps/web/src/app/`, `apps/web/src/features/community-twin/`, `apps/web/src/features/simulation/`, `apps/web/src/lib/`, `tests/e2e/walking-skeleton.spec.ts`, `playwright.config.ts`, `package.json`, `release/dependencies.md`, `pnpm-lock.yaml`.
  - Depends on: 1.2; approval for any test dependencies not approved in 1.1.
  - **Done when:** `pnpm exec playwright test tests/e2e/walking-skeleton.spec.ts` passes against a real local API and the browser shows the hand-calculated synthetic result without hardcoded response metrics or mocked HTTP.

- [ ] 1.4 Make the integration path repeatable in CI
  - Goal: Add one combined check for lint, types, Python/web tests, generated-contract drift, and the browser smoke flow. Test import boundaries; make missing prerequisites fail with actionable messages. Extend this check as later suites and database prerequisites appear.
  - Files: `scripts/check.py`, `scripts/generate_client.py`, `package.json`, `.github/workflows/check.yml`, `tests/contracts/test_import_boundaries.py`, `tests/contracts/test_generated_client.py`, `AGENTS.md`.
  - Depends on: 1.3.
  - **Done when:** `pnpm check` passes from a clean install and CI reproduces the same browser/API/engine flow; changing a Python contract without regenerating the client makes the check fail.

## Phase 2: Deterministic model proof — milestone A, engine work

Build reviewed synthetic/reference cases before scaling the engine. All calculations remain pure and deterministic. Routing selection is a gate for the production compiler, not permission to implement unsupported road semantics.

- [ ] 2.1 Freeze the independent validation protocol
  - Goal: Record benchmark scope, calibration/held-out separation, numeric tolerances, boundary cases, severity-review procedure, and reference evidence with product/engineering and independent domain reviewers. Begin with synthetic/redacted cases while real-document processing remains gated.
  - Files: `docs/validation-protocol.md`, `tests/fixtures/validation/`, `tests/contracts/test_validation_protocol.py`, `release/validation/protocol.json`.
  - Depends on: 1.4; actual independent reviewers and permitted reference evidence must be available for completion.
  - **Done when:** `uv run pytest tests/contracts/test_validation_protocol.py` passes and named reviewers have approved a versioned protocol before held-out scoring, including arrival-time, evacuated-population, and water-shortfall tolerances.

- [ ] 2.2 Define complete operational inputs and canonical run manifests
  - Goal: Add typed entities, unique initial cohorts, units, evidence/assumption references, deterministic scenario metadata, and content hashes. Reject non-finite values, duplicate occupants, missing required resources, and impossible counts.
  - Files: `packages/contracts/`, `packages/domain/inputs/`, `packages/client-generated/`, `tests/contracts/test_operational_inputs.py`, `tests/contracts/test_run_manifest.py`, `tests/fixtures/inputs/`.
  - Depends on: 2.1.
  - **Done when:** `uv run pytest tests/contracts/test_operational_inputs.py tests/contracts/test_run_manifest.py` passes and canonical manifests are stable across reordered input objects while material value changes alter their hashes.

- [ ] 2.3 Implement the small reference router and road fixtures
  - Goal: Implement deterministic exact-edge routing on a reviewed small graph, covering one-way access, ties, closures, vehicle profiles, and turn restrictions. Explicitly block unsupported/ambiguous restrictions rather than treating them as traversable.
  - Files: `packages/simulation/routing/`, `tests/engine/test_reference_routing.py`, `tests/fixtures/roads/`, `release/validation/road-sample.md`.
  - Depends on: 2.2; approval for NetworkX if not already recorded.
  - **Done when:** `uv run pytest tests/engine/test_reference_routing.py` passes and expected edge paths match reviewed cases including both bridge directions, node-via/way-via handling, disconnected access, equal-cost paths, and boundary cuts.

- [ ] 2.4 Complete the routing reuse decision
  - Goal: Compare the reference path with a maintained routing candidate on the same sample; record restriction coverage, exact closures, reproducibility, memory, latency, and integration effort. Select one production implementation in a superseding ADR and update the dependency matrix.
  - Files: `scripts/benchmark_routing.py`, `tests/contracts/test_routing_decision.py`, `release/routing/`, `release/dependencies.md`, `docs/architecture.md`, `docs/architecture-essentials.md`.
  - Depends on: 2.3; obtain approval before adding candidate tools/dependencies.
  - **Done when:** `uv run pytest tests/contracts/test_routing_decision.py` passes and the ADR links measured comparison artifacts and names one selected implementation, supported semantics, and explicit exclusions. Neither an unevaluated choice nor two production routers passes this gate.

- [ ] 2.5 Implement population states, event ordering, and horizon accounting
  - Goal: Add the stable event queue, exclusive cohort states, deadline inclusivity, and terminal event. Preserve pending demand and unfinished movements at the horizon; bound same-time event scheduling.
  - Files: `packages/simulation/kernel/`, `packages/simulation/metrics/population.py`, `tests/engine/test_population.py`, `tests/engine/test_event_boundaries.py`, `tests/fixtures/engine/boundaries/`.
  - Depends on: 2.2.
  - **Done when:** `uv run pytest tests/engine/test_population.py tests/engine/test_event_boundaries.py` passes and hand-calculated fixtures conserve every initial occupant/resident, process same-time disruptions before completions, and never turn unfinished work into success.

- [ ] 2.6 Implement water accounting through the final interval
  - Goal: Integrate integer milliliter consumption with retained remainder, exact exhaustion crossings, supply-location tracking, and unmet demand. Separate safe arrival from water sufficiency.
  - Files: `packages/simulation/kernel/water.py`, `packages/simulation/metrics/water.py`, `tests/engine/test_water.py`, `tests/fixtures/engine/water/`.
  - Depends on: 2.5.
  - **Done when:** `uv run pytest tests/engine/test_water.py` passes and initial occupants, waiting/transit cohorts, an empty event queue, and the horizon's final interval have exact expected consumption without negative stock or lost shortage.

- [ ] 2.7 Enforce trip feasibility and reservations
  - Goal: Add one reusable feasibility check for vehicle seats, assistance, shelter reservations, dedicated crew/vehicle windows, and finite distance budgets. Account for empty travel, loading/unloading, return legs, cancellation, rerouting, and stranded passengers.
  - Files: `packages/simulation/kernel/resources.py`, `packages/simulation/policies/feasibility.py`, `tests/engine/test_trip_feasibility.py`, `tests/engine/test_reservations.py`, `tests/fixtures/engine/resources/`.
  - Depends on: 2.3, 2.5, 2.6.
  - **Done when:** `uv run pytest tests/engine/test_trip_feasibility.py tests/engine/test_reservations.py` passes and concurrent trips cannot double-book seats/vehicles, overfill a shelter, extend a crew window, exceed remaining distance, or erase stranded residents after a disruption.

- [ ] 2.8 Implement deterministic allocation and observed-condition replanning
  - Goal: Implement `deadline_greedy_v1` with stable ties and fixed iteration budgets. Apply the documented atomic-edge closure rule and explicit vehicle outages; keep future unknown events out of policy observations.
  - Files: `packages/simulation/policies/deadline_greedy.py`, `packages/simulation/kernel/observations.py`, `packages/simulation/kernel/disruptions.py`, `tests/engine/test_allocation.py`, `tests/engine/test_knowledge_boundary.py`.
  - Depends on: 2.7.
  - **Done when:** `uv run pytest tests/engine/test_allocation.py tests/engine/test_knowledge_boundary.py` passes and identical inputs produce identical choices, unseen future disruptions do not affect decisions, and a safety-first water-deficient arrival exposes its shortfall.

- [ ] 2.9 Add serializable checkpoints and deterministic replay
  - Goal: Save queue, cohort/resource state, reservations, water remainders, observations, and deterministic sequence state in validated artifacts; resume without new provider calls or executable object serialization.
  - Files: `packages/contracts/checkpoints.py`, `packages/simulation/kernel/checkpoints.py`, `packages/simulation/runner.py`, `tests/engine/test_replay.py`, `tests/engine/test_checkpoint_resume.py`.
  - Depends on: 2.8.
  - **Done when:** `uv run pytest tests/engine/test_replay.py tests/engine/test_checkpoint_resume.py` passes and resumed versus uninterrupted runs have identical canonical event/metric hashes, including mid-trip and water-exhaustion boundaries.

- [ ] 2.10 Freeze scenarios, suites, and hypothetical variants
  - Goal: Validate structured hazards and explicit effects, derive stable seeded streams, and create typed preparatory variants without modifying the baseline. Support conserved pre-scenario water redistribution and declared resource additions; reject deferred resupply/refueling operations.
  - Files: `packages/contracts/scenarios.py`, `packages/domain/scenarios/`, `packages/domain/proposals/`, `tests/engine/test_scenario_suites.py`, `tests/engine/test_proposals.py`, `tests/fixtures/scenarios/`.
  - Depends on: 2.2, 2.8.
  - **Done when:** `uv run pytest tests/engine/test_scenario_suites.py tests/engine/test_proposals.py` passes and invalid targets/counts fail, unrelated entities do not shift existing random draws, and applying a variant preserves source/baseline hashes and resource conservation.

- [ ] 2.11 Derive findings and paired comparison metrics
  - Goal: Link numeric findings to engine events, count unique affected cohorts and evaluable suite members, and compare baseline/variant under identical exogenous inputs. Show vulnerable-group effects, regressions, incomplete members, and provisional priority labels until thresholds are reviewed.
  - Files: `packages/domain/findings/`, `packages/domain/comparisons/`, `packages/simulation/metrics/`, `tests/engine/test_findings.py`, `tests/engine/test_comparisons.py`.
  - Depends on: 2.9, 2.10.
  - **Done when:** `uv run pytest tests/engine/test_findings.py tests/engine/test_comparisons.py` passes and one disrupted baseline/variant pair exposes evidence-backed deltas and regressions; partial suites, model changes, and untested proposals cannot claim measured plan improvement.

- [ ] 2.12 Add reference-policy and sensitivity experiments
  - Goal: Implement `earliest_deadline_reference_v1` using shared feasibility checks, then low/nominal/high one-factor experiments and an agreed adverse combination. Add tiny exhaustive reference cases to quantify heuristic limitations.
  - Files: `packages/simulation/policies/earliest_deadline_reference.py`, `packages/application/experiments/`, `tests/engine/test_reference_policy.py`, `tests/engine/test_sensitivity.py`, `tests/fixtures/validation/sensitivity/`, `release/validation/sensitivity/`.
  - Depends on: 2.1, 2.11.
  - **Done when:** `uv run pytest tests/engine/test_reference_policy.py tests/engine/test_sensitivity.py` passes and travel/loading/demand-timing/water-use experiments preserve identical conditions within each pair, expose outcome ranges and fixture rank reversals, and label policy-dependent failures without claiming optimality or real-world probabilities.

## Phase 3: Evidence and geography proof — milestone A exit

Use a minimal local review surface and one permitted public plan plus reviewed road sample. Do not start the broad public workspace build until 3.9 passes. Real documents/provider calls require the settings and processing gate in 3.1; deterministic tests use saved permitted fixtures.

- [ ] 3.1 Resolve document-processing and remaining dependency choices
  - Goal: Record consent/processing terms, exact Gemini model/region/SDK, retention behavior, and remaining runtime/native-library compatibility. Select the PDF validator/scanner through bounded malformed/encrypted/unsafe-document fixtures; obtain approval for additions.
  - Files: `release/dependencies.md`, `release/providers.json`, `docs/document-processing.md`, `scripts/probe_document_tools.py`, `tests/contracts/test_provider_configuration.py`, `tests/fixtures/pdf-validation/`, `pyproject.toml`, `uv.lock`.
  - Depends on: 1.4, 2.1; product/provider decisions and permitted pilot-document evidence are required.
  - **Done when:** `uv run pytest tests/contracts/test_provider_configuration.py` passes and dated configuration/compatibility evidence names exact approved tools, consent terms, source permissions, and provider retention with no unapproved global fallback or floating model alias.

- [ ] 3.2 Validate and preserve a local PDF artifact
  - Goal: Build a quarantined local intake adapter that checks actual bytes, limits, signature, encryption, scanning, readability, checksum, and physical page mapping. Preserve source bytes and expose repairable errors without executing document scripts.
  - Files: `packages/application/documents/`, `packages/adapters/storage/local.py`, `packages/adapters/documents/`, `packages/contracts/documents.py`, `tests/integration/test_pdf_intake.py`, `tests/fixtures/documents/`.
  - Depends on: 3.1.
  - **Done when:** `uv run pytest tests/integration/test_pdf_intake.py` passes and valid fixtures retain their original checksum/citations while malformed, oversized, encrypted-unsupported, and unsafe fixtures never reach extraction.

- [ ] 3.3 Extract validated fact candidates with provenance
  - Goal: Add bounded page-group Gemini extraction, typed candidate validation, stable cross-page merging, and permitted raw artifact/version capture. Handle retryable provider failures, invalid units/citations, conflicts, and source prompt injection as unresolved data.
  - Files: `packages/adapters/ai/`, `packages/application/extraction/`, `packages/contracts/evidence.py`, `tests/contracts/test_extraction.py`, `tests/fixtures/extraction/`, `release/validation/extraction/`.
  - Depends on: 2.2, 3.2.
  - **Done when:** `uv run pytest tests/contracts/test_extraction.py` passes and a permitted configured-provider probe is recorded separately; extracted candidates have valid physical-page references, absent facts stay unknown, and saved fixture replay needs no fresh AI calls.

- [ ] 3.4 Review evidence and separate document review from run readiness
  - Goal: Add manual source metadata, assertions, assumptions, competing candidates, corrections, and a minimal citation/review panel. Implement readiness reasons, revision conflicts, immutable sealing, and hash-bound personal acknowledgment without official approval or URL fetching.
  - Files: `packages/domain/evidence/`, `packages/domain/readiness/`, `packages/domain/versions/`, `packages/application/review/`, `services/api/review.py`, `apps/web/src/features/community-twin/`, `tests/integration/test_evidence_readiness.py`, `tests/e2e/evidence-review.spec.ts`.
  - Depends on: 2.2, 3.3.
  - **Done when:** `pnpm exec playwright test tests/e2e/evidence-review.spec.ts` passes against the API and a missing-input case remains reviewable, a declared usable assumption can enable a run, and material edits invalidate the acknowledgment. Include `test_evidence_readiness.py` in the combined check.

- [ ] 3.5 Import and pin a small OSM sample
  - Goal: Import a checksummed regional/sample PBF into a catalog, preserving source date/license, polygon/buffer, complete way geometry, restriction relations, and extent-cut warnings. Keep the first fixture small; regional production execution comes later.
  - Files: `services/osm-import/`, `packages/adapters/geo/catalog.py`, `packages/adapters/geo/extract.py`, `tests/integration/test_osm_import.py`, `tests/fixtures/osm/`, `release/validation/geography/`.
  - Depends on: 2.4, 3.1.
  - **Done when:** `uv run pytest tests/integration/test_osm_import.py` passes and repeated import of the pinned sample yields the same source/extent artifacts with complete relevant restrictions and explicit boundary cuts.

- [ ] 3.6 Compile the selected production graph semantics
  - Goal: Implement only the router/compiler selected in 2.4. Preserve directed exact-edge paths, vehicle restrictions, crossings/layers, bridge asset groups, integer weights/projection, and conservative handling of unsupported restrictions.
  - Files: `packages/adapters/geo/compiler/`, `packages/simulation/routing/`, `packages/contracts/graphs.py`, `tests/integration/test_graph_compilation.py`, `tests/fixtures/roads/`, `release/validation/geography/`.
  - Depends on: 2.4, 3.5.
  - **Done when:** `uv run pytest tests/integration/test_graph_compilation.py` passes and the selected compiler matches the reviewed route fixtures; closures remove every relevant bridge segment/direction and ambiguous restrictions cannot silently create usable routes.

- [ ] 3.7 Review location, access connectors, and road assumptions
  - Goal: Add Geoapify suggestions, manual reviewed boundary/location fallback, and a small map with a matching table. Require review of pickup/facility connectors, unknown speeds, neighboring facilities, and graph assumptions before readiness.
  - Files: `packages/adapters/geo/geocoding.py`, `packages/domain/geography/`, `services/api/geography.py`, `apps/web/src/features/community-twin/`, `apps/web/src/components/map/`, `tests/e2e/geography-review.spec.ts`, `tests/fixtures/geocoding/`.
  - Depends on: 3.4, 3.6; approval for any remaining UI/geo dependencies.
  - **Done when:** `pnpm exec playwright test tests/e2e/geography-review.spec.ts` passes and ambiguous locations/unreachable connectors remain unresolved until reviewed; tile failure preserves tables and overlays, and cited/assumed neighboring resources never imply permission.

- [ ] 3.8 Render gap-only and evaluated proof reports
  - Goal: Add escaped, offline HTML/PDF templates with source metadata, citations, scope, assumptions, metrics, comparison regressions, attribution, and independent/untested labels. Keep optional AI explanations out of the required path.
  - Files: `packages/reports/`, `packages/application/reports/`, `tests/integration/test_reports.py`, `tests/fixtures/reports/`, `release/validation/reports/`.
  - Depends on: 2.11, 3.4; approval for renderer dependencies if still outstanding.
  - **Done when:** `uv run pytest tests/integration/test_reports.py` passes and rendered-page inspection records readable gap-only and paired-result PDFs, with no invented metrics for a non-run case, no remote-resource execution, and unchanged source PDF hashes.

- [ ] 3.9 Demonstrate and accept milestone A
  - Goal: Run one permitted public plan through extraction/review, document-gap export, baseline, disruption, and paired hypothetical change. Score held-out cases under the frozen protocol, adjudicate extraction, and record sensitivity, geographic review, and independent validity findings.
  - Files: `scripts/verify_release.py`, `tests/engine/test_held_out_validation.py`, `tests/e2e/model-proof.spec.ts`, `release/validation/milestone-a/`, `release/acceptance.json`.
  - Depends on: 2.1–2.12, 3.1–3.8; actual independent review is required.
  - **Done when:** `uv run python scripts/verify_release.py --milestone A` passes and links passing boundary/replay/held-out results, extraction adjudication, routing/dependency decisions, the complete proof demonstration, and dated independent review with no unresolved critical discrepancy. Stop milestone B work if this gate fails.

## Phase 4: Private ownership and durable work — milestone B, backend

Replace the local proof adapters incrementally with real PostgreSQL/PostGIS and private artifact storage. Reuse the validated domain/engine contracts. Public exposure remains gated on Phase 6.

- [ ] 4.1 Persist exclusive ownership and immutable versions in PostGIS
  - Goal: Add migrations/repositories for owners, workspaces, artifacts, evidence, twins, and versions. Enforce exactly one temporary/account owner, runtime RLS, revision checks, and immutable sealed records; test with a non-owner database role.
  - Files: `db/migrations/`, `db/seeds/`, `packages/adapters/persistence/`, `compose.yaml`, `tests/integration/test_owner_rls.py`, `tests/integration/test_version_storage.py`, `scripts/check.py`, `.github/workflows/check.yml`, `AGENTS.md`.
  - Depends on: 3.9; approval for database/ORM dependencies if not already recorded.
  - **Done when:** `uv run pytest tests/integration/test_owner_rls.py tests/integration/test_version_storage.py` passes against real PostGIS after migrations, and two owners of the same source checksum cannot read or mutate each other's records, including through pooled connections. Document local database startup and include it in CI checks.

- [ ] 4.2 Implement temporary-session creation and renewal
  - Goal: Issue digest-backed secure cookies, atomically create one workspace, enforce two-hour idle/24-hour absolute expiry using server time, and renew only deliberate activity. Add origin/CSRF protection, issuance-limit hooks, and race-safe revocation checks.
  - Files: `services/api/sessions.py`, `packages/application/sessions/`, `packages/adapters/persistence/sessions.py`, `db/migrations/`, `tests/integration/test_temporary_sessions.py`.
  - Depends on: 4.1.
  - **Done when:** `uv run pytest tests/integration/test_temporary_sessions.py` passes and refresh works with the same valid credential, polling never extends expiry, duplicate issuance reuses an active session, and late renewal cannot revive a revoked/expired owner.

- [ ] 4.3 Add optional account sessions and saved workspaces
  - Goal: Integrate configured Identity Platform session exchange, sign-out/recovery behavior, and saved-workspace ownership. Resolve temporary/account credentials by workspace owner without automatically attaching guest data.
  - Files: `services/api/accounts.py`, `packages/adapters/identity/`, `packages/application/workspaces/`, `tests/integration/test_account_sessions.py`, `tests/integration/test_mixed_credentials.py`, `release/providers.json`.
  - Depends on: 4.1, 4.2; approved identity provider configuration.
  - **Done when:** `uv run pytest tests/integration/test_account_sessions.py tests/integration/test_mixed_credentials.py` passes and both credential types can coexist without cross-authorization, sign-in leaves temporary work separate, and invalid/suspended account sessions fail closed.

- [ ] 4.4 Store private artifacts and authorize uploads/downloads
  - Goal: Replace local document storage with private GCS ports, quarantine/finalization checks, generations/checksums, and owner-checked downloads. Cap temporary upload authorization at expiry and use a revocable streaming proxy for temporary reads.
  - Files: `packages/adapters/storage/`, `packages/application/documents/`, `services/api/documents.py`, `services/api/artifacts.py`, `tests/integration/test_artifact_access.py`, `tests/integration/test_temporary_streams.py`.
  - Depends on: 3.2, 4.2, 4.3; configured nonproduction private storage or a faithful local test adapter.
  - **Done when:** `uv run pytest tests/integration/test_artifact_access.py tests/integration/test_temporary_streams.py` passes and wrong owners cannot finalize/read objects, expiry terminates long temporary downloads, and source bytes remain unchanged. Record real-cloud configuration checks at the release gate.

- [ ] 4.5 Connect evidence/scenario/proposal commands to durable versions
  - Goal: Persist the proof's review, readiness, sealing, scenarios, proposals, and change history behind owner-checked APIs. Enforce `If-Match`, scoped idempotency keys, stable problem details, and pagination.
  - Files: `services/api/review.py`, `services/api/scenarios.py`, `services/api/proposals.py`, `packages/application/`, `packages/adapters/persistence/`, `db/migrations/`, `tests/integration/test_version_commands.py`, `packages/client-generated/`.
  - Depends on: 4.1, 4.3, 4.4.
  - **Done when:** `uv run pytest tests/integration/test_version_commands.py` passes and stale edits or reused keys with different payloads return conflicts, restart preserves sealed history, and gap-only drafts remain saveable without simulation readiness.

- [ ] 4.6 Add transactional jobs, outbox, and usage reservations
  - Goal: Persist job/attempt/outbox/run state and reserve estimated usage atomically with expensive commands. Return `202` with stable IDs; verify remaining temporary lifetime before enqueueing.
  - Files: `db/migrations/`, `packages/application/jobs/`, `packages/adapters/persistence/jobs.py`, `services/api/jobs.py`, `services/api/runs.py`, `tests/integration/test_job_submission.py`.
  - Depends on: 4.5.
  - **Done when:** `uv run pytest tests/integration/test_job_submission.py` passes and duplicate commands create one logical job/reservation, transaction failure leaves no orphan accepted command, and insufficient session lifetime rejects work before dispatch.

- [ ] 4.7 Dispatch and claim work with leases and fencing
  - Goal: Add Cloud Tasks dispatch, authenticated worker entry, bounded retries, monotonically fenced leases, and reconciliation of outbox/lease crash windows. Keep stages explicit and bounded.
  - Files: `packages/adapters/tasks/`, `services/worker/dispatch.py`, `services/worker/leases.py`, `services/worker/reconcile.py`, `tests/integration/test_outbox_delivery.py`, `tests/integration/test_worker_fencing.py`.
  - Depends on: 4.6; approved Cloud Tasks dependencies/configuration.
  - **Done when:** `uv run pytest tests/integration/test_outbox_delivery.py tests/integration/test_worker_fencing.py` passes and enqueue/commit crash injection is safe, completed duplicates succeed without duplicating outputs, stale workers cannot publish, and task headers alone cannot authenticate execution.

- [ ] 4.8 Run extraction, graph, simulation, and report stages durably
  - Goal: Wrap existing use cases in bounded handlers, publish attempt artifacts with checkpoints, and schedule suite members independently. Aggregate durable child states, persist cursor-paged event chunks, and expose cancellation/retry/failure states.
  - Files: `services/worker/handlers/`, `packages/application/jobs/`, `packages/adapters/persistence/runs.py`, `services/api/runs.py`, `services/api/reports.py`, `tests/integration/test_stage_recovery.py`, `tests/integration/test_suite_jobs.py`.
  - Depends on: 4.7, 2.9, 3.3, 3.6, 3.8.
  - **Done when:** `uv run pytest tests/integration/test_stage_recovery.py tests/integration/test_suite_jobs.py` passes and a killed/resumed simulation matches uninterrupted output, failed suite members remain explicit, cancellation preserves labeled partial results, and task acknowledgment never leaves untracked work.

- [ ] 4.9 Enforce session, account, network, and global budgets
  - Goal: Implement issuance/concurrency/rate/cost limits, graduated challenge hooks, reservation settlement, and visible limit responses. Preserve completed downloads when compute quota is exhausted and account for shared networks.
  - Files: `packages/application/usage/`, `packages/adapters/persistence/usage.py`, `services/api/limits.py`, `services/worker/usage.py`, `release/limits.json`, `tests/integration/test_usage_limits.py`.
  - Depends on: 4.6, 4.8.
  - **Done when:** `uv run pytest tests/integration/test_usage_limits.py` passes and concurrent submissions/rotated guest cookies cannot bypass global or network caps, provider retries reconcile usage, and existing results remain downloadable until expiry.

- [ ] 4.10 Revoke, cancel, and tombstone on deletion or expiry
  - Goal: Implement explicit end/delete and expiry sweeps, with immediate authorization denial independent of sweep timing. Check owner expiry/tombstones at every worker publication and reject late uploads, renewals, and exports.
  - Files: `packages/application/deletion/`, `packages/adapters/persistence/`, `services/api/sessions.py`, `services/api/workspaces.py`, `services/worker/`, `tests/integration/test_deletion_races.py`, `tests/integration/test_expiry_races.py`.
  - Depends on: 4.4, 4.8.
  - **Done when:** `uv run pytest tests/integration/test_deletion_races.py tests/integration/test_expiry_races.py` passes and expiry/end during upload, run, or export immediately revokes access and prevents stale attempts from recreating published results; another owner's same-source copy survives.

- [ ] 4.11 Purge terminated workspace content and orphan artifacts
  - Goal: Reconcile in-flight/late objects, versions, derived data, and content-bearing database records after tombstoning; retain only the allowed minimal deletion/accounting records. Separate simulated-clock tests from real retention measurements.
  - Files: `services/worker/purge.py`, `packages/adapters/storage/`, `packages/adapters/persistence/deletion.py`, `tests/integration/test_purge.py`, `docs/retention-runbook.md`.
  - Depends on: 4.10.
  - **Done when:** `uv run pytest tests/integration/test_purge.py` passes and repeated cleanup plus injected late artifacts converges without cross-owner deletion, with a recorded schedule capable of the 24-hour active-copy bound. Real backup/provider retention is verified in 6.4, not assumed here.

## Phase 5: Complete the four-screen public flow — milestone B exit

Extend the working proof surfaces instead of rebuilding them. Use real owner-scoped APIs and generated contracts throughout; maps have equivalent tables and critical states have text labels.

- [ ] 5.1 Add temporary and saved onboarding with lifecycle feedback
  - Goal: Add Start temporary analysis and Sign in to save your work, processing terms/limits, expiry warnings, deliberate renewal, reconnect, and End and delete. Explain lost credentials, tab closure, and separate saved workspaces accurately.
  - Files: `apps/web/src/app/`, `apps/web/src/components/session/`, `apps/web/src/lib/`, `tests/e2e/onboarding-lifecycle.spec.ts`.
  - Depends on: 4.3, 4.9, 4.10.
  - **Done when:** `pnpm exec playwright test tests/e2e/onboarding-lifecycle.spec.ts` passes and a guest starts without an account, shared tabs/refresh retain valid ownership, expiry blocks further access, and sign-in never silently saves the guest analysis.

- [ ] 5.2 Connect Community Twin to private uploads and durable review
  - Goal: Connect upload progress/errors, citation inspection, reviewed locations, manual evidence, readiness checklist, revision conflicts, and baseline sealing to durable APIs. Keep review/export available for incomplete models.
  - Files: `apps/web/src/features/community-twin/`, `apps/web/src/components/`, `apps/web/src/lib/`, `tests/e2e/community-twin.spec.ts`.
  - Depends on: 5.1, 4.5, 4.8, 3.7.
  - **Done when:** `pnpm exec playwright test tests/e2e/community-twin.spec.ts` passes and a permitted fixture can be uploaded, corrected, cited, and sealed after reconnect, while missing inputs produce actionable simulation blockers rather than fabricated values.

- [ ] 5.3 Build the structured Scenario editor
  - Goal: Expose demand/deadlines, reviewed road closures, shelter/vehicle outages, explicit power/communication effects, horizon, assumptions, and saved suites. Display a deterministic summary with units and Asia/Manila times.
  - Files: `apps/web/src/features/scenario/`, `apps/web/src/lib/formatting.ts`, `tests/e2e/scenario-editor.spec.ts`.
  - Depends on: 5.2, 4.5.
  - **Done when:** `pnpm exec playwright test tests/e2e/scenario-editor.spec.ts` passes and invalid targets/intervals/resources show server validation, a reviewed scenario seals immutably, and narrative labels cannot silently change numeric engine inputs.

- [ ] 5.4 Build reconnectable Live Simulation playback
  - Goal: Add job progress, cursor-based polling with backoff, timeline/map/table playback, event inspection, and separate durable cancellation. Playback pause/speed controls affect only presentation.
  - Files: `apps/web/src/features/simulation/`, `apps/web/src/components/map/`, `apps/web/src/lib/polling.ts`, `tests/e2e/simulation-playback.spec.ts`.
  - Depends on: 5.3, 4.8.
  - **Done when:** `pnpm exec playwright test tests/e2e/simulation-playback.spec.ts` passes and reconnect resumes committed events without duplicates, partial/failed states stay visible, playback pause does not pause a worker, and polling does not renew temporary expiry.

- [ ] 5.5 Build findings, concrete proposal diffs, and comparisons
  - Goal: Display ranked evidence, gaps versus simulated failures, recurrence denominators, group outcomes, uncertainty/policy dependence, and typed proposal edits. Run paired comparisons and retain regressions and resource requirements.
  - Files: `apps/web/src/features/findings/`, `apps/web/src/components/`, `tests/e2e/findings-comparison.spec.ts`.
  - Depends on: 5.4, 4.5, 2.11, 2.12.
  - **Done when:** `pnpm exec playwright test tests/e2e/findings-comparison.spec.ts` passes and a user creates a hypothetical child variant, sees its exact diff and paired gains/regressions, and can trace quantities to events; unevaluated/partial variants cannot display a measured-improvement claim.

- [ ] 5.6 Connect independent report generation and downloads
  - Goal: Add gap-only, findings, and revision-report downloads using durable jobs and owner checks. Preserve source hashes, allow untested labeled recommendations, and keep completed exports accessible at compute limits until expiry.
  - Files: `apps/web/src/features/community-twin/`, `apps/web/src/features/findings/`, `apps/web/src/components/reports/`, `tests/e2e/report-downloads.spec.ts`, `tests/fixtures/reports/`.
  - Depends on: 5.2, 5.5, 4.4, 4.8, 3.8.
  - **Done when:** `pnpm exec playwright test tests/e2e/report-downloads.spec.ts` passes and guest/saved owners download correctly labeled reports, another owner is denied, expiry revokes temporary streaming, and report generation does not alter the original document.

- [ ] 5.7 Verify milestone B end to end and accessibility
  - Goal: Verify the complete temporary and saved journeys, keyboard navigation, text status/units, map-table equivalence, source preservation, same-PDF isolation, retries, replay, and lifecycle behavior against the durable backend.
  - Files: `tests/e2e/public-journeys.spec.ts`, `tests/e2e/accessibility.spec.ts`, `scripts/verify_release.py`, `release/validation/milestone-b/`, `release/acceptance.json`; fixes may touch only failing feature files identified in the handoff.
  - Depends on: 4.1–4.11, 5.1–5.6.
  - **Done when:** `uv run python scripts/verify_release.py --milestone B` passes and both real browser journeys plus owner-isolation/lifecycle/recovery checks have recorded evidence; a guest completes upload/review/run/compare/export without sign-in or an official-approval step.

## Phase 6: Operational verification and public beta — milestone C

These tasks establish production evidence, not inferred guarantees. Use separate development/staging/production environments. Provisioning, provider charges, and release actions must respect the user's actual authorization; preparing this plan authorizes none of those actions.

- [ ] 6.1 Define private data infrastructure and retention settings
  - Goal: Add Terraform for approved regions, Cloud SQL/PostGIS, private GCS artifact classes, secrets, backup/lifecycle settings, and separated runtime/migration service accounts. Record cost and retention configuration for review.
  - Files: `infra/terraform/data/`, `infra/terraform/environments/`, `release/infrastructure/`, `docs/retention-runbook.md`.
  - Depends on: 5.7, 3.1; approved service region, budget, and infrastructure tooling.
  - **Done when:** `terraform -chdir=infra/terraform/data validate` passes after initialization and a reviewed environment plan demonstrates exclusive service permissions, no public artifacts, and retention settings compatible with temporary-copy/backup bounds. Validation alone does not prove deployment.

- [ ] 6.2 Define runtime, queues, ingress, and redacted observability
  - Goal: Add Cloud Run/API/worker/import jobs, queue deadlines, authenticated task audiences, reconciliation scheduling, same-origin HTTPS/edge controls, instance/connection budgets, and operational metrics with no document/token logging.
  - Files: `infra/terraform/runtime/`, `services/api/Dockerfile`, `services/worker/Dockerfile`, `services/osm-import/Dockerfile`, `apps/web/Dockerfile`, `packages/adapters/telemetry/`, `tests/integration/test_runtime_configuration.py`, `docs/operations-runbook.md`.
  - Depends on: 6.1.
  - **Done when:** `uv run pytest tests/integration/test_runtime_configuration.py` passes and validated infrastructure plans link queue-age/retry/invariant/spend alerts, correct OIDC checks, restricted simulation-worker egress, and a separately scheduled regional import path.

- [ ] 6.3 Add staged delivery, release manifests, and rollback
  - Goal: Build versioned/signed images, pin dependency/model/engine/policy manifests, and use workload identity for deployment. Run migrations once with compatible expand/contract changes and rehearse rollback in an authorized staging environment.
  - Files: `.github/workflows/`, `scripts/verify_release.py`, `scripts/check_deployment.py`, `release/manifests/`, `docs/deployment-runbook.md`.
  - Depends on: 6.2; authorized staging infrastructure must be provisioned before rehearsal.
  - **Done when:** `uv run python scripts/check_deployment.py --environment staging` passes and recorded CI evidence includes frozen builds, contract/migration checks, a working staged journey, and rollback by known image digest without breaking stored run/schema compatibility.

- [ ] 6.4 Measure purge/backup bounds and rehearse restoration
  - Goal: Verify actual active-copy purge, object-generation/soft-delete behavior, backup expiry, and provider disclosures. Restore saved baseline/variants/run evidence with deletion tombstones applied before access reopens; measure agreed RPO/RTO.
  - Files: `scripts/verify_recovery.py`, `tests/integration/test_restore_tombstones.py`, `release/validation/recovery/`, `docs/retention-runbook.md`, `docs/recovery-runbook.md`.
  - Depends on: 6.3, 4.11; observed lifecycle evidence must be available, including the backup retention window.
  - **Done when:** `uv run python scripts/verify_recovery.py --environment staging` passes and dated measurements demonstrate active temporary content purged within 24 hours, backups expired within seven days, owner recovery within approved targets, and no resurrected deleted work or expired credentials. Simulated clocks alone cannot satisfy this release gate.

- [ ] 6.5 Benchmark supported scale, recovery rate, and spend controls
  - Goal: Measure the PRD benchmark and 50-scenario suite at declared hardware/concurrency; report engine/provider time separately, job completion/recovery, import memory, paid-work limits, and abuse behavior. Set supported limits from results.
  - Files: `scripts/benchmark_system.py`, `tests/fixtures/performance/`, `release/validation/performance/`, `release/limits.json`, `docs/operations-runbook.md`.
  - Depends on: 6.3, 4.9.
  - **Done when:** `uv run python scripts/benchmark_system.py --profile public-beta --verify` passes and recorded measurements meet approved PRD gates (provisionally p95 under 60 seconds for the 72-hour/25-barangay/30-shelter/50-vehicle/20,000-edge case, 50 scenarios within ten minutes, and at least 99% valid-job completion/recovery), with visible bounded costs. Any revised target needs an explicit product decision before acceptance.

- [ ] 6.6 Validate public usability, extraction, and findings usefulness
  - Goal: Conduct the PRD study with representative researchers/residents, independently review severity/water/assistance assumptions, and record extraction accuracy, time to findings, and usefulness with reproducible denominators.
  - Files: `release/validation/user-study/`, `release/validation/extraction/`, `release/validation/domain-review/`, `release/acceptance.json`, `scripts/verify_release.py`.
  - Depends on: 5.7, 6.3, 2.1; real participants and independent reviewers are required.
  - **Done when:** `uv run python scripts/verify_release.py --gate product-validation` passes and dated evidence meets PRD targets: at least 4/5 unaided temporary journeys, median active time at most 60 minutes, at least 90% extraction accuracy for present required facts, and at least 80% usefulness among the agreed top findings. Reviewer judgments cannot be manufactured by the script.

- [ ] 6.7 Verify deployed security and failure behavior
  - Goal: Exercise real ingress, IAM/RLS, temporary/account isolation, CSRF, malicious PDFs/source instructions, worker authentication, quotas, telemetry redaction, provider outages, and deletion races in authorized staging. Record and resolve critical findings.
  - Files: `tests/security/`, `scripts/verify_security.py`, `release/validation/security/`, `release/providers.json`; remediation files must be identified in the plan before edits.
  - Depends on: 6.3, 6.4, 6.5.
  - **Done when:** `uv run python scripts/verify_security.py --environment staging` passes and recorded tests show no cross-owner disclosure, no bypass through source checksum or task headers, no secret/document telemetry, and no unresolved critical security or retention finding.

- [ ] 6.8 Close milestone C and record the release decision
  - Goal: Consolidate every PRD §9 criterion, supported limits, budget, model/provider settings, processing terms, support/alert/upgrade ownership, and rollback/restore evidence. Prepare the exact beta artifact and record the authorized release decision separately from readiness.
  - Files: `scripts/verify_release.py`, `release/acceptance.json`, `release/manifests/`, `release/beta-decision.md`, `docs/operations-runbook.md`, `docs/architecture.md`, `docs/architecture-essentials.md`.
  - Depends on: 6.1–6.7, 3.9, 5.7.
  - **Done when:** `uv run python scripts/verify_release.py --milestone C` passes and every PRD acceptance item has current linked evidence, named owners, and a dated go/no-go record with no unresolved launch blocker. Readiness does not imply deployment; record the deployed version and smoke results only if release was authorized and actually performed.

## Deferred scope — milestone D, no implementation scheduled

Temporary-to-saved conversion, shared editing/sharing, automated search and source fetching, AI-authored scenarios/proposals or mid-run branches, in-scenario supply transport, refueling/shared crews, live forecasts, and emergency operations require separate product decisions and task plans. Do not add them as hidden dependencies of milestones A–C. Government approval, departmental administration, and automatic source-plan publication are outside this product's scope.
