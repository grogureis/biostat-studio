"""Behavioral coverage for the methodology extraction endpoint."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from biostat_service.app import _proposal_payload, create_app
from biostat_service.extractors.contracts import (
    EVIDENCE_MAX_CHARS,
    BriefProposal,
    Proposal,
)
from biostat_service.extractors.engine import (
    EngineStatus,
    ExtractionRun,
    MethodologyEngine,
    VariableRun,
)
from biostat_service.extractors.rule import RuleExtractor
from biostat_service.methodology_intake import MAX_DOCUMENT_CHARS


class UnavailableLocalExtractor:
    name = "local:qwen2.5:14b"

    def available(self) -> bool:
        return False


def rule_fallback_engine() -> MethodologyEngine:
    return MethodologyEngine(local=UnavailableLocalExtractor(), rule=RuleExtractor())  # type: ignore[arg-type]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app(methodology_engine_factory=rule_fallback_engine)) as test_client:
        yield test_client


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


_PROJECT_ROOT_NAME = "project.biostat"


def _create_project(
    client: TestClient, tmp_path: Path, *, methodology: dict | None = None
) -> str:
    """Create a minimal project over HTTP and return its id.

    Mirrors the inline /v1/projects setup repeated throughout
    test_service_security.py (workbook + smallest valid StudyBrief) — there
    is no shared fixture for it yet, so this follows that established shape
    rather than inventing a new one. `methodology`, when given, rides along
    on the request body so this one helper covers both entry paths named in
    the task: attaching to an already-open project, and being born with a
    document already set.
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
    body: dict[str, object] = {
        "source_path": str(workbook_path),
        "project_root": str(tmp_path / _PROJECT_ROOT_NAME),
        "brief": brief,
    }
    if methodology is not None:
        body["methodology"] = methodology
    response = client.post("/v1/projects", json=body, headers=headers())
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
    assert body["engine"] == {
        "requested": "local:qwen2.5:14b",
        "used": "rule",
        "fallback_reason": "local_llm_unavailable",
    }


def test_extract_endpoint_publishes_local_engine_status_without_paths_or_raw_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    proposal = Proposal(
        value="cohort",
        confidence=0.79,
        source="local:qwen2.5:14b",
        evidence="prospective cohort",
        evidence_offset=8,
    )

    class StubEngine:
        def extract(self, _document):
            return ExtractionRun(
                BriefProposal(design=proposal),
                EngineStatus(
                    requested="local:qwen2.5:14b", used="local:qwen2.5:14b"
                ),
            )

        def variables(self, _document, _columns):
            return VariableRun((), EngineStatus("local:qwen2.5:14b", "local:qwen2.5:14b"))

    path = tmp_path / "private-protocol.txt"
    path.write_text("Methods\nprospective cohort", encoding="utf-8")
    with TestClient(create_app(methodology_engine_factory=StubEngine)) as local_client:
        response = local_client.post(
            "/v1/methodology/extract",
            json={"source_path": str(path)},
            headers=headers(),
        )

    assert response.status_code == 200
    assert response.json()["engine"] == {
        "requested": "local:qwen2.5:14b",
        "used": "local:qwen2.5:14b",
        "fallback_reason": None,
    }
    assert str(tmp_path) not in response.text


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


def test_project_created_with_a_methodology_document_attaches_it(
    client: TestClient, tmp_path: Path
) -> None:
    """Covers the "birth" entry path: methodology set inside /v1/projects.

    The sibling test above covers "already open" (POST .../methodology);
    this one had no coverage at all before this test — the
    attach_methodology/audit branch inside create_local_project, and the
    read_methodology call that keeps its in-memory context in sync with
    what was just written, ran with zero assertions anywhere in the suite.
    """
    methodology_payload = {
        "text": "Yöntem\nKesitsel çalışma.",
        "source_sha256": "c" * 64,
        "source_format": "docx",
        "original_name": "yontem-created.docx",
        "char_count": 24,
        "truncated": False,
        "extraction_engine": "local:qwen2.5:14b",
    }

    project_id = _create_project(client, tmp_path, methodology=methodology_payload)
    project_root = tmp_path / _PROJECT_ROOT_NAME

    # The document itself landed on disk, not just a manifest reference.
    assert (project_root / "source" / "methodology.txt").read_text(
        encoding="utf-8"
    ) == "Yöntem\nKesitsel çalışma."

    # Durably audited at birth, same pattern as
    # test_service_security.py:168-169.
    audit = (project_root / "audit.jsonl").read_text(encoding="utf-8")
    assert audit.count('"type": "methodology_document_attached"') == 1

    # In-memory state already reflects the document without a restart. This
    # is the assertion that fails if create_local_project's own
    # `methodology = read_methodology(project)` line is deleted — without
    # it context.methodology stays None until the project is closed and
    # reopened, even though the document is already durable on disk.
    context = client.app.state.projects[UUID(project_id)]
    assert context.methodology is not None
    assert context.methodology.original_name == "yontem-created.docx"
    assert context.methodology.extraction_engine == "local:qwen2.5:14b"


def test_variable_proposals_price_a_document_data_conflict(
    client: TestClient, tmp_path: Path
) -> None:
    workbook_path = tmp_path / "staging.xlsx"
    workbook = Workbook()
    workbook.active.append(["evre", "sonuc"])
    for stage in range(1, 5):
        workbook.active.append([stage, stage * 10])
    workbook.save(workbook_path)
    methodology = {
        "text": (
            "Yöntem\nBirincil sonlanım sonuc olarak belirlendi. "
            "Maruziyet evre olarak tanımlandı. "
            "Hastalar evre I-IV olarak sınıflandırıldı."
        ),
        "source_sha256": "d" * 64,
        "source_format": "docx",
        "original_name": "evre-yontem.docx",
        "char_count": 127,
        "truncated": False,
    }
    create_response = client.post(
        "/v1/projects",
        json={
            "source_path": str(workbook_path),
            "project_root": str(tmp_path / "staging.biostat"),
            "brief": {
                "title": "Evre ve sonuç",
                "question": "Evre ile sonuç arasında ilişki var mı?",
                "hypothesis": "İleri evre daha kötü sonuçla ilişkilidir.",
                "design": "cohort",
                "outcome_variables": ["sonuc"],
                "exposure_variables": ["evre"],
            },
            "methodology": methodology,
        },
        headers=headers(),
    )
    project_id = create_response.json()["id"]

    response = client.post(
        f"/v1/projects/{project_id}/variable-proposals", headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert any(item["column"] == "evre" for item in body["proposals"])
    conflict = next(item for item in body["conflicts"] if item["column"] == "evre")
    assert conflict["methods_if_document"] == ["descriptive_summary", "welch_anova"]
    assert conflict["methods_if_data"] == [
        "descriptive_summary",
        "pearson_or_spearman",
    ]
    assert "sınıflandırıldı" in conflict["evidence"]
