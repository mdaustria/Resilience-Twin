# Dependency baseline — Task 1.1

Approved by the user on 12 October 2026 for the local walking skeleton. Direct dependencies are pinned exactly in `pyproject.toml` and the two package manifests; transitive resolutions are pinned in `uv.lock` and `pnpm-lock.yaml`. This is a bootstrap selection, not approval for later geography, provider, database, or browser-test packages.

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

Compatibility evidence: [uv lists CPython 3.13 as Tier 1](https://docs.astral.sh/uv/reference/policies/python/); [Node 24 is an LTS release](https://nodejs.org/en/about/previous-releases); [Vite 8 accepts Node 22.12+ and newer](https://vite.dev/blog/announcing-vite8.html); [pnpm 12 supports Node 24 and Windows x64](https://pnpm.io/installation/). The [openapi-typescript package](https://www.npmjs.com/package/openapi-typescript) supports OpenAPI 3.0/3.1 and Node 20+. A [typescript-eslint compatibility report](https://github.com/typescript-eslint/typescript-eslint/issues/12518) documents TypeScript 7 outside the earlier 8.x peer range, so Task 1.1 pins TypeScript 6.0.3 and confirms resolution with a real install and lint run. Exact package releases are recorded by their [PyPI](https://pypi.org/) and [npm](https://www.npmjs.com/) release pages and the lockfiles.

The approved tools were downloaded into ignored `.runtime/` for this local verification because the preexisting PATH held Node 22.18.0, a pnpm 11.25.0 wrapper, Python 3.9.1, and no uv. To use these workspace-local tools in PowerShell, set the following variables from the repository root before running the guide's commands:

```powershell
$env:PATH = (Resolve-Path '.runtime/node-v24.10.0-win-x64').Path + ';' + (Resolve-Path '.runtime/pnpm/node_modules/.bin').Path + ';' + (Resolve-Path '.runtime/uv').Path + ';' + $env:PATH
$env:UV_PYTHON_INSTALL_DIR = (Resolve-Path '.runtime/python').Path
$env:UV_CACHE_DIR = (Resolve-Path '.runtime').Path + '\uv-cache'
$env:PNPM_HOME = (Resolve-Path '.runtime').Path + '\pnpm-home'
$env:TEMP = (Resolve-Path '.runtime/tmp').Path
$env:TMP = $env:TEMP
```

On a fresh machine, install the exact approved runtime/tool versions first, then run `uv sync --frozen` and `pnpm install --frozen-lockfile`. Run `pnpm generate:client` only after an intentional Python schema change, and use `pnpm check:bootstrap` to reject generated-client drift. The later PDF validator/scanner, geospatial native stack, routing candidate, browser-test runner, database drivers, and provider SDK remain unselected or unapproved.
