"""Run the local and CI walking-skeleton gate with pinned tools."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {"uv": "0.13.0", "pnpm": "12.11.2", "node": "24.10.0"}
STEPS = (
    ("contract drift", "uv", "run", "python", "-m", "scripts.generate_client", "--check"),
    ("Python tests", "uv", "run", "pytest"),
    ("Python lint", "uv", "run", "ruff", "check", "."),
    ("Python types", "uv", "run", "mypy", "packages", "services"),
    ("web tests", "pnpm", "test"),
    ("web lint", "pnpm", "lint"),
    ("web types", "pnpm", "typecheck"),
    ("web build", "pnpm", "build"),
    ("browser smoke", "pnpm", "exec", "playwright", "test", "tests/e2e/walking-skeleton.spec.ts"),
)


def executable(name: str) -> str:
    command = "pnpm.cmd" if os.name == "nt" and name == "pnpm" else name
    found = shutil.which(command)
    if found is None:
        raise RuntimeError(f"Missing {name}; install the approved version in release/dependencies.md")
    return found


def verify_tools() -> None:
    if sys.version_info[:3] != (3, 13, 16):
        raise RuntimeError(
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} "
            "is active; install CPython 3.13.16 as recorded in release/dependencies.md"
        )
    for name, expected in TOOLS.items():
        reported = subprocess.run(
            [executable(name), "--version"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        actual = reported.split()[1] if name == "uv" else reported.removeprefix("v")
        if actual != expected:
            raise RuntimeError(
                f"{name} {actual} is active; install {expected} from release/dependencies.md"
            )


def main() -> int:
    try:
        verify_tools()
        for label, name, *args in STEPS:
            command = [executable(name), *args]
            print(f"> {label}: {name} {' '.join(args)}", flush=True)
            result = subprocess.run(command, cwd=ROOT, check=False)
            if result.returncode != 0:
                if label == "browser smoke":
                    print("Browser prerequisite: run pnpm exec playwright install chromium", file=sys.stderr)
                return result.returncode
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Check prerequisite failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
