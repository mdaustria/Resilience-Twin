# Resilience Twin: agent guide

Resilience Twin helps researchers, residents, students, and community groups independently evaluate public Philippine disaster plans through evidence review and deterministic evacuation/water simulations.
Target: production public self-service application; current stage: milestone A evidence recorded; guest-only Phase 4 backend revalidation next (ADR-031).

## Commands

Run from the repository root with the approved versions in `release/dependencies.md`. Task 1.1 provides the install/run/test/lint commands and `pnpm check:bootstrap`. Task 1.3 adds browser tests. Task 1.4 provides `pnpm check` locally and in GitHub Actions. Do not report an unavailable or unverified command as passing.

- Install: `uv sync --frozen`, then `pnpm install --frozen-lockfile`.
- Run: `pnpm dev` (local web and API; synthetic fixtures until provider/data gates pass).
- Test: `uv run pytest` and `pnpm test` (non-watch mode).
- Browser test: `pnpm exec playwright test`.
- Lint: `uv run ruff check .`, `uv run mypy packages services`, and `pnpm lint`.
- Bootstrap check: `pnpm check:bootstrap` (generated-client drift, Python/web tests, lint, types, and web build).
- Combined check: `pnpm check` (lint, type checks, tests, contract drift, and applicable integration/browser checks; missing prerequisites must fail visibly).
- Task 4.1 Firestore check: `uv run pytest tests/integration/test_owner_access.py tests/integration/test_firestore_rules.py tests/integration/test_version_storage.py`. It starts the pinned Firestore emulator and requires a separately authorized nonproduction cloud smoke target through `RT_FIRESTORE_SMOKE_PROJECT`, `RT_FIRESTORE_SMOKE_DATABASE`, `GOOGLE_APPLICATION_CREDENTIALS`, and `RT_FIRESTORE_SMOKE_APPROVED=1`; absent cloud evidence fails visibly.
- Documentation check (PowerShell): `@('AGENTS.md','docs/plan.md','docs/progress.md','docs/architecture-essentials.md','docs/architecture.md','docs/PRD.md') | ForEach-Object { if (!(Test-Path -LiteralPath $_ -PathType Leaf)) { throw "Missing: $_" }; if (!(Get-Content -LiteralPath $_ -Raw).Trim()) { throw "Empty: $_" } }`.

Install prerequisites and exact approved versions are recorded by Task 1.1 in `release/dependencies.md`. Do not substitute an arbitrary installed runtime or silently install tools.

## Read before editing

- [docs/architecture-essentials.md](docs/architecture-essentials.md): always, before any edit.
- [docs/plan.md](docs/plan.md): find your task, its files, dependencies, and acceptance command.
- [docs/progress.md](docs/progress.md): read the latest entry and continue from its handoff.
- [docs/architecture.md](docs/architecture.md): when your task changes the design; also consult the relevant section when implementing a specified algorithm or contract.
- [docs/PRD.md](docs/PRD.md): when requirements or acceptance criteria are unclear.

## Rules

- Do not add dependencies without asking. Present the concrete packages/tools, versions, purpose, and compatibility evidence first. A technology named in the architecture is not approval to install it; reuse approval already recorded in the conversation or handoff.
- Take one session-sized task at a time. Stay inside its listed files, or explain the necessary scope change in the plan and progress log. Every task also permits updating those two handoff files.
- A task is done only when its **Done when** command passes and its observable behavior is verified. Missing required tooling, fixtures, credentials, or check evidence means partial/blocked, not done. Verification uses PDF + textual-location/OSM inputs and explicit assumptions; no field data, recruited participants, or independent/domain approver is required (ADR-030). Never replace a substantive check with a placeholder, skipped test, or unconditional success.
- Before finishing, update the task checkbox in `docs/plan.md` and append a dated entry to `docs/progress.md`, including exact checks and results, decisions, failed approaches, gotchas, and the next starting point. Leave partial/blocked tasks unchecked.
- Follow the PRD milestone gates. Prove the small model/data path before expanding public onboarding and infrastructure. Use synthetic/redacted fixtures until consent and provider settings are ready; the POC is local and not a public deployment.
- Keep dependencies pointing inward. Generate browser contracts from Python schemas; do not hand-edit generated clients. Keep the simulation free of HTTP, database, AI, and wall-clock dependencies.
- Preserve integer units, deterministic ordering, pinned run inputs, conservation, and terminal accounting. Unknown values are not zero. Explicit assumptions remain visible; document-gap review/export works even when simulation cannot run.
- Enforce exclusive temporary-session ownership and immutable source documents. No sign-in, saved user/conversation history, government approval, municipal role, or temporary-to-saved conversion belongs in the initial release. Temporary processing state expires; downloaded reports remain with the user. Findings and revisions are independent and hypothetical.
- If design changes are necessary, update `docs/architecture.md` and `docs/architecture-essentials.md` together and record the decision. Keep this guide short; detailed design belongs in those documents.
