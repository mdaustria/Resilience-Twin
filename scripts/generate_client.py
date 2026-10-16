"""Generate TypeScript contracts from production-safe and local fixture API schemas."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from packages.adapters.persistence.firestore import Actor
from packages.adapters.persistence.runs import FirestoreRuns
from packages.adapters.persistence.sessions import FirestoreTemporarySessions
from packages.application.deletion import DeleteWorkspace
from packages.application.documents import PrivateDocuments
from packages.application.jobs import JobSubmission
from packages.application.usage import UsagePolicy
from packages.application.versions import DurableVersions
from packages.contracts.run_manifest import RunManifest
from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = (
    ("bootstrap", ROOT / "apps/web/src/generated/bootstrap.ts", False),
    ("skeleton", ROOT / "packages/client-generated/skeleton.ts", True),
    ("operational", ROOT / "packages/client-generated/operational.ts", False),
    ("private-commands", ROOT / "packages/client-generated/private-commands.ts", False),
)


def operational_openapi() -> dict[str, object]:
    """Export standalone contracts without advertising an unimplemented API operation."""
    root = RunManifest.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = root.pop("$defs", {})
    definitions["RunManifest"] = root
    return {
        "openapi": "3.1.0",
        "info": {"title": "Provisional operational contracts", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": definitions},
    }


def private_commands_openapi() -> dict[str, object]:
    return create_app(
        local_fixture_mode=False,
        temporary_sessions=FirestoreTemporarySessions(None),
        private_documents=PrivateDocuments(cast(Any, None), cast(Any, None),
                                           cast(Any, None), cast(Any, None),
                                           secret=b"schema-only-upload-secret-32-bytes"),
        durable_versions=DurableVersions(None),
        job_submission=JobSubmission(None),
        durable_runs=FirestoreRuns(None),
        workspace_deletion=DeleteWorkspace(None),
        usage_policy=UsagePolicy(1, 1, 1, 1, 1, 1, 1),
        private_owner_for=lambda _handle, _workspace: (Actor("temporary", "schema"), None),
        session_origin="https://schema.invalid",
        session_csrf_key=b"schema-only-secret-32-bytes-at-least",
    ).openapi()


def generate_clients(*, check: bool, schemas: tuple[tuple[str, Path, bool], ...] = SCHEMAS) -> int:
    with tempfile.TemporaryDirectory() as directory:
        for name, output, local_fixture_mode in schemas:
            source = Path(directory) / f"{name}-openapi.json"
            result = Path(directory) / f"{name}.ts"
            source.write_text(
                json.dumps(
                    operational_openapi() if name == "operational" else
                    private_commands_openapi() if name == "private-commands" else
                    create_app(local_fixture_mode=local_fixture_mode).openapi(),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "pnpm.cmd" if os.name == "nt" else "pnpm",
                    "exec",
                    "openapi-typescript",
                    str(source),
                    "--output",
                    str(result),
                ],
                cwd=ROOT,
                check=True,
            )
            generated = result.read_text(encoding="utf-8")
            if check:
                if not output.exists() or output.read_text(encoding="utf-8") != generated:
                    raise SystemExit(
                        f"Generated {name} client differs; run pnpm generate:client"
                    )
                print(f"{name} client matches the Python OpenAPI schema.")
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(generated, encoding="utf-8")
                print(f"Generated {output.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated output differs")
    args = parser.parse_args()
    return generate_clients(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
