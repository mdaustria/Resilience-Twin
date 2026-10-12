"""Real local HTTP checks for the development-only synthetic fixture endpoint."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from services.api.main import create_app, local_fixture_enabled

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def base_url() -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = dict(os.environ)
    environment["RESILIENCE_TWIN_ENV"] = "development"
    environment["RESILIENCE_TWIN_LOCAL_FIXTURES"] = "1"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            if server.poll() is not None:
                raise RuntimeError("Local fixture API exited before becoming ready")
            try:
                with urlopen(f"{url}/api/v1/bootstrap", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Local fixture API did not become ready")
        yield url
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def request(
    base_url: str,
    method: str,
    path: str,
    owner: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if owner is not None:
        headers["X-Fixture-Owner"] = owner
    data = json.dumps(payload).encode() if payload is not None else None
    request_object = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request_object, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_synthetic_get_then_run_through_api_application_and_engine(base_url: str) -> None:
    status, case = request(base_url, "GET", "/api/v1/local/cases/one-trip-water", "fixture-a")
    assert status == 200
    assert case["source_label"] == "Synthetic training fixture; no source plan"
    status, result = request(
        base_url, "POST", "/api/v1/local/cases/one-trip-water/run", "fixture-a", case
    )
    assert status == 200
    assert result["arrived_people"] == 6
    assert result["unserved_people"] == 4
    assert result["water_shortfall_ml"] == 2000
    assert result["water_sufficient_people"] == 4


def test_missing_input_and_nonfixture_submission_fail(base_url: str) -> None:
    _, case = request(base_url, "GET", "/api/v1/local/cases/one-trip-water", "fixture-a")
    missing = dict(case)
    del missing["shelter_water_ml"]
    status, detail = request(
        base_url, "POST", "/api/v1/local/cases/one-trip-water/run", "fixture-a", missing
    )
    assert status == 422
    assert any("shelter_water_ml" in str(item["loc"]) for item in detail["detail"])
    changed = dict(case, cohort_people=1000000)
    status, _ = request(
        base_url, "POST", "/api/v1/local/cases/one-trip-water/run", "fixture-a", changed
    )
    assert status == 409


def test_fixture_owners_are_isolated(base_url: str) -> None:
    status, _ = request(base_url, "GET", "/api/v1/local/cases/private-case", "fixture-b")
    assert status == 200
    status, _ = request(base_url, "GET", "/api/v1/local/cases/private-case", "fixture-a")
    assert status == 404


def test_fixture_routes_are_absent_outside_development(monkeypatch: Any) -> None:
    monkeypatch.setenv("RESILIENCE_TWIN_ENV", "production")
    monkeypatch.setenv("RESILIENCE_TWIN_LOCAL_FIXTURES", "1")
    assert not local_fixture_enabled()
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/local/cases/{case_id}" not in paths
    monkeypatch.setenv("RESILIENCE_TWIN_ENV", "development")
    monkeypatch.setenv("RESILIENCE_TWIN_LOCAL_FIXTURES", "0")
    assert not local_fixture_enabled()
    monkeypatch.setenv("RESILIENCE_TWIN_LOCAL_FIXTURES", "1")
    assert local_fixture_enabled()
