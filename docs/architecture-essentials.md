# Resilience Twin — Architecture Essentials

One-page developer reference · 12 October 2026  
Authority: [architecture.md](architecture.md); product scope: [PRD.md](PRD.md). This is the public-use design, not an implementation-status report. Routing implementation remains gated on a reuse evaluation.

## Public-use boundary and next step

Anyone can select **Start temporary analysis** without signing in, or **Sign in to save your work**, to evaluate a public disaster plan. Each private workspace belongs exclusively to a temporary browser session or account. No government affiliation or official approval is required. Recommendations and hypothetical revisions affect only that workspace; source PDFs remain unchanged. All reports are independent analyses.

Temporary mode supports upload/review/simulation/comparison/download with visible smaller limits. It expires after two hours without deliberate activity or 24 hours from creation, whichever comes first; jobs/polling do not renew it. Show expiry warnings and End and delete. Refresh works while the credential is valid; closing a tab is not guaranteed deletion. Lost credentials have no recovery. Revoke access/cancel jobs on expiry/end, purge active copies within 24 hours and expire backups within seven days; verify/disclose provider retention. Temporary means short-lived server storage, not zero storage. Sign-in never silently saves guest work; download before expiry, then start a separate saved workspace.

Start with **PRD milestone A**: one public plan, reviewed road sample, explicit evidence/assumptions, an independently reviewed numerical validation protocol, and a document-gap review → baseline → disruption → paired-change demonstration. Require boundary fixtures, held-out results, sensitivity/reference-policy checks, and the routing/dependency gate. Then build public onboarding/private workspaces and pass load/security/deletion/restore gates. No municipal sponsor is required.

Manual evidence review and deterministic scenarios/replanning remain the first-release path. Temporary-to-saved conversion, shared editing, automated search/source fetching, AI scenarios/branches, in-scenario resupply, shared crews and refueling are deferred. Official approvals and departmental administration are outside the product scope.

## The stack

- **Web:** React + TypeScript + Vite; React Router, TanStack Query, Tailwind/Radix; MapLibre and PDF.js.
- **Backend:** Python + FastAPI + Pydantic; SQLAlchemy/Alembic; generated TypeScript API contracts.
- **Engine:** pure Python/heapq kernel, deterministic greedy allocation and a simple reference policy. NetworkX is the reference router; compare routing reuse before selecting the production compiler. pyosmium/Shapely/pyproj handle PBF/geometry/projection work, not all road semantics.
- **Data:** Cloud SQL PostgreSQL/PostGIS with exclusive temporary/account-owner RLS; private GCS artifacts; opaque digest-backed temporary cookies and optional Identity Platform account sessions. No hidden guest accounts, government roles or approval tables.
- **AI/data providers:** Gemini via Google Gen AI SDK for extraction and optional explanations; Geoapify geocoding/tiles; Geofabrik OSM snapshots. Manual public sources, attributed assertions and explicit assumptions are the pilot path. Google Search ingestion and source fetching remain gated later features.
- **Operations:** Cloud Run, Cloud Tasks + SQL outbox/leases, Cloud Run Jobs for regional imports; Terraform, GitHub Actions, OpenTelemetry. pytest/Hypothesis, Vitest/Playwright; uv/pnpm lockfiles.

Before full implementation, record exact dependency/runtime versions and compatibility, source licenses, provider model/region settings, and the selected PDF validator/scanner and client generator. Do not build a general workflow engine or deploy a second orchestrator alongside Cloud Tasks without a replacement decision.

## Folder map

```text
apps/web/                         Web manifests, entry point, Dockerfile, tests/
  src/{app,lib,components}/       Shared UI; components/{map,reports,session}/
  src/features/                  community-twin/, scenario/, simulation/, findings/
services/{api,worker,osm-import}/ Runtime placeholders; worker/handlers/
packages/contracts/              Canonical Python API/artifact schemas
packages/domain/                 inputs/, scenarios/, proposals/, findings/,
                                 comparisons/, evidence/, readiness/, versions/, geography/
packages/application/            deletion/, documents/, experiments/, extraction/,
                                 jobs/, reports/, review/, sessions/, usage/, workspaces/
packages/simulation/             kernel/, routing/, policies/, metrics/, runner.py
packages/adapters/               persistence/, storage/, ai/, sources/, geo/compiler/,
                                 local/, documents/, identity/, telemetry/, tasks/, search/
packages/{reports,client-generated}/ Reports and generated-client placeholder
db/{migrations,seeds}/
tests/{engine,integration,contracts,e2e,fixtures,security}/
infra/terraform/{data,environments,runtime}/
scripts/  release/  docs/  .github/workflows/
AGENTS.md  compose.yaml  package.json  playwright.config.ts
pyproject.toml  uv.lock  pnpm-workspace.yaml  pnpm-lock.yaml
```

The complete file listing is [scaffold-tree.md](scaffold-tree.md). At the user's request, Task 0.1 reserves all planned paths with headers and empty exports. These are placeholders, including the lockfiles, workflows, and Dockerfiles; builds and test-runner startup require Task 1.1. JSON uses `_comment` metadata. Generated-client and deferred-search locations contain only README placeholders. No data-model implementation, dependency approval, or milestone gate is satisfied by file existence; future implementations remain gated as described above.

## Core conventions

1. Dependencies point inward: entry points → application → domain/contracts. Adapters implement ports; the engine never imports them.
2. Scope every private row, object and job to its account or unexpired temporary owner. Enforce SQL ownership/RLS, never PDF/municipality matching. Temporary bearer secrets stay in Secure/HttpOnly/SameSite cookies; store only digests, enforce CSRF and never put tokens in links/logs. Workspace/session resets cannot bypass network/account/global limits.
3. Edit drafts with revision checks; seal immutable baselines/variants. User acknowledgment binds exact evidence/assumption hashes, not official authority. Missing computational inputs block only simulation: document-gap review/export remains available. An explicit usable assumption can enable a run without official contact.
4. Generate client contracts from Pydantic/OpenAPI. Pin schema, graph, engine, policy, seed and accepted evidence artifacts in each run manifest; pilot response mode is deterministic.
5. Use integer people/seats, seconds, milliliters and known costs in centavos. Store UTC; display `Asia/Manila`. Coordinates are longitude/latitude; metric calculations use a recorded projection.
6. Deterministic events have stable ordering and tie-breaks. The simulated response policy sees only known conditions. Count initial occupants as unique cohorts; check conservation, crew/vehicle windows, distance budgets and shelter reservations. Process a terminal horizon event; unfinished trips/future deadlines never become assumed successes.
7. Jobs return `202` and tolerate duplicates through outbox, leases and fencing. Saved jobs survive sign-out; temporary jobs stop at expiry/end. Check remaining lifetime before enqueueing and expiry at worker commits. Tombstones prevent resurrection. Temporary downloads use a revocable owner-checked proxy; downloaded reports remain with the user.
8. Compare identical exogenous scenarios/seeds/policies within each pair. Sensitivity/reference-policy experiments expose rank reversals. Distinguish cited plan rules from default-policy assumptions and missing documentation from missing resources. Report arrival and water sufficiency separately. Save/export hypothetical revisions only in the owner's workspace, with tested/untested labels.

## Never do this

- Never let Gemini calculate authoritative outcomes, execute source instructions, or mutate engine state directly. Never present the app's analysis as official approval.
- Never invent missing capacities, coordinates, roads, forecasts, resources or permission; unknown is not zero.
- Never use fresh AI/network calls during replay, wall-clock time for algorithmic stopping, or unordered iteration for tie-breaking.
- Never overbook vehicles, silently overfill shelters, erase stranded residents, invent fuel/crew availability, or claim heuristic output is optimal. Never let water inventory go negative or call a water-deficient arrival fully sufficient.
- Never scrape Google results, persist grounding into an evidence database without permission, or treat search snippets as confirmed facts.
- Never trust client ownership claims, expose private objects/secrets, log plan contents, overwrite the source plan, or mutate another workspace. Saving a hypothetical revision never means adoption or field implementation.

Change the full architecture and this reference together. Resolve temporary/account onboarding, private ownership, expiry/purge/backups, provider terms, model configuration, routing/dependency selection, evidence/readiness, model validity/sensitivity, session/network/account/global cost controls and security/load/restore gates before beta. Search integration is deferred; government approval is not a product gate.
