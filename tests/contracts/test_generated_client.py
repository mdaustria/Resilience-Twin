"""Prove that Python schema changes require TypeScript regeneration."""

from copy import deepcopy
from typing import Any

import pytest

from scripts.generate_client import SCHEMAS, generate_clients
from services.api.main import create_app


def test_generated_clients_match_current_python_schemas() -> None:
    assert generate_clients(check=True) == 0


def test_python_contract_change_without_regeneration_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class ChangedApp:
        def openapi(self) -> dict[str, Any]:
            schema = deepcopy(create_app(local_fixture_mode=True).openapi())
            case = schema["components"]["schemas"]["SkeletonCase"]
            case["properties"]["new_contract_field"] = {"type": "string", "title": "New Contract Field"}
            case["required"].append("new_contract_field")
            return schema

    monkeypatch.setattr("scripts.generate_client.create_app", lambda **_kwargs: ChangedApp())
    with pytest.raises(SystemExit, match="Generated skeleton client differs"):
        generate_clients(check=True, schemas=(SCHEMAS[1],))
