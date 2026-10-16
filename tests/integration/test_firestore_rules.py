"""Direct Firebase REST clients are denied by emulator and cloud rules."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from google.cloud.firestore_v1 import Client

from tests.integration.firestore_fixture import HOST, PROJECT


def test_direct_client_cannot_read_or_write_private_data(firestore_client: Client) -> None:
    firestore_client.document("workspaces/task41_rules").set({"private": True})
    url = (
        f"http://{HOST}/v1/projects/{PROJECT}/databases/(default)"
        "/documents/workspaces/task41_rules"
    )
    for method, data in (("GET", None), ("PATCH", b'{"fields":{"private":{"booleanValue":false}}}')):
        request = Request(url, data=data, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=5) as response:
                assert response.status in (401, 403)
        except HTTPError as error:
            assert error.code in (401, 403)
    assert firestore_client.document("workspaces/task41_rules").get().to_dict()["private"]


def test_unauthenticated_client_denied_by_named_cloud_rules() -> None:
    project = os.getenv("RT_FIRESTORE_SMOKE_PROJECT")
    database = os.getenv("RT_FIRESTORE_SMOKE_DATABASE")
    if not project or not database or os.getenv("RT_FIRESTORE_SMOKE_APPROVED") != "1":
        pytest.fail("Cloud rules probe needs an approved project and explicit database")
    url = (f"https://firestore.googleapis.com/v1/projects/{project}/databases/"
           f"{database}/documents/workspaces/rt41_rules_{uuid4().hex}")
    for method, body in (("GET", None),
                         ("PATCH", b'{"fields":{"probe":{"booleanValue":true}}}')):
        target = f"{url}?currentDocument.exists=true" if method == "PATCH" else url
        request = Request(target, data=body, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30):
                pytest.fail(f"Unauthenticated {method} unexpectedly succeeded")
        except HTTPError as error:
            payload = json.loads(error.read())
            assert error.code == 403
            assert payload["error"]["status"] == "PERMISSION_DENIED"
