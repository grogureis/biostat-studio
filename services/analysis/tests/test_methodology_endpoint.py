"""Behavioral coverage for the methodology extraction endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biostat_service.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_extracts_design_from_a_text_document(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "m.txt"
    path.write_text("Yöntem\nRetrospektif kohort çalışması.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_format"] == "txt"
    assert len(body["source_sha256"]) == 64
    assert body["truncated"] is False
    assert body["warnings"] == []
    assert body["brief"]["design"]["value"] == "cohort"
    assert body["brief"]["design"]["source"] == "rule"
    assert body["brief"]["design"]["evidence"]


def test_rejects_unsupported_format_with_a_stable_code(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "m.rtf"
    path.write_text("x", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "methodology_intake_failed:unsupported_format"


def test_response_never_echoes_the_source_path(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "patient-cohort-2026.txt"
    path.write_text("Yöntem\nKesitsel çalışma.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    # A 4xx body would trivially contain neither string, so pin the success
    # path: this must be a real payload that still keeps the path out.
    assert response.status_code == 200
    assert response.json()["brief"]["design"]["value"] == "cross_sectional"
    assert "patient-cohort-2026" not in response.text
    assert str(tmp_path) not in response.text


def test_missing_method_section_is_reported_in_the_response_warnings(
    client: TestClient, tmp_path: Path
) -> None:
    """The brief's own warnings reach the caller, not just the document's."""
    path = tmp_path / "no-section.txt"
    path.write_text(
        "Giriş\nHastalar retrospektif kohort olarak izlendi.", encoding="utf-8"
    )

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert "no_method_section" in body["warnings"]
    assert body["brief"]["design"]["value"] == "cohort"
