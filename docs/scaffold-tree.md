<!--
Purpose: Show the complete empty scaffold for user approval.
Task: docs/plan.md 0.1.
Uses: docs/plan.md, docs/architecture.md, docs/architecture-essentials.md.
TODO(agent): implement
-->

# Scaffold review tree

12 October 2026. All repository paths are shown except Git internals. Existing project documents retain their content; new implementation files contain only headers and empty exports. This inventory is the review artifact, not application logic.

Builds, test runners, lockfiles, containers, and CI are not configured. Task 1.1 must establish approved tooling before these can be verified. No implementation task is complete, and no commit has been made. Requested commit message after user approval: scaffold: empty structure.

```text
Resilience Twin/
+-- .github/
|   \-- workflows/
|       +-- check.yml
|       \-- README.md
+-- apps/
|   \-- web/
|       +-- src/
|       |   +-- app/
|       |   |   \-- index.ts
|       |   +-- components/
|       |   |   +-- map/
|       |   |   |   \-- index.ts
|       |   |   +-- reports/
|       |   |   |   \-- index.ts
|       |   |   +-- session/
|       |   |   |   \-- index.ts
|       |   |   \-- index.ts
|       |   +-- features/
|       |   |   +-- community-twin/
|       |   |   |   \-- index.ts
|       |   |   +-- findings/
|       |   |   |   \-- index.ts
|       |   |   +-- scenario/
|       |   |   |   \-- index.ts
|       |   |   \-- simulation/
|       |   |       \-- index.ts
|       |   +-- lib/
|       |   |   +-- formatting.ts
|       |   |   +-- index.ts
|       |   |   \-- polling.ts
|       |   \-- main.tsx
|       +-- tests/
|       |   \-- README.md
|       +-- Dockerfile
|       +-- eslint.config.js
|       +-- index.html
|       +-- package.json
|       +-- tsconfig.json
|       \-- vite.config.ts
+-- db/
|   +-- migrations/
|   |   \-- README.md
|   \-- seeds/
|       \-- README.md
+-- docs/
|   +-- architecture-essentials.md
|   +-- architecture.md
|   +-- deployment-runbook.md
|   +-- document-processing.md
|   +-- operations-runbook.md
|   +-- plan.md
|   +-- PRD.md
|   +-- progress.md
|   +-- recovery-runbook.md
|   +-- retention-runbook.md
|   +-- scaffold-tree.md
|   \-- validation-protocol.md
+-- infra/
|   \-- terraform/
|       +-- data/
|       |   \-- README.md
|       +-- environments/
|       |   \-- README.md
|       \-- runtime/
|           \-- README.md
+-- packages/
|   +-- adapters/
|   |   +-- ai/
|   |   |   \-- __init__.py
|   |   +-- documents/
|   |   |   \-- __init__.py
|   |   +-- geo/
|   |   |   +-- compiler/
|   |   |   |   \-- __init__.py
|   |   |   +-- __init__.py
|   |   |   +-- catalog.py
|   |   |   +-- extract.py
|   |   |   \-- geocoding.py
|   |   +-- identity/
|   |   |   \-- __init__.py
|   |   +-- local/
|   |   |   \-- __init__.py
|   |   +-- persistence/
|   |   |   +-- __init__.py
|   |   |   +-- deletion.py
|   |   |   +-- jobs.py
|   |   |   +-- runs.py
|   |   |   +-- sessions.py
|   |   |   \-- usage.py
|   |   +-- search/
|   |   |   \-- README.md
|   |   +-- sources/
|   |   |   \-- __init__.py
|   |   +-- storage/
|   |   |   +-- __init__.py
|   |   |   \-- local.py
|   |   +-- tasks/
|   |   |   \-- __init__.py
|   |   +-- telemetry/
|   |   |   \-- __init__.py
|   |   \-- __init__.py
|   +-- application/
|   |   +-- deletion/
|   |   |   \-- __init__.py
|   |   +-- documents/
|   |   |   \-- __init__.py
|   |   +-- experiments/
|   |   |   \-- __init__.py
|   |   +-- extraction/
|   |   |   \-- __init__.py
|   |   +-- jobs/
|   |   |   \-- __init__.py
|   |   +-- reports/
|   |   |   \-- __init__.py
|   |   +-- review/
|   |   |   \-- __init__.py
|   |   +-- sessions/
|   |   |   \-- __init__.py
|   |   +-- usage/
|   |   |   \-- __init__.py
|   |   +-- workspaces/
|   |   |   \-- __init__.py
|   |   \-- __init__.py
|   +-- client-generated/
|   |   \-- README.md
|   +-- contracts/
|   |   +-- __init__.py
|   |   +-- checkpoints.py
|   |   +-- documents.py
|   |   +-- evidence.py
|   |   +-- graphs.py
|   |   \-- scenarios.py
|   +-- domain/
|   |   +-- comparisons/
|   |   |   \-- __init__.py
|   |   +-- evidence/
|   |   |   \-- __init__.py
|   |   +-- findings/
|   |   |   \-- __init__.py
|   |   +-- geography/
|   |   |   \-- __init__.py
|   |   +-- inputs/
|   |   |   \-- __init__.py
|   |   +-- proposals/
|   |   |   \-- __init__.py
|   |   +-- readiness/
|   |   |   \-- __init__.py
|   |   +-- scenarios/
|   |   |   \-- __init__.py
|   |   +-- versions/
|   |   |   \-- __init__.py
|   |   \-- __init__.py
|   +-- reports/
|   |   \-- __init__.py
|   \-- simulation/
|       +-- kernel/
|       |   +-- __init__.py
|       |   +-- checkpoints.py
|       |   +-- disruptions.py
|       |   +-- observations.py
|       |   +-- resources.py
|       |   \-- water.py
|       +-- metrics/
|       |   +-- __init__.py
|       |   +-- population.py
|       |   \-- water.py
|       +-- policies/
|       |   +-- __init__.py
|       |   +-- deadline_greedy.py
|       |   +-- earliest_deadline_reference.py
|       |   \-- feasibility.py
|       +-- routing/
|       |   \-- __init__.py
|       +-- __init__.py
|       \-- runner.py
+-- release/
|   +-- infrastructure/
|   |   \-- README.md
|   +-- manifests/
|   |   \-- README.md
|   +-- routing/
|   |   \-- README.md
|   +-- validation/
|   |   +-- domain-review/
|   |   |   \-- README.md
|   |   +-- extraction/
|   |   |   \-- README.md
|   |   +-- geography/
|   |   |   \-- README.md
|   |   +-- milestone-a/
|   |   |   \-- README.md
|   |   +-- milestone-b/
|   |   |   \-- README.md
|   |   +-- performance/
|   |   |   \-- README.md
|   |   +-- recovery/
|   |   |   \-- README.md
|   |   +-- reports/
|   |   |   \-- README.md
|   |   +-- security/
|   |   |   \-- README.md
|   |   +-- sensitivity/
|   |   |   \-- README.md
|   |   +-- user-study/
|   |   |   \-- README.md
|   |   +-- protocol.json
|   |   \-- road-sample.md
|   +-- acceptance.json
|   +-- beta-decision.md
|   +-- dependencies.md
|   +-- limits.json
|   \-- providers.json
+-- scripts/
|   +-- benchmark_routing.py
|   +-- benchmark_system.py
|   +-- check_bootstrap.mjs
|   +-- check_deployment.py
|   +-- check.py
|   +-- dev.mjs
|   +-- generate_client.py
|   +-- probe_document_tools.py
|   +-- verify_recovery.py
|   +-- verify_release.py
|   \-- verify_security.py
+-- services/
|   +-- api/
|   |   +-- __init__.py
|   |   +-- accounts.py
|   |   +-- artifacts.py
|   |   +-- Dockerfile
|   |   +-- documents.py
|   |   +-- geography.py
|   |   +-- jobs.py
|   |   +-- limits.py
|   |   +-- proposals.py
|   |   +-- reports.py
|   |   +-- review.py
|   |   +-- runs.py
|   |   +-- scenarios.py
|   |   +-- sessions.py
|   |   \-- workspaces.py
|   +-- osm-import/
|   |   +-- __init__.py
|   |   \-- Dockerfile
|   \-- worker/
|       +-- handlers/
|       |   \-- __init__.py
|       +-- __init__.py
|       +-- dispatch.py
|       +-- Dockerfile
|       +-- leases.py
|       +-- purge.py
|       +-- reconcile.py
|       \-- usage.py
+-- tests/
|   +-- contracts/
|   |   +-- test_bootstrap.py
|   |   +-- test_extraction.py
|   |   +-- test_generated_client.py
|   |   +-- test_import_boundaries.py
|   |   +-- test_operational_inputs.py
|   |   +-- test_provider_configuration.py
|   |   +-- test_routing_decision.py
|   |   +-- test_run_manifest.py
|   |   +-- test_skeleton_contract.py
|   |   \-- test_validation_protocol.py
|   +-- e2e/
|   |   +-- accessibility.spec.ts
|   |   +-- community-twin.spec.ts
|   |   +-- evidence-review.spec.ts
|   |   +-- findings-comparison.spec.ts
|   |   +-- geography-review.spec.ts
|   |   +-- model-proof.spec.ts
|   |   +-- onboarding-lifecycle.spec.ts
|   |   +-- public-journeys.spec.ts
|   |   +-- report-downloads.spec.ts
|   |   +-- scenario-editor.spec.ts
|   |   +-- simulation-playback.spec.ts
|   |   \-- walking-skeleton.spec.ts
|   +-- engine/
|   |   +-- test_allocation.py
|   |   +-- test_checkpoint_resume.py
|   |   +-- test_comparisons.py
|   |   +-- test_event_boundaries.py
|   |   +-- test_findings.py
|   |   +-- test_held_out_validation.py
|   |   +-- test_knowledge_boundary.py
|   |   +-- test_population.py
|   |   +-- test_proposals.py
|   |   +-- test_reference_policy.py
|   |   +-- test_reference_routing.py
|   |   +-- test_replay.py
|   |   +-- test_reservations.py
|   |   +-- test_scenario_suites.py
|   |   +-- test_sensitivity.py
|   |   +-- test_trip_feasibility.py
|   |   \-- test_water.py
|   +-- fixtures/
|   |   +-- documents/
|   |   |   \-- README.md
|   |   +-- engine/
|   |   |   +-- boundaries/
|   |   |   |   \-- README.md
|   |   |   +-- resources/
|   |   |   |   \-- README.md
|   |   |   \-- water/
|   |   |       \-- README.md
|   |   +-- extraction/
|   |   |   \-- README.md
|   |   +-- geocoding/
|   |   |   \-- README.md
|   |   +-- inputs/
|   |   |   \-- README.md
|   |   +-- osm/
|   |   |   \-- README.md
|   |   +-- pdf-validation/
|   |   |   \-- README.md
|   |   +-- performance/
|   |   |   \-- README.md
|   |   +-- reports/
|   |   |   \-- README.md
|   |   +-- roads/
|   |   |   \-- README.md
|   |   +-- scenarios/
|   |   |   \-- README.md
|   |   +-- skeleton/
|   |   |   \-- README.md
|   |   \-- validation/
|   |       +-- sensitivity/
|   |       |   \-- README.md
|   |       \-- README.md
|   +-- integration/
|   |   +-- test_account_sessions.py
|   |   +-- test_artifact_access.py
|   |   +-- test_deletion_races.py
|   |   +-- test_evidence_readiness.py
|   |   +-- test_expiry_races.py
|   |   +-- test_graph_compilation.py
|   |   +-- test_job_submission.py
|   |   +-- test_mixed_credentials.py
|   |   +-- test_osm_import.py
|   |   +-- test_outbox_delivery.py
|   |   +-- test_owner_rls.py
|   |   +-- test_pdf_intake.py
|   |   +-- test_purge.py
|   |   +-- test_reports.py
|   |   +-- test_restore_tombstones.py
|   |   +-- test_runtime_configuration.py
|   |   +-- test_skeleton_api.py
|   |   +-- test_stage_recovery.py
|   |   +-- test_suite_jobs.py
|   |   +-- test_temporary_sessions.py
|   |   +-- test_temporary_streams.py
|   |   +-- test_usage_limits.py
|   |   +-- test_version_commands.py
|   |   +-- test_version_storage.py
|   |   \-- test_worker_fencing.py
|   \-- security/
|       \-- README.md
+-- .gitignore
+-- AGENTS.md
+-- compose.yaml
+-- package.json
+-- playwright.config.ts
+-- pnpm-lock.yaml
+-- pnpm-workspace.yaml
+-- pyproject.toml
\-- uv.lock
```
