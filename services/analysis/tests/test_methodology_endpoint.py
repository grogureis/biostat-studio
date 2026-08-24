"""Behavioral coverage for the methodology extraction endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from biostat_service.app import _proposal_payload, create_app
from biostat_service.extractors.contracts import EVIDENCE_MAX_CHARS, Proposal
from biostat_service.methodology_intake import MAX_DOCUMENT_CHARS


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _create_project(client: TestClient, tmp_path: Path) -> str:
    """Create a minimal project over HTTP and return its id.

    Mirrors the inline /v1/projects setup repeated throughout
    test_service_security.py (workbook + smallest valid StudyBrief) — there
    is no shared fixture for it yet, so this follows that established shape
    rather than inventing a new one.
    """
    workbook_path = tmp_path / "source.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    workbook.active.append(["control", 1])
    workbook.active.append(["treated", 2])
    workbook.save(workbook_path)
    brief = {
        "title": "Methodology intake",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    response = client.post(
        "/v1/projects",
        json={
            "source_path": str(workbook_path),
            "project_root": str(tmp_path / "project.biostat"),
            "brief": brief,
        },
        headers=headers(),
    )
    return response.json()["id"]


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
    #
    # original_name is now deliberately the bare filename (Task 2: the
    # renderer carries it forward when attaching the document to a project),
    # so it legitimately appears in the body. What must never appear is the
    # directory it lived in — that is the actual filesystem-path leak this
    # test guards against.
    assert response.status_code == 200
    assert response.json()["brief"]["design"]["value"] == "cross_sectional"
    assert response.json()["original_name"] == "patient-cohort-2026.txt"
    assert str(path) not in response.text
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


def test_truncated_document_without_a_method_section_merges_both_warnings(
    client: TestClient, tmp_path: Path
) -> None:
    """Document warnings first, then brief warnings — the merge order is pinned."""
    path = tmp_path / "long.txt"
    path.write_text("Giriş\n" + "Hastalar kohort olarak izlendi. " * 7_000, encoding="utf-8")
    assert path.stat().st_size > MAX_DOCUMENT_CHARS

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert body["warnings"] == ["document_truncated", "no_method_section"]


def test_evidence_is_bounded_when_the_document_carries_no_punctuation(
    client: TestClient, tmp_path: Path
) -> None:
    """A punctuation-free document (pasted table, OCR) must not return itself.

    Without a bounded sentence window the evidence fallback runs to the end of
    the document, publishing every value in it over HTTP.
    """
    path = tmp_path / "table.txt"
    path.write_text(
        "kohort calismasi "
        + " ".join(f"hasta{index} yas{20 + index % 50} deger{index * 3}" for index in range(400)),
        encoding="utf-8",
    )

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    evidence = response.json()["brief"]["design"]["evidence"]
    assert len(evidence) <= EVIDENCE_MAX_CHARS + 1  # +1 allows the clipping ellipsis
    # The full document now legitimately rides along in the response's `text`
    # field (Task 2: the renderer carries it forward to attach to a project),
    # so the tail of the document is expected to appear somewhere in
    # response.text. What this test actually guards is narrower: the
    # `evidence` snippet specifically must stay bounded and not smuggle the
    # unbounded tail out through a second door.
    assert "hasta399" not in evidence
    assert "deger1197" not in evidence


def test_an_ordinary_sentence_is_returned_whole_and_unclipped(
    client: TestClient, tmp_path: Path
) -> None:
    """The cap must not damage the normal path — this is the plausible regression."""
    sentence = (
        "Bu çalışmada 2019-2024 yılları arasında kliniğimize başvuran hastalar "
        "retrospektif kohort tasarımıyla incelenmiştir."
    )
    path = tmp_path / "normal.txt"
    path.write_text(f"Yöntem\n{sentence}\nBulgular\nHastaların yaş ortalaması verildi.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    evidence = response.json()["brief"]["design"]["evidence"]
    assert evidence == sentence
    assert "…" not in evidence


def test_proposal_serializer_clips_over_long_evidence_on_its_own() -> None:
    """Layer 2 stands alone: it must clip evidence _sentence_around never saw.

    Proposal is the shared contract for every future engine, including the
    language-model one, whose evidence is not bounded by the rule extractor.
    """
    proposal = Proposal(
        value="cohort",
        confidence=0.7,
        source="rule",
        evidence="hasta-001 " * ((EVIDENCE_MAX_CHARS // 10) + 20),
        evidence_offset=0,
    )

    payload = _proposal_payload(proposal)

    assert payload is not None
    assert len(payload["evidence"]) == EVIDENCE_MAX_CHARS + 1
    assert payload["evidence"].endswith("…")
    assert payload["evidence"][:-1] == proposal.evidence[:EVIDENCE_MAX_CHARS]


def test_extract_returns_the_full_text_for_the_renderer_to_carry(
    client: TestClient, tmp_path: Path
) -> None:
    path = tmp_path / "m.txt"
    path.write_text("Yöntem\nRetrospektif kohort çalışması.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    body = response.json()
    assert body["text"] == "Yöntem\nRetrospektif kohort çalışması."
    assert body["original_name"] == "m.txt"


def test_document_attached_to_an_open_project_is_readable_again(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client, tmp_path)  # bkz. Step 1b

    response = client.post(
        f"/v1/projects/{project_id}/methodology",
        json={
            "text": "Yöntem\nKesitsel çalışma.",
            "source_sha256": "b" * 64,
            "source_format": "docx",
            "original_name": "yontem.docx",
            "char_count": 24,
            "truncated": False,
        },
        headers=headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"attached": True}
