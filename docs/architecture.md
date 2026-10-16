# Resilience Twin — Architecture

Status: Guest-only public-use target architecture (ADR-031); milestone A evidence retained; Phase 4 implementation requires revalidation\
Updated: 15 October 2026\
Product authority: [PRD.md](PRD.md)  
Developer quick reference: [architecture-essentials.md](architecture-essentials.md)

## 1. Authority and boundaries

This document is the source of truth for system boundaries, stack, persistence, simulation semantics, and integration contracts. The PRD governs product scope and acceptance. If implementation requires a conflict with the PRD, record the conflict and resolve it explicitly; do not silently change product behavior. Changes to these decisions must update the decision log here and the essentials document in the same pull request.

The architecture supports the four screens: Community Twin, Scenario, Live Simulation, and Resilience Findings. Researchers, residents, and other public users start a temporary analysis without sign-in to analyze publicly available plans. Government affiliation is neither required nor privileged. The municipality is an analysis subject, not a tenant owner. The product supports independent preparedness analysis, not live emergency command or official plan adoption.

**Governing boundary:** Gemini produces candidate extracted facts and optional explanations. Users author scenarios and hypothetical preparatory changes; deterministic policies replan. Reviewed, structured inputs enter a deterministic engine. Only that engine produces operational quantities. Source documents are immutable; proposals and report exports affect only the current user's workspace. There is no municipal approval or publication workflow. AI scenarios/proposals and mid-run branches remain deferred.

The folder tree below describes repository organization, including some historical scaffold locations. Phase 1–3 implementation and milestone A evidence remain valid. ADR-031 changes the target ownership/product design; existing account code is removed through revised Phase 4 tasks, not by this documentation update. Exact dependencies belong in lockfiles and release manifests. No unqualified `latest` dependency or model alias may define a pinned run.

## 2. Stack and reasons

| Layer | Selected technology | Reason and boundary |
| --- | --- | --- |
| Web application | React, TypeScript in strict mode, Vite, React Router | The product is an interactive guest-only application without an initial SEO or server-rendering requirement. A static SPA keeps business rules in one backend. |
| UI and state | Tailwind CSS, Radix primitives, TanStack Query; component-local state for playback and selections | Accessible primitives and reusable styling; server state stays distinct from ephemeral UI state. No second domain store in the browser. |
| Map and document viewer | MapLibre GL JS, PDF.js | Independent map overlays and direct inspection of cited PDF pages. Every important map state also has a table view. |
| API and application services | Python, FastAPI, Pydantic; Firestore server adapter | Typed API contracts, strong validation, and a shared language with geospatial and simulation code. One modular backend, deployed with separate API and worker entry points. |
| Simulation | Pure Python discrete-event kernel using `heapq`, the selected standard-library exact-edge router, explicit stable allocation policies | Reproducible event ordering; municipality-scale performance must be measured. ADR-028 selects one production router. No LLM, database, HTTP, or wall-clock dependency inside the kernel. |
| Geospatial ingestion | pyosmium, Shapely, pyproj; compile OSM into the selected exact-edge graph | Reuse PBF parsing, geometry validation, and metric conversion libraries. Task 3.6 must validate a single OSM routing compiler; these libraries alone do not supply its semantics. |
| Database | Cloud Firestore (ADR-029) | Bounded transactions for version sealing, jobs and reservations; server repositories enforce owner/reference integrity and immutability. Client Security Rules deny direct private-data access. No SQL RLS or PostGIS dependency. |
| Large artifacts | Private Cloud Storage for Firebase | PDFs, page artifacts, road snapshots, run checkpoints, event chunks, and reports stay outside Firestore documents. Checksums and object generations identify immutable bytes. [Server access](https://firebase.google.com/docs/storage/admin/start) |
| Browser ownership | Server-issued opaque temporary-session credential | No Firebase end-user Authentication or hidden guest accounts. Backend Firestore checks enforce one temporary owner, expiry and revocation; matching sources confer no access. |
| AI | Gemini through the Google Gen AI Python SDK; supplied-key Developer API path pending verification | Backend-only candidate extraction and optional explanations. Verify the key's actual API/project, exact model/SDK, billing-tier data handling and processing location before use; no inferred Vertex AI or regional access. [API key handling](https://ai.google.dev/gemini-api/docs/api-key) |
| Evidence research | Manual public-source/reference submission, user assertions, and explicit assumptions | Meets public-pilot acceptance without official contact. No server search or arbitrary URL fetching. A future Google Search adapter requires a suitable ingestion contract (§8.2). |
| Location and basemap | Geoapify geocoding and map tiles | Managed OSM-based location discovery and MapLibre-compatible tiles without operating a geocoder or relying on community public endpoints. Tiles are presentation only. [Geocoding](https://www.geoapify.com/geocoding-api/), [tiles](https://apidocs.geoapify.com/docs/maps) |
| Versioned road source | Geofabrik Philippines OSM PBF snapshots | Reproducible raw map data, not authoritative proof of road access or condition. Import once, then reuse reviewed municipal extracts. [Philippines extracts](https://download.geofabrik.de/asia/philippines.html) |
| Background work | Cloud Tasks, Firestore outbox and job ledger, Cloud Scheduler reconciliation | Durable dispatch, bounded retries, and per-queue concurrency without introducing Redis. Delivery is treated as at least once. External effects occur after transaction commit. |
| Runtime | Firebase Hosting for the Vite SPA; Docker on Cloud Run for API/workers; Cloud Run Jobs for regional imports | Hosting rewrites `/api` to Cloud Run. Long work uses durable jobs; static hosting does not execute Python. [Hosting integration](https://firebase.google.com/docs/hosting/cloud-run) |
| Edge and secrets | Firebase Hosting HTTPS, verified backend sessions, Secret Manager, service-account IAM | One browser origin and no private credentials in the client. Verify abuse controls for Hosting and direct API ingress; do not assume Cloud Armor covers Hosting. |
| Reports | Jinja2 HTML templates rendered to PDF with pinned Playwright Chromium | Reproducible independent findings, recommendations and hypothetical-revision diffs with provenance and tested/untested labels. No source-plan mutation. Rendering runs without arbitrary page scripts or remote URLs. |
| Delivery and observability | Terraform, GitHub Actions with workload identity federation, Artifact Registry, OpenTelemetry, Cloud Logging/Monitoring | Reviewable infrastructure and deployments, short-lived CI credentials, and correlated job traces. |
| Testing and tools | pytest, Hypothesis, Ruff, mypy; Vitest, Testing Library, Playwright, ESLint; uv and pnpm lockfiles | Test numerical invariants and permissions, then browser workflows; keep Python and TypeScript dependencies reproducible. |

Do not add a vector database, general agent framework, event broker, Kubernetes, or optimization solver in the first release. Structured municipal entities and bounded jobs do not yet justify those services. The initial allocator is a documented heuristic, not a claim of global optimality.

### 2.1 Reuse and dependency gate before the full build

ADR-028 selects the small standard-library exact-edge Dijkstra router as the **one production implementation** to integrate with the Task 3.6 OSM compiler. Task 2.4 compared it with [Valhalla](https://valhalla.github.io/valhalla/) 3.9.1 on a pinned Utrecht OSM bridge and node-via turn sample, plus the reviewed synthetic restriction/profile/tie fixture. Both routed the common bridge and turn cases, but Valhalla's documented request API did not provide exact directed-edge-ID closures: a geometry polygon closed both bridge directions when a one-direction closure was required. The reference accepts that closure directly and preserves the reverse edge. [Measured artifacts and explicit coverage/exclusions](../release/routing/ADR-028.md) record reproducibility, memory, latency and integration effort; the different compiled graph extents prohibit a speed ranking. `pyvalhalla` remains development-only for replay, not a second production router. The selected OSM compiler, Philippine source validation, vehicle-profile mapping, uncertainty handling, municipality-scale performance and model-validity checks remain gates; this decision alone authorizes no public deployment.

Keep `heapq` for the small explicit event kernel: domain accounting and serializable checkpoints are the custom work, not a general simulation framework. Retain Cloud Tasks and the minimal Firestore ledger for bounded stages. [Cloud Workflows](https://docs.cloud.google.com/workflows/docs/overview) is an alternative if measured orchestration complexity warrants replacing the dispatcher; do not build a general DAG engine or add two orchestrators. Managed orchestration would still require idempotent domain commits and authorization.

Before milestone A exits, record exact direct dependency/runtime versions, licenses, support status, and compatibility results in a dependency manifest and lockfiles. Verify Python/native geospatial wheels, Node/browser support, PDF.js and Chromium security patching, and Gemini SDK/model/endpoint compatibility. Before Firebase integration, approve exact browser/server SDK and CLI/emulator/runtime versions and verify Firestore indexes, transaction limits and Storage access. Select the PDF validation/scanning tool through a small fixture test; preserve the generator already verified in Task 1.1. Before deployment, verify each service's location, quota, cost, retention, and access configuration. Project existence is not evidence of workload fit. Assign an engineering owner for upgrade/security review before the pilot opens; pinned replay artifacts do not justify deploying vulnerable runtime images.

### 2.2 Firebase selection and migration boundary (13 October 2026)

The user selected Firebase Hosting, Authentication, Firestore and Storage on 13 October 2026 (ADR-029). On 15 October, ADR-031 superseded the end-user Authentication choice: the release is guest-only, with no saved accounts or conversations. Hosting, Firestore, private Storage, Cloud Run, Cloud Tasks and the backend Gemini integration remain. Project `ai-projects-250716` and the supplied identifiers are recorded in plan R.2; actual cloud checks and gaps are in Phase 4/progress. Inspect existing resources before changes and preserve unrelated applications, including their Auth and Storage configuration. Analytics remains disabled.

ADR-029 supersedes the SQL/PostGIS persistence and frontend deployment decisions. Existing SQL-named scaffold files are placeholders to retire or repurpose during Task 4.1, not a second persistence implementation. Firestore stores bounded metadata/records; Storage holds large immutable artifacts. Python geometry/projection/compiler adapters perform the required spatial operations; Task 4.1 must demonstrate query/index coverage and workload fit. Do not substitute database output for the pinned graph or change the pure engine.

All private reads/writes use the API and owner-scoped repositories. Firebase client Security Rules deny direct access; server SDKs bypass these rules, so backend authorization and least-privilege IAM are mandatory. Sealing, reference checks, revisions, job submission, outbox state and quota reservation use bounded Firestore transactions; callbacks must tolerate retries without provider, queue or object-storage side effects. Stage objects separately, publish their pointers after checks, and reconcile orphans. [Rules and server access](https://firebase.google.com/docs/firestore/security/rules-conditions), [transaction behavior](https://firebase.google.com/docs/firestore/manage-data/transactions).

The Gemini secret is backend-only in local environment/Secret Manager configuration. H.1 verifies its API and billing-tier processing terms before a bounded synthetic probe; 3.1 separately gates real documents. A supplied key does not establish Vertex AI service identity, regional processing, or permission to upload source PDFs. No secret, dependency installation, live configuration, spending or deployment is part of this documentation decision.

## 3. System shape and deployment

```text
Browser: four-screen React application
  | same-origin HTTPS, session cookie
Firebase Hosting
  |-- /               -> static Vite SPA
  |-- /api/v1/*       -> FastAPI: authorization + application services
                            |-- Firestore: records, versions, job ledger
                            |-- Cloud Storage for Firebase: private artifacts
                            '-- transactional outbox
                                      |
                            dispatcher + reconciler
                                      |
                                  Cloud Tasks
                                      |
                          authenticated worker containers
                            |-- extraction / AI / evidence
                            |-- graph compilation
                            |-- simulation / findings
                            '-- report generation

Cloud Scheduler -> regional import Cloud Run Job -> versioned OSM catalog
External adapters -> Gemini / Geoapify / Geofabrik
Simulation kernel <- immutable input bundle -> event chunks + metrics
```

API, workers, and import jobs share Python domain packages but have separate service accounts and entry points. Simulation workers have no AI credential or outbound internet requirement. Provider calls occur in integration workers; persisted results cross into the engine as data. Bound worker instances, Firestore operation rates and transaction contention together so autoscaling cannot bypass cost or usage caps.

Use separate development, staging, and production projects. Proposed primary region is `asia-southeast1`, subject to product/engineering review of user-facing processing terms and capability checks for every service. Do not infer that identity, search, or model processing is regional simply because the database is. Disable unapproved global model fallback.

Serve `/api` through Firebase Hosting rewrites to Cloud Run; enforce authorization on direct API URLs as well. Internal worker endpoints require service-account OIDC and the correct audience. Task headers alone are not authentication. Every private browser request resolves an active server-validated temporary session and checks current Firestore ownership. Only that session may inspect, edit, run, export or delete its analysis. User sign-in is removed; service-account authentication and IAM remain mandatory.

Hosting forwards only the `__session` cookie to dynamic backends. Use a host-only Secure/HttpOnly/SameSite opaque cookie whose digest resolves one temporary-session reference. No account reference or Firebase token exchange is accepted. CSRF tokens travel in request headers, not a second forwarded cookie. Return `Cache-Control: private, no-store` for private responses. Test issuance, renewal, revocation and concurrent tabs through actual Hosting; respect rewrite timeouts using `202` jobs. [Hosting cookie behavior](https://firebase.google.com/docs/hosting/manage-cache).

Workspaces and jobs belong to the current browser credential and expire. Refresh/reconnect works while that credential remains valid; lost credentials have no recovery path. Users download reports before ending the analysis or expiry. There is no persistent analysis/conversation history, account dashboard or cross-device access. Multiple tabs sharing the cookie access the same active analysis; new-session creation must not silently destroy it. Temporary versions, evidence and job records remain only for the bounded processing/replay lifecycle.

### 3.1 Temporary session contract

`POST /api/v1/temporary-sessions` atomically creates one temporary session and one temporary workspace after issuance/abuse checks. Generate a cryptographically random 256-bit bearer handle using the runtime security library; retain only its digest in Firestore and send it in the `__session` cookie described above. Never place it in URLs, local storage, exports, telemetry, or user-visible workspace IDs. Use origin/CSRF protections; reject cross-origin creation. Do not invent a custom identity provider or require a hidden account.

Authorize against server time with `expires_at = min(last_user_activity_at + 2 hours, created_at + 24 hours)`. Validate on every private request and worker publication. Deliberate foreground user activity may renew idle time through a CSRF-protected endpoint; status polling, retries, open sockets and worker heartbeats never renew it. Show server expiry and an advance warning. Each server session references exactly one temporary owner. Reject legacy account/mixed-owner records and credentials; never convert them implicitly. Temporary expiry/deletion is irreversible; stale renewal cannot revive it. Firestore TTL cleanup is not the authorization clock or proof of the purge deadline.

End-session revokes the temporary reference, tombstones its workspace, and requests cooperative job cancellation in one transaction. Revoke the bearer handle and clear its cookie; do not preserve account references. A scheduled sweep performs the same transition at expiry, but authorization rejects expiry even if the sweep is late. Do not rely on unload events or cookie disappearance to delete server data. Before enqueueing, ensure the stage/job execution budget fits remaining session lifetime; active work does not extend expiry. Block further uploads/exports after termination, and garbage-collect late artifacts. Temporary uploads use short-lived bounded upload authorization capped at expiry; finalization always rechecks the session.

Temporary artifact reads/downloads use an owner-checked proxy rather than reusable signed URLs, with expiry checks during long streams so session revocation stops further delivery. Already downloaded bytes cannot be revoked. Reconnect is available only while the credential and session remain valid; no account history entry, email recovery or cross-device link is created.

Reserve paid work against session, workspace, network issuance/rate limits and global budget/concurrency caps. Rotating cookies is not a spending-limit reset: enforce edge limits and graduated abuse challenges, considering shared-network users. Set conservative guest document/run limits from measured costs, expose them before work starts, and permit completed-result download until expiry even when compute quota is exhausted. Do not use invasive device fingerprinting as the access-control mechanism.

Progress uses cursor-based HTTP polling every two seconds while a job is active, backing off when hidden or idle. Timeline playback uses committed event chunks and checkpoints. Play/pause/speed changes are local playback controls, not worker execution controls; cancellation is a separate durable API command. This avoids a persistent WebSocket dependency and allows reconnecting after a tab closes.

## 4. Folder structure and dependency rules

```text
/
├── docs/
│   ├── PRD.md
│   ├── architecture.md
│   ├── architecture-essentials.md
│   ├── plan.md / progress.md
│   └── scaffold-tree.md            # Complete on-disk file listing
├── apps/
│   └── web/
│       ├── src/
│       │   ├── app/                 # Routes, session shell, providers
│       │   ├── features/
│       │   │   ├── community-twin/  # Upload, map, evidence, review
│       │   │   ├── scenario/        # Structured scenario editor
│       │   │   ├── simulation/      # Timeline, events, map playback
│       │   │   └── findings/        # Ranking, proposal diff, comparison
│       │   ├── components/          # Shared accessible UI
│       │   └── lib/                 # API client setup, formatting
│       └── tests/
├── services/
│   ├── api/                        # FastAPI routers, session and HTTP concerns
│   ├── worker/                     # Task handlers, leases, dispatch, reconciliation
│   └── osm-import/                 # Regional PBF import job entry point
├── packages/
│   ├── contracts/                  # Canonical Pydantic API + artifact schemas
│   ├── domain/                     # Readiness, evidence review, variants, comparisons
│   ├── application/                # Use cases and adapter interfaces
│   ├── simulation/                 # Pure kernel, routing, allocation, metrics
│   │   ├── kernel/
│   │   ├── routing/
│   │   ├── policies/
│   │   └── metrics/
│   ├── adapters/
│   │   ├── persistence/            # Firestore repositories and owner checks
│   │   ├── storage/                # Cloud Storage for Firebase adapters
│   │   ├── ai/                     # Gemini client, versioned prompts
│   │   ├── search/                 # README only; implementation remains gated
│   │   ├── sources/                # Manual evidence intake; future fetcher gated
│   │   ├── local/                  # Synthetic walking-skeleton adapters
│   │   ├── documents/              # Quarantined PDF validation
│   │   ├── identity/               # Historical account adapter; retire in 4.3
│   │   ├── telemetry/              # Redacted operational telemetry
│   │   ├── geo/                    # Geoapify, OSM import and graph compiler
│   │   └── tasks/                  # Cloud Tasks implementation
│   ├── reports/                    # Escaped templates and PDF renderer
│   └── client-generated/           # Generated TypeScript types and API client
├── db/
│   ├── migrations/                 # Versioned Firestore schema upgrades; retire SQL placeholders
│   └── seeds/                      # Synthetic local data only
├── tests/
│   ├── engine/                     # Golden cases, conservation, replay
│   ├── integration/                # Firestore emulator/cloud, jobs, authorization
│   ├── contracts/                  # Schema and provider fixtures
│   ├── e2e/                        # Public onboarding and private owner isolation
│   ├── security/                   # Deployed security and failure verification
│   └── fixtures/                   # Synthetic/redacted documents and graphs
├── infra/terraform/                # Environments, IAM, queues, storage, database
├── scripts/                        # Generate contracts, verify, local setup
├── release/                        # Versioned runtime/model/policy manifests
├── .github/workflows/
├── AGENTS.md
├── package.json / playwright.config.ts
├── compose.yaml                    # Local service containers; emulator setup is gated
├── pyproject.toml / uv.lock         # Python workspace
└── pnpm-workspace.yaml / pnpm-lock.yaml
```

Dependencies point inward: entry points → application → domain/contracts; adapters implement application ports. `simulation` depends only on contracts and pinned numerical/graph libraries, never on adapters or the web framework. The browser uses generated contracts and never imports database models. Firestore adapter records describe persistence; Pydantic contracts describe the public and artifact interfaces. Generate OpenAPI/TypeScript from the Python contracts and fail CI on drift. Never hand-maintain equivalent business validators in two languages.

The user requested the complete empty structure on 12 October 2026, overriding incremental folder creation for this preparation only. The complete file inventory is [scaffold-tree.md](scaffold-tree.md); the diagram above groups related paths. Headers and empty exports implement no data model, service, workflow, dependency, or fixture. JSON stores header metadata in `_comment`; generated-client and deferred-search directories have only comment-only README placeholders. Builds, runners, manifests, lockfiles, Dockerfiles, and workflows still require their assigned implementation tasks. Milestone A needs only contracts, a reference engine/route path, extraction/evidence fixtures, and a small review surface. Implement application modules and deployment boundaries only when their milestone gates permit them.

## 5. Data model

### 5.1 Common rules

- Use UUIDs for application identity; preserve original OSM identifiers separately. A stable `entity_id` survives revisions within a workspace.
- Every workspace-owned document carries `workspace_id` and lives under a scoped collection path. Server repositories validate that child references belong to the same workspace/version; Firestore provides no SQL foreign-key enforcement.
- Require verified temporary-session context for every repository operation, validate the workspace's exclusive ownership and temporary expiry, and fail closed for missing context. Use Firestore transactions/preconditions for writes and seals. Deny direct client data access in Security Rules; server SDKs bypass rules, so API/worker checks and IAM must be tested separately. Workers derive context from authorized durable jobs and recheck deletion/expiry at publication.
- Shared immutable OSM source catalogs are explicitly non-tenant data. Workspace overrides, facilities, uploaded public-plan copies, and user annotations never enter that shared catalog. Matching public source URLs or checksums must not merge workspace ownership, evidence choices, or deletion lifecycles.
- Drafts are mutable with a revision counter and `If-Match` checks. Sealing produces an immutable baseline/variant version; modifications create a new child version. User review records bind exact hashes and mean acknowledgment of evidence/assumptions, never official approval. Original PDF bytes are never rewritten by a proposal.
- Store UTC timestamps as Firestore timestamps; render scenario time in `Asia/Manila`. Simulation time is integer seconds since scenario start. Store people and seats as integers, water as integer milliliters, and costs as integer centavos when supplied. Missing cost is unknown, not zero.
- Persist geographic geometry in EPSG:4326, longitude then latitude. Compute distance in a recorded local metric projection/geodesic method, then freeze integer millimeters and travel seconds into the graph artifact.

### 5.2 Collections and aggregates

All records below are workspace-scoped unless explicitly identified as identity or public catalog data. These are logical aggregates; Task 4.1 defines bounded documents, subcollections and indexes. Large payloads remain immutable Storage artifacts.

| Aggregate / collections | Essential fields and relationships |
| --- | --- |
| `browser_session` | Opaque-handle digest, expiry/revocation state and one temporary-session reference; no account reference or raw bearer handle |
| `temporary_session` | Token digest, created/last deliberate activity/idle/absolute expiry timestamps, active/revoked/expired status, quota state; no user account required; no raw token stored |
| `workspace` | Mode `temporary`; required `owner_temporary_session_id`, one workspace per session through deterministic identity and atomic creation; reject account/mixed ownership; title/location metadata, active/deleting/deleted state, bounded retention; no membership/role collections |
| `artifact` | Object key, generation, SHA-256, media type, size, retention class, provenance, deletion status; downloads require workspace authorization |
| `document`, `document_version`, `document_page` | Immutable original PDF artifact, public source URL/publication reference and known dates, upload consent, page count, indexed page artifacts and optional printed page labels; physical-page/region coverage status and extraction method; supplementary documents retain separate identities in the same analysis |
| `source_evidence` | Source type, document page or permitted public-source URL, title, retrieved/published/applicable dates, excerpt/region locator, allowed artifact, verification status |
| `fact_candidate`, `fact_review` | Entity and field path, source quantity/unit/range, statement type, applicable date/geography, source fragment, normalized value and explicit conversion/allocation assumption, extraction run, uncertainty, reviewer decision, conflict group; never overwrite competing candidates |
| `twin`, `twin_version` | Draft/sealed state, parent version, declared study boundary and barangay/pickup membership, included population/resources and exclusions, input documents, graph extent/buffer and cross-boundary assumptions, readiness-policy version, content hash |
| `entity`, `entity_revision` | Stable entity ID and kind; revision belongs to a twin version; discriminated typed attributes, geometry artifact/reference with explicit CRS, active status |
| `field_provenance` | Entity revision plus field path → chosen fact candidate, user assertion, or explicit assumption; essential fields require a record |
| `analysis_review` | Exact twin/scenario version hash, workspace owner, acknowledged material assumptions/evidence gaps, review-policy version, time; optional resource statements are source evidence, not required official confirmations |
| `osm_catalog_snapshot` | Public catalog: Geofabrik URL, source date, downloaded checksum, importer version, immutable PBF artifact |
| `graph_snapshot`, `graph_binding` | Tenant graph artifact/hash, source catalog, extent and buffer, compiler policy, edge/node counts; entity-to-access-node binding and its review status |
| `scenario_version`, `scenario_event` | Sealed structured parameters, horizon, input schema, reviewed hazard references, events with target IDs, activation time, operational effect, knowledge time, source/assumption |
| `scenario_suite`, `suite_member` | Immutable ordered members and stable IDs, seeds, generator version; each member identifies exact exogenous conditions |
| `run`, `run_manifest` | Twin/scenario/suite member, baseline/variant lineage, manifest artifact, status, input hash, engine digest, policy, deterministic response mode; AI response artifacts deferred |
| `run_checkpoint`, `run_event_chunk`, `run_metric` | Run sequence and simulation-time range, checksummed artifacts, committed high-water mark; typed metric key, unit, value, affected entity/cohort and evidence event IDs |
| `finding`, `finding_occurrence` | Stable weakness key, severity-policy version, run evidence, distinct affected cohorts, recurrence numerator/denominator, quantified uncertainty and causal-evidence label |
| `proposal`, `proposal_version`, `comparison` | Baseline hash, typed operations, resource requirements, applicability, target twin version, paired run IDs, metric deltas and regressions |
| `job`, `job_attempt`, `outbox`, `usage_reservation` | Idempotency key, dependencies, lease/fencing token, checkpoint, attempt/error state, cancellation flag, quota reservation and actual usage |
| `ai_invocation`, `audit_event` | Permitted input/output artifact hashes, model and prompt/schema versions, provider request ID, costs; actor/action/subject audit without private prompt bodies |

Core relationship: `temporary_session → workspace → twin → twin_version → entity_revision → field_provenance → source_evidence`. Reviews, jobs and within-session change records attribute actions to the temporary owner; there are no user-account rows. A comparison pairs runs in the same workspace. Saving/exporting never changes its source document or another workspace. Temporary versioning supports replay only until expiry/deletion, not permanent history. There is no official baseline pointer or approval-decision aggregate.

Typed `entity_revision.attributes` uses schema-validated Firestore maps for bounded entity-specific fields, with IDs, version ownership and geometry artifact references explicit. Compiler validation resolves all cross-entity IDs within the same sealed version. Do not use arbitrary LLM JSON as the operational model.

### 5.3 Entity types

| Type | Required operational fields when used |
| --- | --- |
| Barangay | Name, boundary/reference, aggregate population, source date |
| Population cohort | Barangay, count, initial state/location, pickup point when evacuation is requested, mobility/assistance traits, evacuation mode and readiness constraints |
| Pickup point | Confirmed location, graph access binding, any staging limit |
| Shelter | Location/access binding, safe capacity, availability, permitted cohort needs, initial occupant cohort IDs, water inventory |
| Vehicle | Seats, initial location, availability schedule, dedicated crew reference/windows, finite remaining operating-distance budget in millimeters, compatible routes/modes, loading/unloading parameters |
| Bridge / road asset | OSM member edge IDs, reviewed asset grouping, access limitations; condition remains unknown unless separately sourced |
| Supply store | Location, initial water quantity, consumption allocation; pilot transfers occur only before scenario start, in-scenario resupply deferred |
| Critical facility | Location, function, explicit modeled dependency/effect, or `informational_only` |
| Procedure | Source steps plus reviewed operational rules; unmodeled steps remain informational |

Cohorts are mutually exclusive population partitions with possibly multiple vulnerability traits. Do not sum overlapping trait totals to obtain a population. If only overlapping aggregate counts exist, flag partition uncertainty and require a declared modeling assumption. Additional displacement draws from the unrequested population; external arrivals require their own cohort and source assumption.

Each initial occupant belongs to exactly one cohort in the initial `sheltered` state at one shelter. Shelter occupancy is derived from those cohorts, never an additional independent population count. Validate that initial occupancy fits capacity, and reserve initial consumption from scenario time zero. A later capacity reduction can produce forced overload. Crew references are resource labels, not personal records; the pilot requires dedicated crews and rejects a crew assigned to overlapping vehicle windows. Unknown crew or fuel budgets need explicit plausible assumptions to run; no official confirmation is required, and those results remain assumption-dependent.

Documentary candidates are not operational entities. Preserve reported-existing, proposed/target, historical and scenario-assumption statements with their original units, ranges, applicable dates and geography. Promotion requires a reviewed usable value for the scenario date/extent, or a separately labeled explicit assumption. Family capacities require a retained family-to-person conversion/allocation rule and integer result; range selection requires an explicit assumption. A blank is unknown unless reviewed evidence establishes absence. Resolve shared facilities to one resource identity before allocation and keep population/exposure overlaps out of additive demand. Preserve competing source numbers, including Guiguinto's 3,987 subtotal and 4,087 printed total, with the review decision instead of silently repairing source arithmetic. QC's proposed district shelters, procurement budgets and household water connections cannot populate operational inventories by extraction alone.

### 5.4 Immutable run bundle

The worker compiles a content-addressed bundle containing `schema_version`, twin and scenario hashes, graph hash, source references, integer-valued operational data, scenario-suite member, seed and RNG algorithm, engine/container digest, policy/allocator version, iteration budgets, and `response_mode=deterministic`. A saved AI response stream is a later schema extension, not a pilot requirement. Canonical serialization sorts keys and sets and rejects NaN/infinity. Do not serialize executable Python objects or accept pickle artifacts.

The twin hash binds the study extent, membership/exclusions, source applicability and accepted conversion/allocation assumptions as well as operational quantities. Changing any material scope or evidence decision creates a new version. Paired comparisons require the same exogenous scenario and declared study scope; city-wide source totals cannot silently replace study-area cohorts.

Separate the deterministic result hash from operational metadata such as job duration, attempt number, or provider latency. Report replays from saved events and engine re-execution from pinned inputs are distinct actions. Regenerating an optional explanation creates a new explanation artifact without changing engine results. Newly accepted extraction facts require a new twin version and run; they are never silently incorporated into replay.

## 6. Key flows and algorithms

### 6.1 Upload, extraction, and evidence review

1. `POST /workspaces/{id}/documents` checks unexpired temporary ownership, applicable quota, remaining session lifetime, public-source metadata and processing consent; returns a bounded, expiring upload authorization into quarantine storage. Source metadata does not trigger server fetching or a government-verification workflow.
2. Upload finalization verifies actual bytes, size, file signature, checksum, and page readability. A sandboxed validation worker scans the file; reject unsupported encryption or malformed content with a repairable error. Untrusted PDFs never execute scripts in the app origin.
3. Create extraction jobs by page groups with stable original-page mappings and bounded overlaps for split tables. Gemini emits typed fact candidates with physical page indexes and region/excerpt references. Persist permitted raw outputs separately from accepted data.
4. Validate types, ranges, units, page bounds and evidence references. Cross-page merges use stable source identifiers and candidate matching, not blind name equality. Fuzzy entity matches become review suggestions.
5. Show candidates and discrepancies in Community Twin. A citation points to visible evidence, not simply a model assertion of confidence. A source's absence is `unknown`, not a fabricated zero.
6. A review command selects or corrects a fact, writes provenance and change-history entries, and recomputes readiness in one transaction. User review records bind exact version hashes; changing material values invalidates the relevant acknowledgment. Assertions and assumptions remain labeled even after review.

Maintain coverage for every physical page and relevant content region with processed/unresolved/failed status, method, source locator and recovery reason. Processed means inspected, not accepted as fact. Nonempty extracted text cannot close image-table coverage. Route visual tables and graphic presence/absence marks through an approved visual/OCR method or explicit manual recovery; retain cross-page table/header links without duplicate rows. Acceptance cases include Guiguinto page 84's image content and pages 120–121's split table. An unresolved critical region remains visible and blocks dependent operational promotion unless independently supplied evidence or a labeled usable assumption resolves the input; a readable PDF remains available for gap review.

Use the exact two source identities in [the PDF input review](pdf-input-fit-review.md#inspection-and-source-identity) as separate compatibility cases. Intake/extraction limits for the guest-only flow must admit each full file, at least 191 pages and 9,418,109 bytes per file. Bound work by page groups, remaining lifetime and declared aggregate quotas; retain every page's mapping. Publish limits and measure complete-file processing separately from simulation performance. Reject unsupported limits with actionable errors, never silent truncation. Provider/source gates still apply; local inspection is not authorization to upload these files to Gemini or redistribute fixtures.

The readiness evaluator returns `document_review_available`, `computable`, and `ready_to_run` with reasons. Evidence inspection and gap-report export remain available when simulation is blocked. `computable` requires valid essential values or explicit usable assumptions; `ready_to_run` additionally requires the owner's acknowledgment of material assumptions and a valid reviewed scenario. Neither means certified or officially approved. Default speeds and policies have versioned units, applicability, and uncertainty records.

Each readiness reason identifies the missing/contested field, engine requirement, acceptable evidence/assumption remedy and dependent conclusions. Supplementary sources have their own immutable identities and physical-page citations in the same analysis; referenced but absent QC annexes stay missing until actually supplied. Recheck temporal applicability (including historical Guiguinto scenarios), units, conflicts, geographic allocation and scope after corrections. Unsupported walking, staged transfers and resupply stay informational. Record source-only readiness/gap export separately from the supplemented baseline, disruption, paired-change and findings export for each document.

Record how each modeled operating rule maps to a cited plan passage, a user interpretation, or an explicit default policy. Unsupported procedures stay visible as not modeled. A missing document field generates a documentation-gap finding, not a claim that the municipality lacks the resource. A gap-only report contains no fabricated simulation metrics. Each run reports its modeled scope and assumptions so the user can distinguish a test of documented procedures from a hypothetical allocation policy.

### 6.2 Location and road compilation

QC proof simulations cover an explicitly selected study area, per the 13 October 2026 scope decision. Before sealing, record its named barangays/pickups, polygon/boundary, population/resources, graph extent/buffer, exclusions and cross-boundary assumptions. Full-document review still includes all 112 QC pages. Guiguinto also records its modeled extent and exclusions. Review membership and external resource allocation explicitly; administrative location confirmation alone cannot define demand or resource availability. Carry scope labels into maps, tables and reports. The 25-barangay benchmark does not establish whole-QC simulation for 142 barangays.

1. Geoapify suggests locations; the user confirms the municipality. Match the administrative boundary against the pinned OSM catalog, or require a reviewed polygon if absent or ambiguous.
2. Extract the polygon plus a configured, recorded routing buffer from the regional PBF. Preserve complete road geometries and relevant turn-restriction relations. Report cut edges at the extent boundary.
3. Build a directed multigraph, retaining OSM node connectivity, one-way rules, access tags, parallel ways, bridge/tunnel layers, and vehicle restrictions. Geometric crossings without a shared node are not intersections.
4. Use turn-aware routing state `(node_id, incoming_edge_id)` for supported node-via restrictions. Way-via restrictions need additional path history and are not represented by that state alone. The reuse gate must document supported restrictions; unsupported, conditional, or ambiguous restrictions block affected routes until reviewed conservative exclusions or an explicitly validated interpretation are applied. Never silently declare them traversable.
5. Assign positive integer travel times from reviewed speed profiles and frozen lengths. Missing speeds use visible, versioned assumptions. Unsupported ferries, walking, or private transport cannot become hidden alternate routes.
6. Match facilities and pickup points to accessible nodes within a configured distance, checking barriers and road access. Proposed connectors carry distance and provenance and require confirmation. No point teleports to a distant road.
7. Group bridge member edges into reviewed asset IDs so a closure affects every relevant direction/segment. The same OSM way ID alone is not guaranteed to describe one physical bridge.
8. Freeze the graph artifact. External shelters and routes through neighboring municipalities require explicit inclusion and evidence or declared assumptions. Modeling their availability never implies operational permission to use them.

The standard-library reference router uses Dijkstra over admissible edges/turns with integer travel weights and deterministic ordering by stable edge ID. It retains bounded edge-history state for reviewed way-via restrictions; `(node_id, incoming_edge_id)` alone is insufficient for them. The production implementation is selected at §2.1's reuse gate and must preserve equivalent reviewed semantics. Preserve the exact edge path, not just node IDs. Route cache keys include graph hash, observed disruption-state hash, vehicle/routing profile hash, origin and destination. Changes invalidate the relevant cache. Travel-time sensitivity applies a pinned rational multiplier to base edge times, rounded upward to positive integer seconds; that multiplier belongs to the routing profile and run manifest.

### 6.3 Scenario preparation and knowledge boundaries

The user authors the structured scenario and a deterministic summary exposes its inputs. Schema/domain validators reject nonexistent targets, invalid intervals, negative resources, impossible displacement, and undeclared hazard-to-closure inference. The owner reviews and seals parameters before a run. AI-generated scenarios are deferred and must satisfy the same checks if later enabled.

An exogenous event has an effective time and a time when the simulated response policy learns about it. The engine knows the schedule to execute it; the allocation policy sees only observations and explicitly configured forecast assumptions available at the current simulation time. This prevents accidental perfect knowledge of future disruptions; the public user is not being modeled as a municipal decision-maker.

Sampled suites derive stable independent random streams from the suite seed, member ID, event type, and entity ID using a pinned algorithm, never Python's process-randomized `hash()`. Freeze all sampled events before comparisons. Adding an entity does not shift unrelated random draws. Changed target IDs require a reviewed mapping or make the pair non-comparable.

### 6.4 Discrete-event simulation

Use an event queue ordered by `(time_seconds, phase, stable_sequence)`. At each simulation time:

1. Integrate water demand for the preceding interval and record any exact exhaustion crossing.
2. Apply effective disruptions and resource changes.
3. Resolve movement/loading/unloading completions against the updated state.
4. Activate new evacuation demand and received observations.
5. Evaluate deadlines; unloading completed exactly at the deadline counts as on time.
6. Replan and commit new feasible actions, then check invariants and emit state changes.

All event handlers must schedule future work at a positive time increment or a later bounded phase, preventing zero-time loops. Late evacuation continues after a missed deadline and is reported separately.

Always schedule a terminal event at horizon `H`, even for an otherwise empty queue. At `H`, integrate the preceding interval and process disruptions, existing action completions, demand/observations, and deadlines in the normal order; do not dispatch new positive-duration actions. Save a final checkpoint and metrics. Unfinished trips retain location/progress, passengers, reservations, and consumed budgets; they are not rounded up to arrivals. Demand not yet served is reported, while an unserved cohort whose deadline is after `H` is pending rather than a deadline miss. Saved later events remain unevaluated. A completion exactly at `H` counts only after the ordinary disruption/completion rules are applied.

People occupy exactly one state: not requested, waiting, loading, in transit, unloading, or sheltered. Assistance traits remain attached to the cohort. Late/unserved status is a metric over these states, not another population bucket. Conservation is checked after each event. Vehicles have one location or edge-progress record and one active trip; passengers are not duplicated during rerouting.

Reserve shelter seats for committed inbound trips and release reservations on reroute or cancellation. Admit only within current capacity. Rejected arrivals stay accounted for and are replanned; they do not disappear. If a shelter's capacity falls below existing occupancy, record forced overload and a new relocation demand. Never erase occupants or claim the historical state complied with the new limit.

Default road closures prevent new edge entry. A vehicle already on an edge completes that edge under the explicit atomic-edge assumption, then replans; this does not model bridge collapse during traversal. Scenarios can instead mark an on-edge vehicle stranded using an explicit vehicle-outage event. Passengers remain stranded until a modeled recovery/availability event; the engine cannot invent a rescue or teleport them to a node.

Water consumption integrates integer milliliter demand with a retained fractional remainder from the per-day rate. If inventory runs out within an interval, record the crossing time and accumulate unmet demand; inventories never become negative. Demand follows each cohort's configured supply source/location, including initial occupants and waiting or transit provisions. Pre-scenario redistribution conserves stock across stores and shelters, changes initial inventories, and is labeled a proposed preparatory action. Additional stock is a separately declared resource addition. Reject in-scenario transport/resupply commands in the pilot; later support must model transport, timing, and competing vehicle use.

Trip feasibility covers pickup travel, loading, passenger travel, unloading, and any required return/reposition leg within one reviewed crew/vehicle availability window and remaining operating-distance budget. Reserve the planned distance when dispatching, deduct actual edge travel as it occurs, and release unused reservations on cancellation/reroute. Revalidate after every disruption; do not commit an edge that exceeds the remaining budget. If rerouting makes safe completion impossible, retain occupants at the last reachable state and report stranded/unserved demand. No automatic refuel, crew extension, or teleportation is allowed. Repositioning and empty travel consume the same budget. The distance budget is an explicitly approximate fuel model, not a prediction of fuel consumption.

### 6.5 Allocation, replanning, and deterministic limits

The release policy `deadline_greedy_v1` is a reproducible rolling-horizon heuristic:

1. Enumerate ready cohorts, available compatible vehicles, and feasible shelters using currently known conditions.
2. Calculate pickup, loading, travel, unloading, and vehicle-release times. A feasibility check enforces route access, seats, assistance needs, shelter reservations, crew/vehicle windows, and operating-distance budgets. Estimate each candidate shelter's water deficit through the horizon using currently known inventory, existing occupants, committed inbound trips, and configured consumption. Future unknown disruptions are not available to this estimate.
3. Prioritize tightest deadline slack; break ties by reviewed assistance priority, earlier deadline, then stable cohort ID. Rank vehicle/shelter candidates by on-time seats delivered, projected water deficit, completion time, travel time, and stable IDs. Safety-first ordering can choose a water-deficient shelter to avoid deadline misses; record the tradeoff explicitly. Arrival and sustained water sufficiency are separate metrics, never a combined success flag.
4. Commit trips and reservations, splitting cohorts by integer seats as needed. Never assume fractional people or multiple simultaneous uses of a vehicle.
5. Improve assignments with a fixed number of deterministic candidate moves and short simulated evaluations. Compare outcomes lexicographically: total deadline misses, vulnerable-group deadline misses, rejected shelter demand/forced overload, water deficit, then known resource cost and travel effort. Unknown costs remain visible and are not treated as free.
6. Report the iteration budget, uncovered demand, limitations, and tradeoffs. This is feasible heuristic planning, not proof of the best possible response.

The priority policy is reviewable and versioned; the default does not silently let large groups erase vulnerable-group outcomes. Always show disaggregated results. Domain validation can change this policy before pilot launch, with benchmark comparisons.

Milestone A also implements `earliest_deadline_reference_v1`: prioritize absolute deadline, then assistance priority and stable cohort ID, using the same feasibility checks and candidate ranking but without local improvement moves. Its purpose is to reveal dependence on allocation choices, not to provide an optimum. Keep production baseline/proposal pairs on the same policy; reference-policy and uncertainty sweeps are separate labeled experiments.

Pilot proposals are user-authored typed preparatory changes: shelter preferences, vehicle starting positions, initial inventory redistribution, and explicitly declared resource additions. Validate permissions, conservation, changed assumptions, and readiness before a fresh paired run. Checkpoints support durable execution and playback; they are not an AI branching subsystem.

AI replanning is deferred. Before enabling it, require saved observations and exact proposal artifacts, schema/feasibility checks, branch lineage, deterministic timeout behavior, paired evaluation, and evidence of improvement over the reference policies. AI calls must remain outside the kernel. No such provider dependency or response stream is required by the pilot engine; the manifest records `response_mode=deterministic`.

### 6.6 Finding generation and comparison

Engine rules derive findings from typed violations and metrics. Group occurrences by weakness type and stable asset/cohort IDs; count each suite member once per weakness. Track unique affected cohorts and maximum/interval-specific counts so repeated rejected dispatches do not inflate affected population.

Recurrence is `members with weakness / completed evaluable members`; show the planned suite size, failed/cancelled members, and exclusions. A partial suite cannot be presented as a complete paired comparison. Permit partial report export with its status and exclusions visible; untested proposals cannot claim measured improvement. Do not convert recurrence into real-world probability.

Structural articulation/cut analysis identifies candidate chokepoints. A “single point of failure affecting N residents” claim additionally requires directed, turn-aware reachability and paired disruption evidence; a bridge label or centrality score alone is insufficient. Observed associations remain labeled as such unless controlled comparisons support attribution.

Severity comes from a versioned engineering policy with explicit assumed thresholds; results retain provisional priority labels and raw metrics. External severity certification is not required (ADR-030). Gemini explains structured finding IDs and evidence references. Numeric text is rendered from metric references; unsupported quantities or references are rejected, with a deterministic explanation template as fallback. Findings identify document gaps, simulated failures, policy dependence, and proposed alternatives separately.

An improvement comparison pins the same suite events, graph, engine, policies and random draws and changes only the declared proposal operations. Response policies are identical; responses may differ because state differs, and each is saved. Model upgrades or graph refreshes create a separate comparison class, not a claimed plan improvement. Record per-member deltas, vulnerable-group effects, worst cases, newly introduced failures, and required resources.

The pilot's bounded sensitivity suite varies travel times, loading times, demand timing, and consumption rates over explicit engineering low/nominal/high defaults or explicit user-supplied ranges, one factor at a time plus one declared adverse combination. Save the exact expanded configurations and range provenance; do not invent probabilistic confidence intervals. For each configuration/policy, compare baseline and proposal under identical conditions. Report outcome ranges, ranking reversals, and failures that disappear under the reference policy. Those failures are policy-dependent, not established unavoidable asset shortages. New graph/model versions require a separate validation and comparison class.

### 6.7 Personal versions, recommendations, and reports

A seal/save command checks current owner identity and draft revision, validates the selected operation's prerequisites, then atomically writes a new immutable version and change-history entry. Simulation readiness is checked only for operations that require simulation; a user may save incomplete drafts and export gap-only reports. Stale edits return a conflict. Acknowledging assumptions or choosing a preferred variant is not an approval decision.

Baseline and proposal versions reference the immutable source PDF and remain in the same owner workspace. Applying a proposed change creates a hypothetical child model and a concrete diff; it never writes back to the document, a municipal system, or another user's model. No municipal verification, official roles, submit-for-approval action, or automatic external delivery exists.

Report generation pins the selected baseline/variant and any evaluated comparison. Include the public document's source/date, independent-analysis label, modeled versus unmodeled scope, cited evidence, user assumptions, model/policy versions, completed/partial/not-run status, recommendations and proposed-revision diff, regressions, required resources, and attribution. A recommendation without a completed comparison is labeled untested. A download is a user-owned assessment, not an amended or endorsed municipal plan.

## 7. Durable jobs and application API

### 7.1 Job execution

All expensive endpoints return `202 Accepted` with a durable job ID. A transaction writes the domain command, quota reservation, job and outbox row. A dispatcher submits a task named from the job and stage; reconciliation retries unsent outbox rows. A successful enqueue followed by a database failure must be safe to repeat.

Worker processing is at least once. Claim with a lease and monotonically increasing fencing token; only the current token can commit results. Stage artifacts go to attempt-specific temporary keys; a short database transaction publishes their immutable references and advances the checkpoint. A stale worker's unreferenced objects are garbage-collected. Completed duplicates return success; an actively leased duplicate returns a retryable response unless durable completion has already occurred.

Use separate queues for extraction, graph compilation, simulation, and reports. Target task stages below five minutes, enforce a ten-minute application budget and a twenty-minute queue deadline, and checkpoint before the application budget. HTTP tasks have a documented thirty-minute maximum; long regional imports use Cloud Run Jobs. [Cloud Tasks limits](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)

Do not acknowledge a task while its only remaining work is an untracked background coroutine. Acknowledge after stage completion or a committed continuation/outbox record. One scenario member is a schedulable simulation unit; suite aggregation waits on durable child states. Cloud Scheduler reconciles expired leases, import executions, orphan artifacts, and exhausted retries. It does not restart completed logical jobs.

Cancellation is cooperative at event/checkpoint boundaries; partial data stays labeled partial. Invalid input is terminal with an actionable reason. Transient provider failures retry with bounded exponential backoff and jitter. Exhausted jobs enter a visible failed state with a retry command. Retrying extraction can incur another provider charge: deduplicate logical outputs, record attempts, and reconcile usage rather than claiming exactly-once billing.

### 7.2 API conventions and key commands

Base path for workspace operations: `/api/v1/workspaces/{workspace_id}`. There is no cross-session workspace listing or account workspace-creation endpoint. `POST /api/v1/temporary-sessions` creates temporary access; `GET`, `POST /activity`, and `DELETE` on `/api/v1/temporary-sessions/current` inspect, deliberately renew, and end it. All commands enforce current server-side ownership/expiry. Mutations accept an `Idempotency-Key` scoped to actor type/ID, workspace, route and payload hash; reuse with a different body returns `409`. Session issuance is rate-limited and retries with an existing valid cookie reuse its session rather than minting extra workspaces. Draft edits require `If-Match`. Responses use generated schemas and structured problem details with stable error codes.

| Endpoint suffix | Purpose |
| --- | --- |
| Workspace root: `GET`, `DELETE` | Owner-only access and deletion; deletion cancels work and tombstones the workspace |
| `/documents`, `/documents/{id}/finalize` | Authorized upload and extraction |
| `/twins/{id}/draft`, `/facts/{id}/reviews` | Versioned editing and evidence selection |
| `/twins/{id}/readiness`, `/twins/{id}/seal` | Actionable checks and immutable input version |
| `/evidence` | Manual public-source references, user assertions and assumptions; no server URL fetching |
| `/research-requests` — deferred | Future search capability, disabled until contract and security gates pass; never an unrestricted proxy |
| `/scenarios`, `/suites` | Structured scenario and suite version creation |
| `/runs`, `/runs/{id}/cancel` | Start/cancel a pinned simulation |
| `/runs/{id}/events?after=...`, `/runs/{id}/checkpoints` | Bounded cursor pages for reconnectable playback |
| `/jobs/{id}`, `/findings?suite_id=...` | Progress, failures and findings |
| `/proposals`, `/comparisons` | Concrete changes and paired evaluation |
| `/analysis-reviews`, `/reports` | Owner acknowledgment of material assumptions; independent gap/findings/revision reports, with no official approval state |

Pagination is required for entities, events and within-session change records. All private downloads use the revocable owner-checked proxy in §3.1. Object paths and UUID secrecy are not access controls. Use Secure, HttpOnly, SameSite cookies, origin checks and CSRF tokens for mutations. Session expiry/revocation and workspace deletion take effect on protected commands; stale browser state never authorizes a request. Account routes and token exchange are absent; ownership transfer and conversion are unsupported.

## 8. External APIs and data contracts

### 8.1 Integration matrix

| Service | Requests / information sent | Returned data and handling | Failure behavior |
| --- | --- | --- | --- |
| Gemini managed API | Consented PDF page groups; minimum finding context; fixed schemas | Candidate output validated into contracts; record model, prompt/schema versions and permitted artifacts | Bounded retry; keep extraction unresolved; deterministic explanation fallback; simulations need no provider call |
| Manual evidence intake | User-uploaded public source documents, permitted excerpts, URL metadata, assertions/assumptions | Quarantined documents follow the upload pipeline; source references require user review | Keep unresolved facts visible; a URL alone does not confirm an input; no required official contact |
| Google Search adapter — deferred | Future authorized gap query with public municipality and field context only | Capability-dependent discovery, never automatically confirmed facts; see §8.2 | Feature disabled until its gates pass; manual review remains available |
| Public source retrieval — deferred | Future approved source URLs, no private cookies | MIME/size-limited evidence, dates, checksum and permitted excerpt/archive | Inaccessible/unverified candidate; no promotion from snippet alone |
| Geoapify Geocoding | Text place and country filter | Ranked location candidates; user confirms boundary | Manual reviewed location/polygon entry; record unresolved match |
| Geoapify tiles | Browser viewport and restricted public tile key | Presentation basemap; preserve attribution | Graph overlays/table still work; show basemap unavailable |
| Geofabrik | Regional snapshot download, never user documents | PBF, retrieval date and checksum; source refresh creates a new catalog version | Existing pinned graphs remain usable; no silent substitution |
| Temporary session service | No sign-in credentials; bounded same-origin session creation and random cookie | Digest-backed, expiring ownership checked in Firestore; no Firebase account dependency for guest access | Expiry/revocation denies access and cancels work; no account recovery |
| Cloud Storage for Firebase / Cloud Tasks / Firestore | Service-account operations scoped to artifacts/jobs/data | Durable storage and dispatch under application contracts | Retry, reconcile and expose incomplete states |

Geoapify keys used in browser tiles are deliberately public, restricted by origin and quota, and cannot access private app data. Geocoding and private integrations remain server-side. Provider timeout, quota, retry, retention and allowed-region policies are centralized in adapters. Integration capability tests run before releases; external limits are not hard-coded as product promises.

### 8.2 Google Search: deferred capability, not a pilot launch dependency

The revised PRD accepts manual research and evidence review for the production pilot. Automated Google Search discovery plus durable evidence is deferred. As checked on 12 October 2026, Google's Custom Search JSON API is closed to new customers and existing users must transition by 1 January 2027. It is not the selected production foundation. [Official API notice](https://developers.google.com/custom-search/v1/overview)

Google Search grounding is available for Gemini, but its published terms restrict automated collection of grounded results/links, downstream crawling from those links, and building databases from results. Do not assume it is a drop-in evidence-ingestion API. [Service-specific terms, Grounding with Google Search](https://cloud.google.com/terms/service-terms)

If automated research is later approved, introduce `SearchProvider` with explicit capabilities for discovery, source fetching, persistence, display and retention. Enable automated candidate ingestion only when the provider arrangement explicitly supports this workflow. Product/engineering must obtain the appropriate Google offering/permission and validate its contract before implementing the automated search flow. Do not scaffold an unused provider platform in the pilot or claim that access already exists.

The pilot may generate a minimal Google Search query that the user opens themselves, then accepts independently supplied source documents, excerpts, or URL metadata for human review. It does not scrape Google results, fetch arbitrary URLs, or turn grounded responses into records. This is the selected pilot workflow and must pass the PRD's manual-evidence usability gate. User-supplied evidence still requires source rights and validation; manual entry cannot be used to disguise prohibited bulk ingestion.

If display-only Gemini search grounding is later enabled, isolate it from the evidence database, show required search presentation to the initiating user, and implement the applicable retention/display policy. Do not feed its results into the simulation, source crawler, or fact-selection pipeline without a permitted contract. Non-search Gemini extraction and scenario artifacts retain their separate persistence policy.

### 8.3 External-content controls

In the pilot, validate source references as HTTP(S) URLs without embedded credentials, display them as escaped text/external links, and never fetch them server-side or embed remote source pages in the app. User-uploaded evidence uses the same quarantined validation and size limits as plan documents. Never execute document instructions.

Before enabling a future source fetcher, it must only permit HTTP(S), reject credentials in URLs, block private/link-local/metadata IP ranges, validate DNS and every redirect, and use an isolated egress identity without cloud-data credentials. Enforce content, decompression, redirect and time limits. Never execute retrieved HTML or embedded PDF instructions. Restrict source retrieval to the specific requested page; this is not a general crawler. This gate applies even if a future search contract permits discovery.

Store only artifacts allowed by the source/provider policy. Evidence without archival permission retains permitted metadata and review records; do not pretend its original bytes can always be replayed. Numeric replay uses the sealed reviewed facts, while source reinspection may become unavailable. Deleted evidence and expired artifacts are explicitly tombstoned.

Preserve OSM, Geoapify and other required attribution in app and exports. The project does not use public Nominatim, public Overpass or OSM community tile endpoints as its production service dependency. [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/), [tile policy](https://operations.osmfoundation.org/policies/tiles/)

## 9. Operations, validation, and release requirements

### Security and data lifecycle

Keep service accounts separate for API, provider workers, simulation workers, reports, imports, and migrations. Runtime IAM cannot administer database/rules configuration; application repositories prohibit ownership transfer and enforce versioned record schemas. Restrict private object buckets, disable public access, and redact document text, credentials, and personal information from logs. Treat source material as data even if it contains instructions directed at the model. Public availability of a PDF is not authorization to inspect another user's uploaded copy or analysis.

Configure retention separately for source documents, candidate AI output, review evidence, runs, reports, and change history. Product publishes retention/deletion defaults and processing terms before users upload; source documents may contain personal information despite being public. Deletion covers object generations, derived artifacts and provider copies where supported; backups expire under the published policy. An owner deletion request atomically marks the workspace deleting and cancels queued/running work. Every worker commit checks the tombstone so late retries cannot republish results; reconcile in-flight uploads and generated objects for purge. Restoration reapplies tombstones before access reopens. Deleting one user's public-plan copy must not delete another owner's work. Purging an input explicitly ends full re-execution availability for affected runs.

Temporary expiry follows the same tombstone/cancellation path as explicit deletion. Purge active temporary artifacts and content-bearing records within 24 hours after termination; retain only minimal non-content deletion/accounting records needed for cleanup and bounded abuse controls, never the bearer secret. Use a temporary artifact storage class/bucket whose versioning/soft-delete settings cannot silently extend retention. Any database/storage backup containing temporary content must expire within at most 7 days; validate restore tombstones and effective backup settings. Provider-side retention may differ and must be verified/disclosed before launch. Do not claim zero server storage or immediate physical erasure. These bounds are release requirements, not capabilities already demonstrated.

Use managed regional database HA, point-in-time recovery and storage recovery settings consistent with the retention policy. Initial service recovery targets are RPO at most one hour and RTO at most four hours, pending pilot budget approval and a restoration exercise. A four-hour service recovery can exceed the two-hour session idle limit; it cannot promise restoration of that user's analysis. Task 6.4 must measure which active sessions remain eligible, disclose possible loss and keep original expiry intact. These are targets, not established guarantees.

### Verification strategy

- Unit/property tests: population and water conservation, unique initial occupants, single vehicle ownership, crew windows, distance reservation/consumption and exhaustion, capacity reservations, identical-time ordering, deadline inclusivity, repeated outage handling, invalid units, deterministic tie-breaking, and terminal accounting with an empty queue or unfinished trips.
- Golden graph cases: one-way roads, node-via and way-via turn bans, conditional/unsupported restrictions, bridge segments in both directions, disconnected pickup, boundary truncation, inaccessible shelter connector, and equal-cost paths. Unsupported cases must block or use reviewed conservative exclusions.
- Replay cases: identical pinned inputs produce identical canonical events/metrics; resume after checkpoint and duplicate task delivery produce the same result as uninterrupted execution.
- Small exhaustive reference cases: compare heuristic output with an enumerated optimum to quantify known limitations, without claiming the heuristic always reaches it.
- Input-based verification (ADR-030): freeze exact synthetic arithmetic references for evacuation time/count and water shortfall; record discrepancies and block release on critical failures. Existing visible cases are regression references, not blind held-out validation. PDF + textual location resolved to pinned OSM are the only required external analysis inputs; no field outcomes, event reports, recruited participants or independent/domain reviewers are required. Include plans with missing/ambiguous procedures and verify distinction between documentary claims and assumed policy. PRD §9 defines acceptance and change control for tolerances.
- Sensitivity: nominal/low/high and agreed adverse combinations, reference-policy comparisons, and explicit rank reversals. Do not silently treat a heuristic's failure as proof that every feasible plan fails.
- Database/integration tests: temporary-owner API authorization, client deny rules, one-session ownership and legacy account rejection, revoked/expired sessions, idle-renewal versus expiry races, polling not renewing sessions, stale reviews, expiry/deletion during uploads/jobs/downloads, retry fencing, outbox crash windows, session/network/global limits, and late artifact purge. Same-source/checksum analyses remain isolated; no account path may authorize a request.
- AI evaluations: adjudicate each supplied PDF separately against PRD §9's 90% threshold with explicit denominators and run-critical fact review. Cover image/split tables, graphic marks, unit ranges/conversions, source conflicts, historical/proposed statements, invalid citations, injection, schema failures and unsupported explanation metrics. Unresolved critical facts cannot become operational values. Model changes require reevaluation; no AI replanning evaluation is required until proposed.
- Browser/report tests: complete guest-only flow for each supplied source and two independent sessions; idle/absolute expiry warnings, end-and-delete, refresh/reconnect, shared tabs, lost credentials, completed-result download at compute limits, manual gap-only reports, source preservation, keyboard access, citations and independent/untested labels. Measure 24-hour active purge and seven-day backup expiry; restoration never revives expired sessions.
- Performance: the PRD's 72-hour, 25-barangay, 30-shelter, 50-vehicle, 20,000-edge benchmark and 50-member suite, with declared hardware, AI-call contribution and concurrency. Report deterministic engine time separately from provider time; do not imply the suite meets its end-to-end target until measured.
- Source compatibility: each complete PDF independently passes intake, coverage/review and source-only gap export, then a supplemented baseline/disruption/paired-change/export journey. Milestone A uses local proof adapters; milestone B verifies guest-only access and cross-session isolation; milestone C measures published size/processing limits and temporary-lifetime feasibility. QC outputs identify the selected study area and exclusions. Neither gap export nor full-document ingestion proves a successful simulation.

Operational restoration is bounded to still-active temporary state and its original valid credential/expiry. Apply expiry and deletion tombstones before reopening access; never extend a session or recover a lost credential from backup. Backups are not user history. Record recovery objectives and demonstrate them in Task 6.4 within the existing retention bounds.

### Deployment and observability

CI runs changed-code checks, contract generation, schema upgrades and ownership/rules checks against the Firestore emulator plus required cloud smoke evidence, engine invariants/replay, authorization integration cases and relevant browser tests. Build signed/versioned container artifacts; stage migrations use expand/contract changes before compatible application rollouts. Roll back by known image digest while preserving the database schema contract and historical engine artifacts. Do not execute migrations independently in every autoscaled instance.

Trace IDs link API command → job → attempt → provider request → run. Monitor queue age, expired leases, retries, provider failures, extraction review rates, invariant failures, run duration, incomplete suite members, per-workspace spend and recovery health. Never place raw plan contents or tokens in telemetry. Reserve estimated quota before enqueueing, settle actual usage afterward, and stop new work at hard workspace limits without corrupting existing jobs.

Public-beta production blockers: working guest-only access with session isolation; verified expiry/purge/backups and published provider retention/processing terms; engineering-tested readiness and explicit provisional severity/water assumptions; explicit crew/fuel assumptions; selected-router OSM compiler/geographic validation and remaining dependency gates; model-validity, sensitivity, document-gap and manual-evidence acceptance; security/replay/load/deletion checks; session/network/global abuse and cost limits; support ownership; and a demonstrated restore. Government approval is not a product gate. Accounts, persistent analysis/conversation history, automated Google Search, temporary-to-saved conversion, collaborative access, and AI replanning remain deferred. Record exact limits and versions in the release manifest. No application code is being claimed complete by this document.

## 10. Decision log

Decision status is selected unless explicitly marked gated. Replacements keep the old entry and add a superseding decision with migration consequences.

| ID | Decision | Alternatives considered | Why / consequence |
| --- | --- | --- | --- |
| ADR-001 | Modular Python backend with separate API/worker deployments | Microservices; all logic in web server | Keeps transactions and domain rules together while allowing compute isolation; split services only with measured need. |
| ADR-002 | React/Vite SPA | Next.js SSR; server-rendered templates | Four private interactive screens do not require SSR; one backend owns authorization and business logic. |
| ADR-003 — superseded by ADR-029 | PostgreSQL/PostGIS plus GCS | Firestore; document-only database; files in SQL | Historical relational design; replaced by the user's Firebase selection on 13 October 2026. |
| ADR-004 — superseded by ADR-018, then ADR-023/029 | Tenant memberships and scoped roles in SQL, managed identity | Client role claims; separate database per user | Historical role design replaced by single-owner workspaces; ADR-029 replaces RLS with Firestore server authorization/IAM and client deny rules. Government roles and memberships are not implemented. |
| ADR-005 | Immutable sealed versions and run bundles | Mutating live model referenced by old runs | Preserves personal review, source fidelity and reproducibility; creates additional storage and lifecycle work. |
| ADR-006 | Pure discrete-event simulation | LLM simulation; fixed-minute stepping; individual agents | Event-driven aggregate operations are inspectable and efficient; atomic-edge and cohort assumptions are documented limits. |
| ADR-007 — implementation gated by ADR-019 | Directed OSM snapshots and local routing | Live hosted routing calls; tile-derived roads | Closures and replay require control over the exact graph. Reuse gate selects the production compiler/router; topology validation remains required. |
| ADR-008 | Deterministic greedy allocation with bounded improvements | OR-Tools optimization; LLM assignments | Establishes a reproducible baseline with predictable computation. Exact optimization is deferred until benchmarks justify its complexity; do not claim optimality. |
| ADR-009 — pilot scope superseded by ADR-018 | AI outside the engine, saved proposals/fallbacks | Live autonomous agent inside the event loop | Boundary remains mandatory; pilot AI is extraction and optional explanations, with no AI replanning branches. |
| ADR-010 | Cloud Tasks with outbox, leases and fencing | In-process tasks; Redis/Celery; full workflow platform | Managed delivery plus explicit database state handles the bounded pipeline; retries require idempotent stage design. |
| ADR-011 | Polling and immutable event chunks | WebSockets; always-open SSE | Playback and recovery do not require bidirectional low-latency connections. Upgrade only for demonstrated UX needs. |
| ADR-012 | Geoapify UI services and Geofabrik source snapshots | Public OSM endpoints; self-host all map infrastructure | Managed discovery/display with independent reproducible roads; paid-service quotas and attribution remain operational dependencies. |
| ADR-013 — superseded by ADR-018 for pilot | Google Search adapter with contracted ingestion capabilities | Custom Search JSON API; treating Gemini grounding as a search scraper | Original automated-search launch gate is replaced by manual evidence acceptance. Provider contract remains a gate for the deferred feature (§8.2). |
| ADR-014 | One cloud, provisional Singapore region | Multi-cloud; mandatory on-premise; unreviewed global endpoints | Reduces operational overhead and aligns managed model/storage/queue services. Data-owner and capability review can require a revised region decision. |
| ADR-015 | Evidence-backed rules rank findings; Gemini explains | LLM severity scores; one resilience pass rate | Quantities, recurrence, and policy are auditable; narrative cannot invent evidence or probability. |
| ADR-016 | Compare identical exogenous suites and policy versions | Fresh random scenarios for each plan | Makes plan changes interpretable; model/graph upgrades are a separate experiment class. |
| ADR-017 | Pin runtime/model/policy manifests at release | Permanently hard-coded model name; floating aliases | Supports provider evolution while preserving saved artifacts and detecting behavior changes through evaluations. |
| ADR-018 — audience/approval superseded by ADR-023 | Historical invitation-only municipal pilot; manual evidence; deterministic scenarios/replanning; planner and distinct approver | Launch public users, department scopes, automated search and AI branches together | Retained for decision history only. ADR-023 removes invitation/official approval and enables public users; manual evidence and deterministic simulation remain selected. |
| ADR-019 — superseded by ADR-028 | Evaluate routing reuse before production compiler implementation | Commit immediately to bespoke OSM semantics; deploy two routers | The required one-router selection was made in ADR-028 after the pinned small-sample comparison. |
| ADR-020 | Explicit horizon/initial-occupant accounting; dedicated crew windows and finite distance budgets | Implicit terminal success; unlimited operations; full crew/fuel logistics | Adds required cohort/budget fields and terminal metrics to contracts. No refueling/shared-crew or in-scenario supply scheduling in pilot. |
| ADR-021 | Safety-first evacuation with separate water-sufficiency outcomes | Reject every water-deficient shelter; label every arrival fully successful | Clarifies PRD hard invariants and extends ADR-008 ranking. Water cannot go negative; shortage remains visible even when arrival avoids a deadline miss. Input-based engineering verification and explicit user assumptions apply (ADR-030); no official-use state exists. |
| ADR-022 — empirical/reviewer scope superseded by ADR-030 | Prespecified arithmetic tolerances, bounded sensitivity and reference-policy checks | Conservation-only validation; one allocator presented as plan truth | Supplements ADR-008/015/016. Keep each baseline/proposal pair on identical conditions and policy; policy/uncertainty sweeps are separate experiments. |
| ADR-023 — sign-in requirement superseded by ADR-025 | Public self-service analysis; private single-owner workspaces; hypothetical revisions only | Government-only pilot; official approvals; shared municipality model | Removes municipal authority workflows under ADR-004/018. Source immutability and personal reviews remain selected. ADR-025 adds temporary ownership; collaboration remains deferred. |
| ADR-024 | Separate documentary review from simulation readiness | Require official resource confirmation; block all review on incomplete inputs; infer missing facts as zero | Gap-only review/export works without simulation. Explicit usable assumptions can make a model runnable. Track cited plan rules versus assumed policies and label incomplete/untested outputs. Product validation is independent of user or municipal approval. |
| ADR-025 — account option superseded by ADR-031 | No-sign-in temporary analysis plus optional saved accounts | Mandatory sign-in; browser-only processing; hidden anonymous accounts; automatic account attachment | Adds temporary-session digest/expiry and exclusive workspace ownership types, owner-aware jobs/reviews and bounded retention (RLS replaced by ADR-029). Two-hour idle/24-hour absolute expiry; active purge within 24 hours and backups within seven days. No account history/recovery or automatic conversion. Reuse the same engine/report path; constrain paid work by session/network/global budgets. |
| ADR-026 | Separate full-document compatibility from declared study-area simulation; require both supplied PDF cases | One-plan acceptance; infer operational inventory from documentary statements; whole-QC claim from a small proof | User selected an explicit QC study area on 13 October 2026. PRD §5.1 governs per-file intake minima and separate source-only/supplemented outcomes. Preserve coverage, source units/ranges, temporal/geographic applicability and conflicts before operational promotion. No dependency or provider authorization is granted. |
| ADR-027 | Use a small Python standard-library Dijkstra reference router for Task 2.3 | Add NetworkX 3.6.1 as a new dependency | The user selected the standard-library option on 13 October 2026 after reviewing a concrete NetworkX proposal. No NetworkX dependency is installed. ADR-028 subsequently selected this exact-edge algorithm for production integration. |
| ADR-028 | Select the standard-library exact-edge Dijkstra router as the one production implementation | Deploy Valhalla 3.9.1 or two runtime routers | [Measured comparison and exclusions](../release/routing/ADR-028.md): same pinned OSM bridge/turn cases, exact directed-closure gap in Valhalla's request API, stable reference ties and conservative uncertainty. `pyvalhalla` is development-only. Task 3.6 still must prove the OSM compiler and later scale gates. |
| ADR-029 — end-user Authentication superseded by ADR-031 | User-selected Firebase Hosting, Authentication (email and Google), Firestore, Storage; backend Gemini key path | ADR-003 Cloud SQL/PostGIS; web container hosting; assumed Vertex AI-only integration | Selected 13 October 2026. Supersedes ADR-003 and the persistence/transport aspects of ADR-004/025; keeps exclusive ownership and lifecycle guarantees. Replace SQL RLS/FKs with tested server authorization, reference checks and Firestore transactions; deny direct client data access. Geometry stays in Python/artifacts. Hosting fronts Cloud Run with `__session` transport. Record supplied project metadata in plan R.2; key/service configuration, dependencies, provider terms, retention and release remain gated. |
| ADR-030 | PDF + textual location/OSM and explicit assumptions are the required analysis basis; engineering verification replaces field/reviewer/participant gates | Mandatory event outcomes, after-action reports, independent domain approval and recruited usability studies | Selected by the user on 14 October 2026. Supersedes the empirical and independent-review portions of ADR-021/022 and prior Task 2.1/3.9/6.6 criteria. Freeze hand-calculated regression references and hash-pinned inputs, check PDF extraction against source pages and OSM topology against the pinned snapshot, retain boundary/replay/sensitivity checks, and use scripted workflow/traceability acceptance. Extra documents are optional; missing values stay unknown or become explicit user-accepted assumptions. No field-validity or human-usability claim follows. Source processing, dependencies, security, ownership and deployment gates remain. |
| ADR-031 | Guest-only on-demand analysis; no sign-in, user accounts, persistent analysis/conversation history or cross-device recovery | Optional saved accounts and dual ownership in ADR-025/029; removal of all server state | User-approved 15 October 2026. Preserve completed Phase 1–3 and milestone A evidence; replan Phase 4 and align Phases 5–6. Retain private temporary Firestore/Storage state, immutable within-session versions, Cloud Tasks/OIDC, worker recovery, expiry, purge and session/network/global cost controls. Keep two-hour idle/24-hour absolute expiry, 24-hour active-copy purge and seven-day backup bounds. Operational restore can recover only still-valid sessions with original credentials and expiry; it cannot restore deleted work or lost access. Remove account surfaces/dependency gates in revised 4.1–4.3; do not disable shared-project Auth. Product scope changes do not assert implementation or production readiness. |

## 11. Remaining implementation decisions

These are explicit configuration or launch gates, not permission to redefine the architecture opportunistically:

1. Complete PRD milestone A for both supplied PDF cases under §6.1 and PRD §5.1: use each permitted PDF and textual location, resolve the concrete QC study area against OSM, freeze exact arithmetic references before scoring, and demonstrate each source-only gap review plus supplemented baseline → disruption → paired hypothetical change → export. A municipal sponsor is not required.
2. Complete the remaining dependency/runtime matrix (§2.1), including the currently unselected PDF validator/scanner and client generator. Implement only ADR-028's selected router in the production OSM compiler and validate Philippine source, exact closure/restriction behavior and workload scale before deployment.
3. Verify the user-reported Gemini key's actual API/project and select/evaluate exact GA model IDs, endpoints and SDK versions for extraction and optional explanations. Record billing-tier processing/retention terms and secret configuration; do not infer regional or Vertex AI access. Save provider-reported version metadata where available. AI scenarios/replanning are deferred.
4. Implement guest-only temporary sessions, exclusive owner-scoped workspaces, expiry/deletion during jobs, effective purge/backup bounds and service-region/provider-retention disclosures. Verify lifecycle defaults and guest limits before beta. Use explicit assertions/assumptions for incomplete evidence; no official confirmation process is required.
5. Declare PDF/OSM values or explicit exploratory assumptions for hazard effects, travel/loading, crew windows, distance budgets, water policy, assistance priorities, severity thresholds, graph buffer and access-connector distances. No field calibration is required. Run the required sensitivity and reference-policy comparisons.
6. Benchmark engine/import memory and cost, choose managed-service sizes and temporary-session/network/global quotas, and record supported limits, budget, operational owner, restore results and PRD acceptance before opening public beta.
7. Later-feature gate only: obtain a suitable Google Search interface/arrangement and validate its API, display, fetching and persistence contract before enabling automated evidence research. This does not block a pilot that passes manual-evidence acceptance.

Implementation order follows PRD §12: model/data proof for a public user, public workspace flow, production hardening, then evidence-driven expansion. The small proof preserves owner isolation and source immutability; public onboarding is part of milestone B. Government/department approval workflows are outside scope. Do not build general orchestration or AI branching in milestone A. Use synthetic/redacted fixtures until document-processing settings and consent are ready.

External documentation was consulted on 12 October 2026 and Firebase Hosting/Firestore/Storage plus Gemini key documentation rechecked on 13 October 2026 for ADR-029. Recheck provider capabilities and terms before enabling an integration or changing its data handling. Architecture changes are reviewed here; lockfiles and manifests record the exact implemented release.
