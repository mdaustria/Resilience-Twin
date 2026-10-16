# Supervisor handover — 16 October 2026

This repository is a research prototype in progress, not a deployed public service. Start with [the agent guide](../AGENTS.md), [the implementation plan](plan.md), [the latest progress entry](progress.md), [architecture essentials](architecture-essentials.md), and [the PRD](PRD.md). The plan's checkboxes and acceptance commands are the source of truth for completion.

## Current state and next task

- Milestone A evidence is recorded. Revised guest-only Phase 4 and Tasks 5.1–5.6 are recorded complete in the plan and progress log.
- Task **5.7 remains open**. Both exact public PDFs passed full-file intake, source-only review and gap-report export in separate local guest sessions. `release/validation/milestone-b/source-only-browser.json` explicitly says `full_journey_verified: false`.
- The guest browser has no sealed-scenario-to-worker submission path. Worker inputs must be deterministically built from the sealed review, baseline, graph, scenario and proposal; the older pilot proof uses fixed resources that do not equal the guest baseline. Complete both PDF run/compare/evaluated-export journeys, accessibility and session isolation/lifecycle evidence, then run `pnpm check` and `uv run python scripts/verify_release.py --milestone B`. Do not mark 5.7 or milestone B complete before those pass.
- Phase 6 deployment, retention, scale and security gates remain open. Local emulator and synthetic results are not production evidence.

## Reproducing locally

Use the exact runtime and dependency versions and setup in [`release/dependencies.md`](../release/dependencies.md). Install with `uv sync --frozen` and `pnpm install --frozen-lockfile`. The commands in `AGENTS.md` describe checks. Some checks need a pinned Firestore emulator, Java, ClamAV and the matching Playwright browser. The full `pnpm check` includes an authorized nonproduction Firestore smoke target; without its separately provided credentials and approval settings, that check must fail visibly. The GitHub workflow currently has no cloud credential configured for that smoke gate, so do not infer a green full check from a push or from earlier local results.

The two original public PDFs are **not tracked in Git**. The local browser tests expect exact SHA-256-named copies under `.runtime/task32-intake/pilot-qc-temporary/documents/` and `.runtime/task32-intake/pilot-guiguinto-saved/documents/`. Their hashes, byte sizes and page counts are in [`release/validation/document-intake/full-source-intake.json`](../release/validation/document-intake/full-source-intake.json). Provide those source files separately to reproduce the exact-PDF tests, verify their hashes, and do not mistake a ZIP of tracked source for a complete input-data handoff. The `.runtime` directory also contains machine-specific installed tools, temporary test files and potentially local credentials; it is excluded from Git and should be excluded from a shared ZIP. Recreate it using the dependency guide.

## Access and ownership to transfer separately

- Grant the supervisor appropriate access to the GitHub repository and verify they can clone it. Share the final commit hash with the handoff.
- If they will run cloud or provider checks, arrange their own approved access to the nonproduction Google Cloud/Firebase project, named Firestore database, Storage bucket and Gemini account/key. Provide credentials only through an approved secure channel; do not put service-account JSON, API keys or passwords in Git, the ZIP or chat.
- Decide who owns billing/spend limits, provider settings, deployment, logs and retained data before any public staging or release. The provider and infrastructure status is recorded in [`release/providers.json`](../release/providers.json), [`release/dependencies.md`](../release/dependencies.md) and the Phase 6 plan.
- Preserve the public-PDF provenance and usage permissions when transferring the original inputs. The repo holds hashes, extracted evidence and generated reports, but the original bytes must be handed over separately if the supervisor needs to rerun exact-source validation.

## Suggested package

Share the GitHub repository as the canonical code/evidence snapshot and a clean ZIP of the same commit for convenience. Exclude `.git`, `.runtime`, `.venv`, `node_modules`, caches, build output and logs from the ZIP. Supply the two original PDFs separately with their hashes. Ask the supervisor to clone, install the pinned tools, and run the checks for the next task; current milestone status must remain open until the recorded acceptance commands pass.
