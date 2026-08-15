import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from biostat_service.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_is_available_on_loopback(client):
    response = client.get("/health")

    assert response.json() == {"status": "ok", "service": "biostat-analysis", "api": 1}


def test_create_app_rejects_missing_session_token(monkeypatch):
    monkeypatch.delenv("BIOSTAT_SESSION_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BIOSTAT_SESSION_TOKEN must be set"):
        create_app()


def test_create_app_rejects_empty_session_token(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "")

    with pytest.raises(RuntimeError, match="BIOSTAT_SESSION_TOKEN must be set"):
        create_app()


def test_v1_rejects_missing_token(client):
    response = client.get("/v1/session")

    assert response.status_code == 401


def test_v1_rejects_raw_unprefixed_token(client):
    response = client.get("/v1/session", headers={"Authorization": "test-token"})

    assert response.status_code == 401


@pytest.mark.parametrize("authorization", ["Bearer", "Basic test-token", "BearerX test-token"])
def test_v1_rejects_malformed_authorization_scheme(client, authorization):
    response = client.get("/v1/session", headers={"Authorization": authorization})

    assert response.status_code == 401


def test_v1_rejects_wrong_bearer_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401


def test_v1_accepts_session_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200


def test_authenticated_project_plan_job_and_report_routes_keep_values_out_of_responses(
    client, tmp_path: Path
):
    """The entire local workflow publishes metadata/results, never raw workbook values."""
    workbook_path = tmp_path / "study.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["group", "outcome"])
    for index in range(12):
        sheet.append(["control" if index < 6 else "treated", 100 + index])
    workbook.save(workbook_path)
    brief = {
        "title": "Treatment comparison",
        "question": "Does treatment change the measured outcome?",
        "hypothesis": "Treatment is associated with a different outcome.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
        "language": "en",
    }
    headers = {"Authorization": "Bearer test-token"}

    created = client.post(
        "/v1/projects",
        headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(tmp_path / "study.biostat"), "brief": brief},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["profile"]["rows"] == 12
    assert "control" not in created.text
    assert str(workbook_path) not in created.text

    planned = client.post("/v1/plans", headers=headers, json={"project_id": payload["id"]})
    assert planned.status_code == 200
    assert planned.json()["blocking_errors"] == []

    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={"project_id": payload["id"], "approved_plan_version": planned.json()["version"]},
    )
    assert queued.status_code == 200
    job_id = queued.json()["id"]
    for _ in range(100):
        status = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert status.status_code == 200
        if status.json()["status"] in {"completed", "failed", "cancelled"}:
            break
    assert status.json()["status"] == "completed"
    assert status.json()["result"]["results"]
    assert "control" not in status.text

    audit_text = (tmp_path / "study.biostat" / "audit.jsonl").read_text(encoding="utf-8")
    assert '"type": "analysis_completed"' in audit_text
    assert '"data_fingerprint"' in audit_text
    assert "control" not in audit_text

    destination = tmp_path / "results.docx"
    exported = client.post(
        "/v1/reports",
        headers=headers,
        json={"project_id": payload["id"], "job_id": job_id, "language": "en", "destination": str(destination)},
    )
    assert exported.status_code == 200
    assert exported.json() == {"saved": True, "filename": "results.docx"}
    assert destination.exists()


def test_v1_rejects_non_loopback_client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app(), client=("192.0.2.1", 5000)) as remote_client:
        response = remote_client.get(
            "/v1/session", headers={"Authorization": "Bearer test-token"}
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "loopback_only"}


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
