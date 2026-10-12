"""Generate the bootstrap TypeScript contract from the local FastAPI OpenAPI schema."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from services.api.main import app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/web/src/generated/bootstrap.ts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated output differs")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "bootstrap-openapi.json"
        result = Path(directory) / "bootstrap.ts"
        source.write_text(json.dumps(app.openapi(), sort_keys=True), encoding="utf-8")
        subprocess.run(
            ["pnpm.cmd" if os.name == "nt" else "pnpm", "exec", "openapi-typescript", str(source), "--output", str(result)],
            cwd=ROOT,
            check=True,
        )
        generated = result.read_text(encoding="utf-8")

    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != generated:
            raise SystemExit("Generated bootstrap client differs; run pnpm generate:client")
        print("Bootstrap client matches the Python OpenAPI schema.")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated, encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
