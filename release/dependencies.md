# Dependency baseline — Tasks 1.1 and 1.3

The Task 1.1 runtime and bootstrap dependencies were approved by the user on 12 October 2026. The user separately approved `@playwright/test` 1.64.0 and its matching Chromium browser for Task 1.3 on the same date. Direct dependencies are pinned exactly in `pyproject.toml` and the two package manifests; transitive resolutions are pinned in `uv.lock` and `pnpm-lock.yaml`. Later geography, provider, and database packages remain unapproved.

| Runtime/tool | Exact version | Purpose |
| --- | --- | --- |
| CPython | 3.13.16 | API, schema generation, Python checks |
| uv | 0.13.0 | Python runtime and frozen dependency install |
| Node.js | 24.10.0 | Local web build and scripts |
| pnpm | 12.11.2 | Web workspace and frozen dependency install |

| Direct package | Exact version | Purpose |
| --- | --- | --- |
| FastAPI | 0.143.0 | Local HTTP API and OpenAPI schema |
| Pydantic | 2.14.1 | Typed bootstrap response and future contracts |
| Uvicorn | 0.53.0 | Local ASGI server |
| pytest | 9.1.1 | Python bootstrap tests |
| Ruff | 0.17.0 | Python lint |
| mypy | 2.4.0 | Python type checks |
| React, React DOM | 19.3.0 | Browser entry point |
| Vite | 8.3.4 | Local web server and build |
| TypeScript | 6.0.3 | Web type checks; held below 7 for parser compatibility |
| @types/react, @types/react-dom | 19.3.0 | React TypeScript declarations |
| ESLint | 10.10.0 | Web lint |
| typescript-eslint | 8.71.1 | TypeScript ESLint parser and recommended rules |
| openapi-typescript | 7.13.0 | Generate browser types from FastAPI OpenAPI |
| @playwright/test | 1.64.0 | Browser smoke test runner and assertions against the local web/API/engine path |

Compatibility evidence: [uv lists CPython 3.13 as Tier 1](https://docs.astral.sh/uv/reference/policies/python/); [Node 24 is an LTS release](https://nodejs.org/en/about/previous-releases); [Vite 8 accepts Node 22.12+ and newer](https://vite.dev/blog/announcing-vite8.html); [pnpm 12 supports Node 24 and Windows x64](https://pnpm.io/installation/). The [openapi-typescript package](https://www.npmjs.com/package/openapi-typescript) supports OpenAPI 3.0/3.1 and Node 20+. A [typescript-eslint compatibility report](https://github.com/typescript-eslint/typescript-eslint/issues/12518) documents TypeScript 7 outside the earlier 8.x peer range, so Task 1.1 pins TypeScript 6.0.3 and confirms resolution with a real install and lint run. [Playwright's package metadata](https://registry.npmjs.org/@playwright/test/1.64.0) requires Node 20+, and its [installation guide](https://playwright.dev/docs/intro) supports Node 24.x and Windows 11+. Exact package releases are recorded by their [PyPI](https://pypi.org/) and [npm](https://www.npmjs.com/) release pages and the lockfiles.

The approved tools were downloaded into ignored `.runtime/` for this local verification because the preexisting PATH held Node 22.18.0, a pnpm 11.25.0 wrapper, Python 3.9.1, and no uv. To use these workspace-local tools in PowerShell, set the following variables from the repository root before running the guide's commands:

```powershell
$env:PATH = (Resolve-Path '.runtime/node-v24.10.0-win-x64').Path + ';' + (Resolve-Path '.runtime/pnpm/node_modules/.bin').Path + ';' + (Resolve-Path '.runtime/uv').Path + ';' + $env:PATH
$env:UV_PYTHON_INSTALL_DIR = (Resolve-Path '.runtime/python').Path
$env:UV_CACHE_DIR = (Resolve-Path '.runtime').Path + '\uv-cache'
$env:PNPM_HOME = (Resolve-Path '.runtime').Path + '\pnpm-home'
$env:TEMP = (Resolve-Path '.runtime/tmp').Path
$env:TMP = $env:TEMP
$env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path '.runtime').Path + '\playwright-browsers'
```

On a fresh machine, install the exact approved runtime/tool versions first, then run `uv sync --frozen` and `pnpm install --frozen-lockfile`. Run `pnpm exec playwright install chromium` to install Playwright's matching browser before `pnpm exec playwright test tests/e2e/walking-skeleton.spec.ts`. Task 1.3 downloaded Chrome for Testing 156.0.8078.4 (Playwright Chromium revision 1248), matching headless shell revision 1248, into ignored `.runtime/playwright-browsers/`. Run `pnpm generate:client` only after an intentional Python schema change, and use `pnpm check:bootstrap` to reject generated-client drift. The later PDF validator/scanner, geospatial native stack, routing candidate, database drivers, and provider SDK remain unselected or unapproved.

Task 1.4's GitHub workflow uses these exact setup actions, separately approved by the user on 12 October 2026. They install the already approved runtime and package versions above on `ubuntu-24.04` before `pnpm check`:

| CI action | Exact release | Purpose |
| --- | --- | --- |
| [actions/checkout](https://github.com/actions/checkout/releases/tag/v7.0.1) | v7.0.1 | Fetch the repository for checks |
| [actions/setup-node](https://github.com/actions/setup-node/releases/tag/v7.1.0) | v7.1.0 | Install Node 24.10.0 |
| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv/releases/tag/v10.2.0) | v10.2.0 | Install uv 0.13.0; uv installs Python 3.13.16 |

The repository currently has no Git remote, so a hosted CI run has not been observed. The local combined check covers the same application commands but does not prove the GitHub runner configuration.
