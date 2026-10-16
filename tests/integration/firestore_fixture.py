"""Required Firestore emulator lifecycle for Task 4.1 tests."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import Client

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "demo-resilience-twin"
with socket.socket() as _port_reservation:
    _port_reservation.bind(("127.0.0.1", 0))
    HOST = f"127.0.0.1:{_port_reservation.getsockname()[1]}"


@pytest.fixture(scope="session")
def firestore_client() -> Iterator[Client]:
    pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
    if pnpm is None:
        pytest.fail("Firestore emulator prerequisite missing: approved pnpm not on PATH")
    environment = dict(os.environ)
    local_jdk = ROOT / ".runtime" / "jdk-21.0.12.1+1"
    if local_jdk.exists():
        environment["JAVA_HOME"] = str(local_jdk)
        environment["PATH"] = str(local_jdk / "bin") + os.pathsep + environment["PATH"]
    environment["FIRESTORE_EMULATOR_HOST"] = HOST
    port = int(HOST.split(":")[1])
    log_path = ROOT / ".runtime" / "tmp" / f"firestore-emulator-{port}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = log_path.parent / f"firebase-test-{port}.json"
    config_path.write_text(json.dumps({
        "firestore": {
            "rules": str(ROOT / "firestore.rules"),
            "indexes": str(ROOT / "firestore.indexes.json"),
        },
        "emulators": {
            "firestore": {"host": "127.0.0.1", "port": port},
            "ui": {"enabled": False},
            "singleProjectMode": True,
        },
    }), encoding="utf-8")
    config_home = ROOT / ".runtime" / "firebase-config"
    config_home.mkdir(parents=True, exist_ok=True)
    environment["XDG_CONFIG_HOME"] = str(config_home)
    environment["NO_UPDATE_NOTIFIER"] = "1"
    with log_path.open("w", encoding="utf-8") as log:
        emulator = subprocess.Popen(
            [pnpm, "exec", "firebase", "emulators:start", "--only", "firestore",
             "--project", PROJECT, "--config", str(config_path)],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(180):
                if emulator.poll() is not None:
                    pytest.fail(f"Firestore emulator exited; inspect {log_path}")
                try:
                    with urlopen(f"http://{HOST}/", timeout=1):
                        break
                except (URLError, TimeoutError):
                    time.sleep(1)
            else:
                pytest.fail(f"Firestore emulator unavailable; inspect {log_path}")
            clear_url = (
                f"http://{HOST}/emulator/v1/projects/{PROJECT}/databases/"
                "(default)/documents"
            )
            with urlopen(Request(clear_url, method="DELETE"), timeout=10):
                pass
            previous = os.environ.get("FIRESTORE_EMULATOR_HOST")
            os.environ["FIRESTORE_EMULATOR_HOST"] = HOST
            try:
                client = firestore.Client(project=PROJECT)
                yield client
                client.close()
            finally:
                if previous is None:
                    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
                else:
                    os.environ["FIRESTORE_EMULATOR_HOST"] = previous
        finally:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(emulator.pid), "/T", "/F"],
                               capture_output=True, check=False)
            else:
                emulator.terminate()
            try:
                emulator.wait(timeout=10)
            except subprocess.TimeoutExpired:
                emulator.kill()
                emulator.wait(timeout=5)
