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

    # sha256_file reads the file too, so it is a reader failure like any other
    # and belongs INSIDE this guard. Left outside, a PermissionError from it
    # escapes extract_document unsuppressed — and its str() carries the full
    # filesystem path. Nothing leaks to a response today because app.py has a
    # blanket handler, but that is one layer, and this module deliberately
    # insists on two everywhere else.
    try:
        if source_format == "docx":
            raw = _read_docx(path)
        elif source_format == "pdf":
            raw = _read_pdf(path)
        else:
            raw = _read_plain(path)
        source_sha256 = sha256_file(path)
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
        source_sha256=source_sha256,
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
    "gereç ve yöntemler",
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


# Length-preserving casefolds. str.lower() is locale-independent and maps
# U+0130 (İ) to TWO code points ("i" + COMBINING DOT ABOVE), which both
# (a) fails to match the heading literals below and (b) changes the string
# length, corrupting every match offset computed against `lowered` once it
# is used to slice the original (unfolded) `text`. Folding İ -> i first, one
# character for one character, keeps positions aligned.
#
# ASCII capital "I" cannot be folded one way for both languages: Turkish
# spells the uppercase of dotless "ı" as ASCII "I" (so "TARTIŞMA" needs
# I -> ı to become "tartışma" and match), but English needs "I" -> "i" (so
# "MATERIALS AND METHODS" matches "materials and methods"). One global
# mapping breaks one language or the other, so both folds are tried and the
# match positions are unioned (see _heading_positions_union).
_FOLD_TR = str.maketrans({"İ": "i", "I": "ı"})  # Turkish: capital I is dotless ı
_FOLD_EN = str.maketrans({"İ": "i"})  # ASCII: capital I lowercases to i


def _heading_positions(lowered: str, headings: tuple[str, ...]) -> list[int]:
    positions: list[int] = []
    for heading in headings:
        for match in re.finditer(rf"^\s*{re.escape(heading)}\b.*$", lowered, re.MULTILINE):
            positions.append(match.start())
    return positions


def _heading_positions_union(
    lowered_tr: str, lowered_en: str, headings: tuple[str, ...]
) -> list[int]:
    """Match positions found under either casefold, deduplicated and sorted.

    The same heading can match at the same offset under both folds (any
    heading with no I/İ in it, and every character before it, folds
    identically both ways). Deduplicating before interval merging matters:
    re-emitting the same position would reintroduce the duplicate-chunk bug
    (Bug A) that interval merging was built to fix.
    """
    positions = set(_heading_positions(lowered_tr, headings))
    positions.update(_heading_positions(lowered_en, headings))
    return sorted(positions)


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/contained (start, end) intervals, sorted by start.

    A method-family heading (e.g. "Statistical analysis") that occurs before
    the same stop heading as an earlier method-family heading (e.g.
    "Materials and Methods") produces a chunk that is a strict subset of the
    first. Without merging, joining the chunks pastes that text in twice.
    Intervals separated by an intervening stop (e.g. a main Methods section
    and an appendix Methods section split by Results) stay disjoint.
    """
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def select_relevant_text(text: str, budget: int) -> tuple[str, tuple[str, ...]]:
    """Return the methodology-relevant slice of a document, bounded by budget.

    Deterministic and engine-independent: every extractor receives the same
    slice, so a gold-set comparison measures the engine and not the cropping.
    """
    budget = max(0, budget)

    lowered_tr = text.translate(_FOLD_TR).lower()
    lowered_en = text.translate(_FOLD_EN).lower()
    if len(lowered_tr) != len(text) or len(lowered_en) != len(text):
        # Defensive guard: if some future input still changes length under
        # either fold, match offsets against that folded string cannot be
        # trusted to index into `text`. Fail closed to the prefix fallback
        # rather than silently return a corrupted slice.
        return text[:budget], ("no_method_section",)

    starts = _heading_positions_union(lowered_tr, lowered_en, SECTION_HEADINGS)

    if not starts:
        return text[:budget], ("no_method_section",)

    stops = _heading_positions_union(lowered_tr, lowered_en, STOP_HEADINGS)
    intervals: list[tuple[int, int]] = []
    for start in starts:
        following = [stop for stop in stops if stop > start]
        end = following[0] if following else len(text)
        intervals.append((start, end))

    chunks = [text[start:end] for start, end in _merge_intervals(intervals)]

    selected = "\n".join(chunks)
    return selected[:budget], ()
