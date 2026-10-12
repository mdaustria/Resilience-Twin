"""Generate TypeScript contracts from production-safe and local fixture API schemas."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = (
    ("bootstrap", ROOT / "apps/web/src/generated/bootstrap.ts", False),
    ("skeleton", ROOT / "packages/client-generated/skeleton.ts", True),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated output differs")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        for name, output, local_fixture_mode in SCHEMAS:
            source = Path(directory) / f"{name}-openapi.json"
            result = Path(directory) / f"{name}.ts"
            source.write_text(
                json.dumps(
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
            if args.check:
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


if __name__ == "__main__":
    raise SystemExit(main())
