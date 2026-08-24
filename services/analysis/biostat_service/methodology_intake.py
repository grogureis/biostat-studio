"""Metodoloji dokümanından deterministik metin çıkarma."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from biostat_service.data_intake import sha256_file


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_CHARS = 200_000

SUPPORTED_FORMATS = frozenset({"docx", "pdf", "txt", "md"})


class MethodologyIntakeError(ValueError):
    """Stable, value-free failure code for document intake."""


@dataclass(frozen=True)
class MethodologyDocument:
    source_sha256: str
    source_format: str
    text: str
    char_count: int
    truncated: bool
    warnings: tuple[str, ...]


def _source_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_FORMATS:
        raise MethodologyIntakeError("unsupported_format")
    return suffix


def _read_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _read_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_document(path: Path) -> MethodologyDocument:
    source_format = _source_format(path)

    try:
        size = path.stat().st_size
    except OSError:
        raise MethodologyIntakeError("unreadable_document") from None
    if size > MAX_DOCUMENT_BYTES:
        raise MethodologyIntakeError("file_too_large")

    try:
        if source_format == "docx":
            raw = _read_docx(path)
        elif source_format == "pdf":
            raw = _read_pdf(path)
        else:
            raw = _read_plain(path)
    except MethodologyIntakeError:
        raise
    except Exception:  # noqa: BLE001 - any reader failure is one stable code
        raise MethodologyIntakeError("unreadable_document") from None

    text = raw.strip()
    if not text:
        raise MethodologyIntakeError("no_extractable_text")

    warnings: list[str] = []
    truncated = len(text) > MAX_DOCUMENT_CHARS
    if truncated:
        text = text[:MAX_DOCUMENT_CHARS]
        warnings.append("document_truncated")

    return MethodologyDocument(
        source_sha256=sha256_file(path),
        source_format=source_format,
        text=text,
        char_count=len(text),
        truncated=truncated,
        warnings=tuple(warnings),
    )


# Bölüm başlıkları TR+EN. Sıra önemsiz; hepsi taranır ve metindeki konumlarına
# göre sıralanır. Başlığın kendisi de seçime dahil edilir çünkü çıkarım motoru
# "Yöntem" kelimesini bağlam olarak kullanır.
SECTION_HEADINGS = (
    "gereç ve yöntem",
    "gerec ve yontem",
    "yöntem",
    "yontem",
    "yöntemler",
    "istatistiksel analiz",
    "istatistik analiz",
    "materials and methods",
    "methods",
    "methodology",
    "statistical analysis",
    "study design",
)

# Bir sonraki bölümün başladığını gösteren başlıklar — seçim burada durur.
STOP_HEADINGS = (
    "bulgular",
    "sonuçlar",
    "sonuclar",
    "tartışma",
    "tartisma",
    "kaynaklar",
    "results",
    "discussion",
    "conclusion",
    "references",
)


def _heading_positions(lowered: str, headings: tuple[str, ...]) -> list[int]:
    positions: list[int] = []
    for heading in headings:
        for match in re.finditer(rf"^\s*{re.escape(heading)}\b.*$", lowered, re.MULTILINE):
            positions.append(match.start())
    return sorted(positions)


def select_relevant_text(text: str, budget: int) -> tuple[str, tuple[str, ...]]:
    """Return the methodology-relevant slice of a document, bounded by budget.

    Deterministic and engine-independent: every extractor receives the same
    slice, so a gold-set comparison measures the engine and not the cropping.
    """
    lowered = text.lower()
    starts = _heading_positions(lowered, SECTION_HEADINGS)

    if not starts:
        return text[:budget], ("no_method_section",)

    stops = _heading_positions(lowered, STOP_HEADINGS)
    chunks: list[str] = []
    for start in starts:
        following = [stop for stop in stops if stop > start]
        end = following[0] if following else len(text)
        chunks.append(text[start:end])

    selected = "\n".join(chunks)
    return selected[:budget], ()
