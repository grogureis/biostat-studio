"""Behavioral coverage for methodology document text extraction."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from docx import Document
import pytest

from biostat_service.methodology_intake import (
    MAX_DOCUMENT_CHARS,
    MethodologyDocument,
    MethodologyIntakeError,
    extract_document,
)


def write_docx(path: Path, paragraphs: list[str]) -> Path:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)
    return path


def test_extracts_docx_paragraphs_in_order(tmp_path: Path) -> None:
    path = write_docx(tmp_path / "m.docx", ["Yöntem", "Retrospektif kohort."])

    result = extract_document(path)

    assert result.source_format == "docx"
    assert "Yöntem" in result.text
    assert result.text.index("Yöntem") < result.text.index("Retrospektif kohort.")
    assert result.truncated is False


def test_reports_sha256_of_source_file(tmp_path: Path) -> None:
    path = write_docx(tmp_path / "m.docx", ["Yöntem"])

    result = extract_document(path)

    assert result.source_sha256 == sha256(path.read_bytes()).hexdigest()


def test_extracts_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "m.txt"
    path.write_text("Kesitsel çalışma.", encoding="utf-8")

    result = extract_document(path)

    assert result.source_format == "txt"
    assert result.text.strip() == "Kesitsel çalışma."


def test_extracts_markdown(tmp_path: Path) -> None:
    path = tmp_path / "m.md"
    path.write_text("# Yöntem\n\nOlgu-kontrol.", encoding="utf-8")

    result = extract_document(path)

    assert result.source_format == "md"
    assert "Olgu-kontrol." in result.text


def test_rejects_unsupported_format(tmp_path: Path) -> None:
    path = tmp_path / "m.rtf"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(MethodologyIntakeError) as excinfo:
        extract_document(path)

    assert str(excinfo.value) == "unsupported_format"


def test_rejects_document_with_no_extractable_text(tmp_path: Path) -> None:
    path = write_docx(tmp_path / "empty.docx", ["", "   "])

    with pytest.raises(MethodologyIntakeError) as excinfo:
        extract_document(path)

    assert str(excinfo.value) == "no_extractable_text"


def test_truncates_oversized_text_and_warns(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("a" * (MAX_DOCUMENT_CHARS + 500), encoding="utf-8")

    result = extract_document(path)

    assert result.truncated is True
    assert result.char_count == MAX_DOCUMENT_CHARS
    assert "document_truncated" in result.warnings


def test_error_message_never_contains_the_file_path(tmp_path: Path) -> None:
    path = tmp_path / "secret-patient-study.rtf"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(MethodologyIntakeError) as excinfo:
        extract_document(path)

    assert "secret-patient-study" not in str(excinfo.value)
    assert str(tmp_path) not in str(excinfo.value)
