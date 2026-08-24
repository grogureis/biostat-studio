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
    select_relevant_text,
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
    pypdf often cannot extract text from Type 3 embedded fonts. The rcParam
    is scoped with matplotlib.rc_context (the same pattern visuals.py uses
    for svg.hashsalt) so it never leaks into other tests in this process.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure()
    figure.text(0.1, 0.5, text)
    try:
        with matplotlib.rc_context({"pdf.fonttype": 42}):
            figure.savefig(path, format="pdf")
    finally:
        plt.close(figure)
    return path


def test_pdf_with_text_layer_round_trips_known_text(tmp_path: Path) -> None:
    path = write_pdf_with_text(tmp_path / "m.pdf", "Retrospective cohort study")

    result = extract_document(path)

    assert result.source_format == "pdf"
    assert "Retrospective cohort study" in result.text


def test_selects_turkish_method_section() -> None:
    text = (
        "Giriş\nAlakasız giriş metni.\n"
        "Gereç ve Yöntem\nRetrospektif kohort tasarımı kullanıldı.\n"
        "Bulgular\nAlakasız bulgu metni.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert "Retrospektif kohort tasarımı" in selected
    assert "Alakasız bulgu metni" not in selected
    assert warnings == ()


def test_selects_english_method_section() -> None:
    text = (
        "Introduction\nIrrelevant.\n"
        "Materials and Methods\nA retrospective cohort design was used.\n"
        "Results\nIrrelevant results.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert "retrospective cohort design" in selected
    assert "Irrelevant results" not in selected


def test_falls_back_to_prefix_and_warns_when_no_section_found() -> None:
    text = "Başlıksız düz metin. " * 100

    selected, warnings = select_relevant_text(text, budget=200)

    assert selected == text[:200]
    assert warnings == ("no_method_section",)


def test_selection_never_exceeds_budget() -> None:
    # Bug D fix: the heading must actually match so this exercises the
    # joined-chunk branch (selected[:budget]), not the no-match fallback
    # (text[:budget]) which is already covered by the fallback test above.
    # "Yöntem" has no İ/I, so it is unaffected by the Turkish-fold fix and
    # isolates the budget-clamping behavior being tested here.
    text = "Yöntem\n" + ("veri " * 5000)

    selected, warnings = select_relevant_text(text, budget=300)

    assert warnings == ()
    assert len(selected) <= 300


def test_overlapping_method_sections_are_merged_not_duplicated() -> None:
    """Bug A: Methods -> Statistical analysis -> Results is the near-universal
    biomedical paper shape. Both headings are method-family headings whose
    chunk both run up to the same Results stop, so the second chunk was a
    strict subset of the first and got pasted in twice."""
    text = (
        "Materials and Methods\n"
        "Patients were enrolled prospectively.\n"
        "Statistical analysis\n"
        "Chi-square test was used for categorical variables.\n"
        "Results\n"
        "Irrelevant results text.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert selected.count("Chi-square test was used") == 1
    assert warnings == ()


def test_disjoint_method_sections_separated_by_results_are_kept_separate() -> None:
    """Merging must not collapse a main Methods section and an appendix
    Methods section that are separated by an intervening Results section."""
    text = (
        "Methods\n"
        "Main analysis plan described here.\n"
        "Results\n"
        "Primary outcome text.\n"
        "Methods\n"
        "Appendix sensitivity analysis plan described here.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert "Main analysis plan described here" in selected
    assert "Appendix sensitivity analysis plan described here" in selected
    assert warnings == ()


def test_turkish_dotted_capital_does_not_corrupt_heading_offset() -> None:
    """Bugs B+C: str.lower() maps U+0130 (İ) to "i" + COMBINING DOT ABOVE,
    which both (B) fails to match the ASCII-i heading literals and (C) makes
    len(lowered) != len(text), so a match position found in `lowered` drifts
    when used to slice the original `text`. Preceding İ characters must not
    shift where the returned slice starts."""
    text = (
        "Giriş\n"
        "Katılımcılar İzmir, İstanbul ve İzmit şehirlerinden seçildi.\n"
        "İstatistiksel Analiz\n"
        "Ki-kare testi kullanıldı.\n"
        "Bulgular\n"
        "İlgisiz bulgular.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert warnings == ()
    assert selected.startswith("İstatistiksel Analiz")


def test_negative_budget_returns_empty_string() -> None:
    """Bug E(a): text[:budget] with a negative budget slices from the end,
    so a negative budget must be clamped to zero rather than passed through."""
    text = "Yöntem\nKohort çalışması yapıldı.\n"

    selected, _ = select_relevant_text(text, budget=-5)

    assert selected == ""


def test_matches_plural_gerec_ve_yontemler_heading() -> None:
    """Bug E(b): "gereç ve yöntemler" (plural compound) matched neither
    "gereç ve yöntem" (the plural suffix breaks the \\b boundary) nor
    "yöntemler" (the line starts with "gereç", not "yöntemler")."""
    text = (
        "Giriş\nAlakasız.\n"
        "Gereç ve Yöntemler\nRetrospektif kohort tasarımı kullanıldı.\n"
        "Bulgular\nAlakasız.\n"
    )

    selected, warnings = select_relevant_text(text, budget=10_000)

    assert "Retrospektif kohort tasarımı" in selected
    assert warnings == ()
