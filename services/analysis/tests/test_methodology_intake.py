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


def test_formatted_traceback_never_contains_the_file_path(tmp_path: Path) -> None:
    import traceback

    path = tmp_path / "secret-patient-study.docx"
    path.write_text("not really a docx", encoding="utf-8")

    try:
        extract_document(path)
    except MethodologyIntakeError as exc:
        rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    else:
        raise AssertionError("expected MethodologyIntakeError")

    assert "secret-patient-study" not in rendered
    assert str(tmp_path) not in rendered


def write_pdf(path: Path) -> Path:
    """Minimal single-page PDF with no text layer (a stand-in for a scanned PDF)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_pdf_without_text_layer_is_rejected_as_scanned(tmp_path: Path) -> None:
    path = write_pdf(tmp_path / "scan.pdf")

    with pytest.raises(MethodologyIntakeError) as excinfo:
        extract_document(path)

    assert str(excinfo.value) == "no_extractable_text"


def test_pdf_is_a_supported_format(tmp_path: Path) -> None:
    from biostat_service.methodology_intake import SUPPORTED_FORMATS

    assert "pdf" in SUPPORTED_FORMATS


def write_pdf_with_text(path: Path, text: str) -> Path:
    """Single-page PDF with a genuine, pypdf-extractable text layer.

    Uses matplotlib's PDF backend (already a service dependency) with
    pdf.fonttype=42 (TrueType) instead of the default 3 (Type 3), because
    pypdf often cannot extract text from Type 3 embedded fonts.
    """
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    import matplotlib.pyplot as plt

    figure = plt.figure()
    figure.text(0.1, 0.5, text)
    figure.savefig(path, format="pdf")
    plt.close(figure)
    return path


def test_pdf_with_text_layer_round_trips_known_text(tmp_path: Path) -> None:
    path = write_pdf_with_text(tmp_path / "m.pdf", "Retrospective cohort study")

    result = extract_document(path)

    assert result.source_format == "pdf"
    assert "Retrospective cohort study" in result.text
