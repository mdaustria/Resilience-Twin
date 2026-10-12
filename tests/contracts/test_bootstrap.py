"""Verify the local API bootstrap and its published schema."""

from services.api.main import app, bootstrap_status


def test_bootstrap_status() -> None:
    status = bootstrap_status()
    assert status.status == "ready"
    assert status.schema_version == "bootstrap.v1"


def test_openapi_exposes_typed_bootstrap_response() -> None:
    schema = app.openapi()
    response = schema["paths"]["/api/v1/bootstrap"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/BootstrapStatus"
    )
    properties = schema["components"]["schemas"]["BootstrapStatus"]["properties"]
    assert set(properties) == {"status", "schema_version"}
