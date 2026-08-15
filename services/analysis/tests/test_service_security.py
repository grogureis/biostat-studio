import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from biostat_service.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_is_available_on_loopback(client):
    response = client.get("/health")

    assert response.json() == {"status": "ok", "service": "biostat-analysis", "api": 1}


def test_v1_rejects_missing_token(client):
    response = client.get("/v1/session")

    assert response.status_code == 401


def test_v1_accepts_session_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200


def test_launcher_emits_only_port_and_api_readiness():
    process = subprocess.Popen(
        [sys.executable, "-m", "biostat_service.app", "--port", "0"],
        env={**os.environ, "BIOSTAT_SESSION_TOKEN": "test-token"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        readiness = json.loads(process.stdout.readline())
        assert readiness.keys() == {"port", "api"}
        assert isinstance(readiness["port"], int)
        assert readiness["port"] > 0
        assert readiness["api"] == 1
    finally:
        process.terminate()
        process.wait(timeout=5)
