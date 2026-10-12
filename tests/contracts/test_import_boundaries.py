"""Keep the local vertical slice's Python dependencies pointing inward."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = (
    "packages/contracts",
    "packages/domain",
    "packages/simulation",
    "packages/application",
    "packages/adapters",
    "packages/reports",
    "services/api",
)
FORBIDDEN = {
    "packages/contracts": ("packages.application", "packages.adapters", "packages.simulation", "services", "apps"),
    "packages/domain": ("packages.application", "packages.adapters", "packages.simulation", "services", "apps"),
    "packages/simulation": ("packages.application", "packages.adapters", "services", "apps", "fastapi", "sqlalchemy", "google", "datetime", "time"),
    "packages/application": ("packages.adapters", "services", "apps"),
    "packages/adapters": ("services", "apps"),
    "packages/reports": ("services", "apps"),
    "services/api": ("packages.simulation",),
}


def imported_modules(path: Path, source: str) -> list[str]:
    modules: list[str] = []
    package_parts = path.parent.parts
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                modules.append(".".join((*base, *(node.module or "").split("."))).rstrip("."))
            elif node.module:
                modules.append(node.module)
    return modules


def violations(path: Path, source: str) -> list[str]:
    section = next((name for name in SCANNED if path.as_posix().startswith(f"{name}/")), None)
    if section is None:
        return []
    return [
        module
        for module in imported_modules(path, source)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN[section])
    ]


def test_python_import_boundaries() -> None:
    found = []
    for section in SCANNED:
        for file in sorted((ROOT / section).rglob("*.py")):
            relative = file.relative_to(ROOT)
            for module in violations(relative, file.read_text(encoding="utf-8")):
                found.append(f"{relative}: {module}")
    assert not found, "Forbidden inward dependency:\n" + "\n".join(found)


def test_boundary_checker_catches_direct_and_relative_imports() -> None:
    path = Path("packages/simulation/kernel/runner.py")
    assert violations(path, "from services.api.main import app\nfrom ...adapters.local import fixtures\n") == [
        "services.api.main",
        "packages.adapters.local",
    ]
