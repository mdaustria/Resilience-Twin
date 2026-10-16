# Dependency baseline — Tasks 1.1 and 1.3

The Task 1.1 runtime and bootstrap dependencies were approved by the user on 12 October 2026. The user separately approved `@playwright/test` 1.64.0 and its matching Chromium browser for Task 1.3 on the same date. Direct dependencies are pinned exactly in `pyproject.toml` and the two package manifests; transitive resolutions are pinned in `uv.lock` and `pnpm-lock.yaml`. Task 3.1 provider/PDF additions approved on 13 October are listed below; later geography and database packages remain unapproved.

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

On a fresh machine, install the exact approved runtime/tool versions first, then run `uv sync --frozen` and `pnpm install --frozen-lockfile`. Run `pnpm exec playwright install chromium` to install Playwright's matching browser before `pnpm exec playwright test tests/e2e/walking-skeleton.spec.ts`. Task 1.3 downloaded Chrome for Testing 156.0.8078.4 (Playwright Chromium revision 1248), matching headless shell revision 1248, into ignored `.runtime/playwright-browsers/`. Run `pnpm generate:client` only after an intentional Python schema change, and use `pnpm check:bootstrap` to reject generated-client drift. The Task 3.1 choices below supersede the earlier PDF/provider dependency gap; geospatial native libraries and database drivers remain unselected or unapproved.

Task 1.4's GitHub workflow uses these exact setup actions, separately approved by the user on 12 October 2026. They install the already approved runtime and package versions above on `ubuntu-24.04` before `pnpm check`:

| CI action | Exact release | Purpose |
| --- | --- | --- |
| [actions/checkout](https://github.com/actions/checkout/releases/tag/v7.0.1) | v7.0.1 | Fetch the repository for checks |
| [actions/setup-node](https://github.com/actions/setup-node/releases/tag/v7.1.0) | v7.1.0 | Install Node 24.10.0 |
| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv/releases/tag/v10.2.0) | v10.2.0 | Install uv 0.13.0; uv installs Python 3.13.16 |

The repository is connected to [GitHub](https://github.com/mdaustria/Resilience-Twin). The [Task 1.4 workflow run](https://github.com/mdaustria/Resilience-Twin/actions/runs/38223437566) passed on commit `5b9b90951d096aecf3c2581c56ea03e42e026379` on `ubuntu-24.04`, validating the frozen install and combined check in the hosted runner.

## Task 2.4 evaluation dependency (13 October 2026)

The user approved `pyvalhalla==3.9.1` and a small public OSM sample for the
local routing reuse evaluation. It is pinned in the development group of
`pyproject.toml` and `uv.lock`; it is **not** a production router.
The [3.9.1 PyPI release](https://pypi.org/project/pyvalhalla/3.9.1/) is MIT
licensed and publishes a Windows x64 `cp312-abi3` wheel and Linux x64/aarch64
`manylinux_2_28` wheels. Those ABI tags support this repository's CPython
3.13.16 and Linux CI runtime; the Windows wheel was actually installed and
used to build tiles and route the pinned sample. Linux CI import/build remains
to be verified. The wheel bundles local graph-building executables, so this
evaluation did not require Docker or a server. `uv add --dev` resolved 28
packages and added only `pyvalhalla` to the existing environment. See
[`routing/README.md`](routing/README.md) for the exact sample, measurements,
and measured semantics. [ADR-028](routing/ADR-028.md) selects the
standard-library exact-edge implementation as the sole production router for
Task 3.6 integration. No new production routing runtime dependency is approved.

## Task 3.1 document/provider dependency decision (13 October 2026)

The user explicitly approved the three exact additions on 13 October 2026:

| Tool | Exact version | Purpose and compatibility evidence |
| --- | --- | --- |
| [google-genai](https://pypi.org/project/google-genai/2.29.0/) | 2.29.0 | Backend Gemini Developer API SDK. PyPI requires Python 3.10+ and distributes a universal Python wheel; installed with the pinned CPython 3.13.16 runtime. Exact model/API selection remains gated in `release/providers.json`. |
| [pypdf](https://pypi.org/project/pypdf/6.20.1/) | 6.20.1 | Strict PDF structure/page/encryption checks and bounded active-entry selection probe. BSD-3-Clause; PyPI requires Python 3.9+ and distributes a universal wheel; installed with pinned CPython 3.13.16. It is not a malware scanner. |
| [ClamAV](https://github.com/Cisco-Talos/clamav/releases/tag/clamav-1.5.4) | 1.5.4 | Separate malware scanning runtime. Official Windows x64 and Linux x64 assets exist; Windows archive verified against the published digest via the official asset API. Fresh signatures and clean/custom-signature detection passed locally on Windows and in Ubuntu 24.04 CI; production packaging remains open. |

`uv add` resolved and installed both Python packages and their transitive
dependencies after approval, updating `pyproject.toml` and `uv.lock`. The
ClamAV executable is kept only in ignored `.runtime`; no full PDF/provider
acceptance gate is claimed from package metadata or a local scan alone. See `docs/document-processing.md` and
`scripts/probe_document_tools.py` for configuration and fixture evidence.

The Task 3.1 Linux CI step now names the official `clamav-1.5.4.linux.x86_64.deb`
archive and verifies its published SHA-256
`28d6efc5b4423e7830c3559339552eb53870a9eac51ac4efb37d60530d329886`
before installation. [ClamAV's Linux package guidance](https://docs.clamav.net/manual/Installing.html)
states that its Debian build has external libraries statically compiled and
targets glibc 2.27 or newer; the approved `ubuntu-24.04` runner meets that
minimum. The workflow updates signatures and requires both clean and benign
detection paths. [Run 38518985622](https://github.com/mdaustria/Resilience-Twin/actions/runs/38518985622)
passed on 14 October 2026 for commit `88ac5431f7da3bd252c343593dd63d487fd8a5a7`
on the isolated scanner branch. Its Ubuntu 24.04 log records ClamAV 1.5.4,
`scanner_status=verified`, clean exit 0 and benign custom-signature detection
exit 1; the frozen installs and branch combined check also passed. This verifies
the hosted Linux scanner path, not production image packaging.

## Task 4.1 Firestore dependency approval (14 October 2026)

The user approved these exact additions on 14 October 2026:

| Package/tool | Exact version | Purpose and compatibility |
| --- | --- | --- |
| [firebase-admin](https://pypi.org/project/firebase-admin/7.7.0/) | 7.7.0 | Python server SDK for Firestore owner-scoped transactions; PyPI publishes a universal wheel and Python 3.13 support. Locked `google-cloud-firestore==2.34.1` is transitive. Server calls bypass client Security Rules. |
| [firebase-tools](https://github.com/firebase/firebase-tools/releases/tag/v15.30.1) | 15.30.1 | Firestore emulator/rules CLI, pinned as a root development dependency under Node 24.10.0. The exact install and emulator test ran locally. Its transitive `protobufjs==7.6.6` postinstall was inspected; it checks a dependent version scheme and is the only newly allowlisted build in `pnpm-workspace.yaml`. |
| [Eclipse Temurin JDK](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1) | 21.0.12.1+1 | Local and CI Firestore emulator runtime. The local Windows x64 archive matched the publisher SHA-256 `f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e`. CI fetches the same version's Linux x64 archive and checks its publisher digest. Firebase documents a forthcoming Java 21 requirement for the Firestore emulator. |

The approved JDK is unpacked only under ignored `.runtime/` locally.
The user approved browser `firebase@12.19.0` for the earlier account design on
15 October 2026. ADR-031 removes end-user sign-in from this release; Task 4.3
removed the unused browser SDK and its `@firebase/util` build allowance from
the frozen manifest. The server `firebase-admin` package remains required for
Firestore and Storage service operations. No web Auth configuration is needed.

Task 4.7 queue client approved by the user on 15 October 2026:

| Package | Exact version | Purpose and compatibility |
| --- | --- | --- |
| [google-cloud-tasks](https://pypi.org/project/google-cloud-tasks/2.26.0/) | 2.26.0 | Python Cloud Tasks HTTP queue client for durable outbox dispatch. Its published package supports Python 3.13; `uv add` resolved it with approved Python 3.13.16 and locked transitive `grpc-google-iam-v1==0.14.5`. |

The queue adapter is local and injected in tests. No live queue, worker service account or dispatch permission is configured yet.
