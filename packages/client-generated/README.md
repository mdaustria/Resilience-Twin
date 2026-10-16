# Generated browser contracts

Run `pnpm generate:client` after changing Python contracts. `pnpm check` detects drift.

- `skeleton.ts` describes the existing local fixture API.
- `operational.ts` is generated from the Python `RunManifest` and referenced operational models. It declares no API operations: Task 2.2 does not enable a run endpoint or implement readiness/sealing UI.
- `private-commands.ts` is generated from the configured owner-checked review, scenario and proposal routers. These routes remain unmounted in the default app until Firestore/session/CSRF dependencies are configured.

Integer quantities are limited to JavaScript's safe-integer range. Ordered road geometry, routes and scenario events belong to separately pinned artifacts, not the unordered collections in these provisional v1 contracts. Run domain validation and manifest verification on the server; TypeScript declarations alone cannot enforce cross-record rules.
