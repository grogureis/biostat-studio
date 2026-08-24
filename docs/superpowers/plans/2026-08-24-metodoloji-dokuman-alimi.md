# Metodoloji Doküman Alımı — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kullanıcı bir metodoloji dokümanı (docx/pdf/txt/md) yükler; program metni çıkarır, kural tabanlı olarak çalışma özeti alanlarını önerir ve önerileri kanıtıyla birlikte ekranda gösterir.

**Architecture:** Metin çıkarma Python servisinde (`methodology_intake.py`), çıkarım kural tabanlı (`extractors/rule.py`), Electron yalnızca dosya seçip opak capability token üretir — renderer dosya yolunu hiç görmez. `planner.py` ve analiz katmanı bu planda hiç değişmez.

**Tech Stack:** Python 3.12 · FastAPI · pydantic v2 · python-docx (mevcut) · pypdf (yeni) · Electron 37 · React 19 · TypeScript · vitest · pytest

**Spec:** `docs/superpowers/specs/2026-08-24-metodoloji-cikarimi-design.md`

## Global Constraints

- Python `>=3.12,<3.13`. Test komutu: `npm run test:python`
- Desktop test komutu: `npm run test:desktop` (vitest). Typecheck: `npm run typecheck --workspace apps/desktop`
- Yeni bağımlılık yalnızca: `pypdf>=5,<6` (`services/analysis/pyproject.toml`)
- `MAX_DOCUMENT_BYTES = 25 * 1024 * 1024` — üstü reddedilir (spec §4 Karar D)
- `MAX_DOCUMENT_CHARS = 200_000` — üstü kırpılır **ve uyarı üretilir**, sessiz kırpma yasak
- Renderer dosya yolu görmez; capability token deseni (`main.ts:59-71`, `api-proxy.ts:43-51`) korunur
- Hiçbir hata mesajı, uyarı veya log **hücre değeri ya da dosya yolu içermez** (mevcut `data_intake.py` kuralı)
- Fixture konumu: repo kökü `tests/fixtures/` (bkz. `test_data_intake.py:20`)
- **Değişmez:** `planner.py`, `analyses.py`, `power.py`, `reporting.py`, `data_intake.py`
- Bilingual: kullanıcıya görünen her string TR ve EN olarak sağlanır

---

### Task 1: Metin çıkarma çekirdeği — docx / txt / md

**Files:**
- Create: `services/analysis/biostat_service/methodology_intake.py`
- Create: `services/analysis/tests/test_methodology_intake.py`

**Interfaces:**
- Consumes: hiçbir şey (ilk task)
- Produces:
  - `MethodologyDocument(source_sha256: str, source_format: str, text: str, char_count: int, truncated: bool, warnings: tuple[str, ...])` — frozen dataclass
  - `MethodologyIntakeError(ValueError)` — `str(exc)` bir hata kodu döner
  - `extract_document(path: Path) -> MethodologyDocument`
  - `MAX_DOCUMENT_BYTES: int`, `MAX_DOCUMENT_CHARS: int`
  - Hata kodları: `unsupported_format`, `file_too_large`, `no_extractable_text`, `unreadable_document`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:python -- tests/test_methodology_intake.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'biostat_service.methodology_intake'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Metodoloji dokümanından deterministik metin çıkarma."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from docx import Document


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_CHARS = 200_000

SUPPORTED_FORMATS = frozenset({"docx", "txt", "md"})


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


def extract_document(path: Path) -> MethodologyDocument:
    source_format = _source_format(path)

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MethodologyIntakeError("unreadable_document") from exc
    if size > MAX_DOCUMENT_BYTES:
        raise MethodologyIntakeError("file_too_large")

    try:
        raw = _read_docx(path) if source_format == "docx" else _read_plain(path)
    except MethodologyIntakeError:
        raise
    except Exception as exc:  # noqa: BLE001 - any reader failure is one stable code
        raise MethodologyIntakeError("unreadable_document") from exc

    text = raw.strip()
    if not text:
        raise MethodologyIntakeError("no_extractable_text")

    warnings: list[str] = []
    truncated = len(text) > MAX_DOCUMENT_CHARS
    if truncated:
        text = text[:MAX_DOCUMENT_CHARS]
        warnings.append("document_truncated")

    return MethodologyDocument(
        source_sha256=sha256(path.read_bytes()).hexdigest(),
        source_format=source_format,
        text=text,
        char_count=len(text),
        truncated=truncated,
        warnings=tuple(warnings),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:python -- tests/test_methodology_intake.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/methodology_intake.py services/analysis/tests/test_methodology_intake.py
git commit -m "feat: extract methodology document text from docx, txt and md"
```

---

### Task 2: PDF desteği ve taranmış PDF tespiti

**Files:**
- Modify: `services/analysis/pyproject.toml` (dependencies listesi)
- Modify: `services/analysis/biostat_service/methodology_intake.py`
- Modify: `services/analysis/tests/test_methodology_intake.py`

**Interfaces:**
- Consumes: Task 1'in `extract_document`, `MethodologyIntakeError`, `SUPPORTED_FORMATS`
- Produces: `SUPPORTED_FORMATS` artık `"pdf"` içerir; taranmış PDF `no_extractable_text` koduyla reddedilir

- [ ] **Step 1: Add the dependency**

`services/analysis/pyproject.toml` içindeki `dependencies` listesine, `python-docx` satırından sonra ekle:

```toml
    "pypdf>=5,<6",
```

Kur:

```bash
services/analysis/.venv-py312/bin/pip install "pypdf>=5,<6"
```

- [ ] **Step 2: Write the failing tests**

`services/analysis/tests/test_methodology_intake.py` dosyasının **sonuna** ekle:

```python
def write_pdf(path: Path, lines: list[str]) -> Path:
    """Minimal single-page PDF with a real text layer."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_pdf_without_text_layer_is_rejected_as_scanned(tmp_path: Path) -> None:
    path = write_pdf(tmp_path / "scan.pdf", [])

    with pytest.raises(MethodologyIntakeError) as excinfo:
        extract_document(path)

    assert str(excinfo.value) == "no_extractable_text"


def test_pdf_is_a_supported_format(tmp_path: Path) -> None:
    from biostat_service.methodology_intake import SUPPORTED_FORMATS

    assert "pdf" in SUPPORTED_FORMATS
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npm run test:python -- tests/test_methodology_intake.py -k pdf -v`
Expected: FAIL — `assert 'pdf' in SUPPORTED_FORMATS` ve `unsupported_format != no_extractable_text`

- [ ] **Step 4: Write minimal implementation**

`methodology_intake.py` içinde `SUPPORTED_FORMATS` satırını değiştir:

```python
SUPPORTED_FORMATS = frozenset({"docx", "pdf", "txt", "md"})
```

`_read_plain` fonksiyonundan sonra ekle:

```python
def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
```

`extract_document` içindeki okuma satırını değiştir:

```python
        if source_format == "docx":
            raw = _read_docx(path)
        elif source_format == "pdf":
            raw = _read_pdf(path)
        else:
            raw = _read_plain(path)
```

Not: metin katmanı olmayan PDF boş string döner ve mevcut `if not text: raise MethodologyIntakeError("no_extractable_text")` kolu devreye girer. Taranmış PDF için ayrı bir kod **gerekmiyor** — kullanıcıya gösterilen mesaj Task 8'de bu koddan türetilir.

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm run test:python -- tests/test_methodology_intake.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Commit**

```bash
git add services/analysis/pyproject.toml services/analysis/biostat_service/methodology_intake.py services/analysis/tests/test_methodology_intake.py
git commit -m "feat: read PDF methodology documents and reject scanned ones"
```

---

### Task 3: Bölüm bulucu — modele giden metnin daraltılması

**Files:**
- Modify: `services/analysis/biostat_service/methodology_intake.py`
- Modify: `services/analysis/tests/test_methodology_intake.py`

**Interfaces:**
- Consumes: Task 1'in `MethodologyDocument`
- Produces: `select_relevant_text(text: str, budget: int) -> tuple[str, tuple[str, ...]]` — döndürdüğü ikinci eleman uyarı kodları; ilgili bölüm bulunamazsa `("no_method_section",)`

Bu fonksiyon üç çıkarım motorunun da **önünde** durur; motordan bağımsız olması şart (spec §5).

- [ ] **Step 1: Write the failing tests**

Dosyanın sonuna ekle:

```python
from biostat_service.methodology_intake import select_relevant_text


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
    text = "İstatistiksel Analiz\n" + ("veri " * 5000)

    selected, _ = select_relevant_text(text, budget=300)

    assert len(selected) <= 300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:python -- tests/test_methodology_intake.py -k select_ -v`
Expected: FAIL — `ImportError: cannot import name 'select_relevant_text'`

- [ ] **Step 3: Write minimal implementation**

`methodology_intake.py` sonuna ekle:

```python
import re


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:python -- tests/test_methodology_intake.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add services/analysis/biostat_service/methodology_intake.py services/analysis/tests/test_methodology_intake.py
git commit -m "feat: narrow methodology text to its method sections deterministically"
```

---

### Task 4: `RuleExtractor` — çalışma tasarımı sınıflandırması

**Files:**
- Create: `services/analysis/biostat_service/extractors/__init__.py`
- Create: `services/analysis/biostat_service/extractors/contracts.py`
- Create: `services/analysis/biostat_service/extractors/rule.py`
- Create: `services/analysis/tests/test_rule_extractor.py`

**Interfaces:**
- Consumes: Task 1 `MethodologyDocument`, Task 3 `select_relevant_text`
- Produces:
  - `Proposal(value: str, confidence: float, evidence: str | None, evidence_offset: int | None, source: str)` — frozen dataclass
  - `BriefProposal(title, question, hypothesis, design, outcome_concepts, exposure_concepts, covariate_concepts)` — hepsi `Proposal | None` ya da `tuple[Proposal, ...]`
  - `RuleExtractor()` with `.name`, `.available()`, `.extract_brief(doc) -> BriefProposal`

- [ ] **Step 1: Write the failing tests**

```python
"""Behavioral coverage for the deterministic rule-based extractor."""

from __future__ import annotations

from biostat_service.extractors.contracts import BriefProposal, Proposal
from biostat_service.extractors.rule import RuleExtractor
from biostat_service.methodology_intake import MethodologyDocument


def make_document(text: str) -> MethodologyDocument:
    return MethodologyDocument(
        source_sha256="0" * 64,
        source_format="txt",
        text=text,
        char_count=len(text),
        truncated=False,
        warnings=(),
    )


def test_extractor_is_always_available() -> None:
    assert RuleExtractor().available() is True
    assert RuleExtractor().name == "rule"


def test_detects_turkish_retrospective_cohort() -> None:
    document = make_document("Yöntem\nRetrospektif kohort çalışması yürütüldü.")

    result = RuleExtractor().extract_brief(document)

    assert result.design is not None
    assert result.design.value == "cohort"
    assert "kohort" in result.design.evidence.lower()
    assert result.design.source == "rule"


def test_detects_turkish_case_control() -> None:
    document = make_document("Yöntem\nOlgu-kontrol tasarımı kullanıldı.")

    assert RuleExtractor().extract_brief(document).design.value == "case_control"


def test_detects_turkish_cross_sectional() -> None:
    document = make_document("Yöntem\nKesitsel bir çalışma planlandı.")

    assert RuleExtractor().extract_brief(document).design.value == "cross_sectional"


def test_detects_randomized_trial() -> None:
    document = make_document("Methods\nA randomized controlled trial was conducted.")

    assert RuleExtractor().extract_brief(document).design.value == "trial"


def test_detects_repeated_measures() -> None:
    document = make_document("Yöntem\nTekrarlı ölçümler ile değerlendirildi.")

    assert RuleExtractor().extract_brief(document).design.value == "repeated"


def test_leaves_design_empty_when_nothing_matches() -> None:
    document = make_document("Yöntem\nHastalar değerlendirildi.")

    assert RuleExtractor().extract_brief(document).design is None


def test_evidence_offset_points_into_the_original_text() -> None:
    text = "Yöntem\nRetrospektif kohort çalışması yürütüldü."
    document = make_document(text)

    design = RuleExtractor().extract_brief(document).design

    assert design.evidence_offset is not None
    assert text[design.evidence_offset:].lower().startswith("retrospektif kohort")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:python -- tests/test_rule_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'biostat_service.extractors'`

- [ ] **Step 3: Write the contracts module**

`services/analysis/biostat_service/extractors/__init__.py`:

```python
"""Methodology extraction engines."""
```

`services/analysis/biostat_service/extractors/contracts.py`:

```python
"""Shared proposal contracts for every methodology extraction engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proposal:
    """One machine-suggested value, always carrying its own evidence."""

    value: str
    confidence: float
    evidence: str | None = None
    evidence_offset: int | None = None
    source: str = "rule"


@dataclass(frozen=True)
class BriefProposal:
    """Study-brief fields proposed from a methodology document.

    Every field is a suggestion, never a decision: the user confirms each one
    before planner.build_plan is allowed to see it.
    """

    title: Proposal | None = None
    question: Proposal | None = None
    hypothesis: Proposal | None = None
    design: Proposal | None = None
    outcome_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
    exposure_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
    covariate_concepts: tuple[Proposal, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Write the rule extractor**

`services/analysis/biostat_service/extractors/rule.py`:

```python
"""Deterministic keyword-and-pattern extractor.

This engine is the always-available floor: it needs no model, no network and
no setup, and it is the baseline a language model must beat on the gold set.
It leaves a field empty rather than guessing.
"""

from __future__ import annotations

import re

from ..methodology_intake import MethodologyDocument, select_relevant_text
from .contracts import BriefProposal, Proposal


# Modele/kurala giden metin bütçesi. 12_000 karakter ~3 sayfa yoğun metin;
# bir metodoloji bölümü bunun altında kalır ve küçük yerel modellerin bağlamına
# da sığar (spec §5, bağlam bütçesi).
SELECTION_BUDGET = 12_000

# Tasarım sözlüğü. Sıra ÖNEMLİ: daha özgül kalıplar önce denenir, çünkü
# "randomize kontrollü çalışma" hem trial hem cohort kelimesi taşıyabilir.
DESIGN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("case_control", r"olgu[\s-]*kontrol|vaka[\s-]*kontrol|case[\s-]*control"),
    ("trial", r"randomize|randomised|randomized|klinik araştırma|controlled trial"),
    ("repeated", r"tekrarl[ıi] ölçüm|tekrarlayan ölçüm|repeated measures|longitudinal follow-?up"),
    ("cohort", r"kohort|cohort"),
    ("cross_sectional", r"kesitsel|cross[\s-]*sectional"),
)


class RuleExtractor:
    """Keyword-based extractor with no external dependency."""

    name = "rule"

    def available(self) -> bool:
        return True

    def extract_brief(self, document: MethodologyDocument) -> BriefProposal:
        selected, _ = select_relevant_text(document.text, SELECTION_BUDGET)
        offset = document.text.find(selected[:64]) if selected else -1
        base = offset if offset >= 0 else 0

        return BriefProposal(design=self._design(selected, base))

    def _design(self, text: str, base: int) -> Proposal | None:
        for design, pattern in DESIGN_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            return Proposal(
                value=design,
                confidence=0.7,
                evidence=self._sentence_around(text, match.start()),
                evidence_offset=base + match.start(),
                source=self.name,
            )
        return None

    @staticmethod
    def _sentence_around(text: str, index: int) -> str:
        start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
        end = min(
            (position for position in (text.find(".", index), text.find("\n", index)) if position != -1),
            default=len(text),
        )
        return text[start: end + 1].strip()
```

Not: `confidence=0.7` sabit ve kasıtlıdır — kural tabanı kalibre edilmiş bir olasılık üretmez; 0.7, "eşleşme buldum ama bağlamı doğrulayamadım" anlamında sabit bir işarettir. Kalibrasyon gold set ölçümünden sonra ele alınır (spec §11).

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm run test:python -- tests/test_rule_extractor.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Commit**

```bash
git add services/analysis/biostat_service/extractors services/analysis/tests/test_rule_extractor.py
git commit -m "feat: classify study design from methodology text with a rule engine"
```

---

### Task 5: Servis uç noktası ve oturumda doküman saklama

**Files:**
- Modify: `services/analysis/biostat_service/contracts.py`
- Modify: `services/analysis/biostat_service/app.py:495` civarı (`/v1/data/profile`'ın hemen ardına)
- Create: `services/analysis/tests/test_methodology_endpoint.py`

**Interfaces:**
- Consumes: Task 1 `extract_document`, Task 4 `RuleExtractor`, `BriefProposal`
- Produces: `POST /v1/methodology/extract` — gövde `{"source_path": str}`, yanıt:
  ```json
  {
    "source_sha256": "...", "source_format": "docx",
    "char_count": 1234, "truncated": false, "warnings": [],
    "brief": {"design": {"value": "cohort", "confidence": 0.7,
                         "evidence": "...", "evidence_offset": 12, "source": "rule"}}
  }
  ```
  Hata: HTTP 422, `detail` = `methodology_intake_failed:<kod>`

- [ ] **Step 1: Write the failing tests**

```python
"""Behavioral coverage for the methodology extraction endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from biostat_service.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    return TestClient(create_app())


def headers() -> dict[str, str]:
    return {"X-Biostat-Session": "test-token"}


def test_extracts_design_from_a_text_document(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "m.txt"
    path.write_text("Yöntem\nRetrospektif kohort çalışması.", encoding="utf-8")

    response = client.post(
        "/v1/methodology/extract", json={"source_path": str(path)}, headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_format"] == "txt"
    assert body["brief"]["design"]["value"] == "cohort"
    assert body["brief"]["design"]["source"] == "rule"


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

    assert "patient-cohort-2026" not in response.text
    assert str(tmp_path) not in response.text
```

Not: oturum başlığının adı ve doğrulama biçimi `services/analysis/tests/test_service_security.py` içindeki mevcut desenle **birebir aynı olmalı**. Bu testi yazmadan önce o dosyayı aç ve `require_session`'ın beklediği başlık adını oradan kopyala; yukarıdaki `X-Biostat-Session` bir varsayımdır, doğrula.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:python -- tests/test_methodology_endpoint.py -v`
Expected: FAIL — 404, rota tanımlı değil

- [ ] **Step 3: Add the request contract**

`services/analysis/biostat_service/contracts.py` sonuna ekle:

```python
class MethodologyExtractRequest(BaseModel):
    source_path: str = Field(min_length=1)
```

- [ ] **Step 4: Add the route**

`services/analysis/biostat_service/app.py` içinde `data_profile` fonksiyonunun **hemen ardına** ekle:

```python
    @v1.post("/methodology/extract")
    def methodology_extract(request: MethodologyExtractRequest) -> dict[str, Any]:
        try:
            document = extract_document(Path(request.source_path))
        except MethodologyIntakeError as exc:
            raise HTTPException(
                status_code=422, detail=f"methodology_intake_failed:{exc}"
            ) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="methodology_intake_failed:unreadable_document"
            ) from exc

        methodology_documents[document.source_sha256] = document
        brief = RuleExtractor().extract_brief(document)
        return {
            "source_sha256": document.source_sha256,
            "source_format": document.source_format,
            "char_count": document.char_count,
            "truncated": document.truncated,
            "warnings": list(document.warnings),
            "brief": _brief_proposal_payload(brief),
        }
```

`create_app()` içinde, `v1` router'ı tanımlanmadan **önce** ekle:

```python
    methodology_documents: dict[str, MethodologyDocument] = {}
```

Modül düzeyinde, diğer yardımcıların yanına ekle:

```python
def _proposal_payload(proposal: Proposal | None) -> dict[str, Any] | None:
    if proposal is None:
        return None
    return {
        "value": proposal.value,
        "confidence": proposal.confidence,
        "evidence": proposal.evidence,
        "evidence_offset": proposal.evidence_offset,
        "source": proposal.source,
    }


def _brief_proposal_payload(brief: BriefProposal) -> dict[str, Any]:
    return {
        "title": _proposal_payload(brief.title),
        "question": _proposal_payload(brief.question),
        "hypothesis": _proposal_payload(brief.hypothesis),
        "design": _proposal_payload(brief.design),
        "outcome_concepts": [_proposal_payload(p) for p in brief.outcome_concepts],
        "exposure_concepts": [_proposal_payload(p) for p in brief.exposure_concepts],
        "covariate_concepts": [_proposal_payload(p) for p in brief.covariate_concepts],
    }
```

Import satırlarına ekle:

```python
from .extractors.contracts import BriefProposal, Proposal
from .extractors.rule import RuleExtractor
from .methodology_intake import MethodologyDocument, MethodologyIntakeError, extract_document
```

`contracts` importuna `MethodologyExtractRequest` ekle.

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm run test:python -- tests/test_methodology_endpoint.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full Python suite for regressions**

Run: `npm run test:python`
Expected: PASS — mevcut testlerin hiçbiri kırılmamalı

- [ ] **Step 7: Commit**

```bash
git add services/analysis/biostat_service/contracts.py services/analysis/biostat_service/app.py services/analysis/tests/test_methodology_endpoint.py
git commit -m "feat: expose methodology extraction over the local service"
```

---

### Task 6: Electron capability, IPC ve proxy allowlist

**Files:**
- Modify: `apps/desktop/electron/path-capabilities.ts:1` (`PathCapabilityScope`)
- Modify: `apps/desktop/electron/main.ts:74` civarı (yeni `ipcMain.handle`)
- Modify: `apps/desktop/electron/bridge.ts:25,35`
- Modify: `apps/desktop/electron/api-proxy.ts:11,51`
- Modify: `apps/desktop/electron/path-capabilities.test.ts`
- Modify: `apps/desktop/electron/api-proxy.test.ts`

**Interfaces:**
- Consumes: Task 5'in `POST /v1/methodology/extract` rotası
- Produces:
  - `PathCapabilityScope` artık `"methodology-document"` içerir
  - IPC kanalı `biostat:select-methodology-document` → `{ id, displayName } | null`
  - `bridge.selectMethodologyDocument(): Promise<PathCapability | null>`
  - api-proxy `source_capability` → `source_path` enjeksiyonunu `methodology-document` scope'uyla yapar

- [ ] **Step 1: Write the failing tests**

`apps/desktop/electron/api-proxy.test.ts` içine, mevcut `data/profile` testinin yanına ekle:

```typescript
it("swaps a methodology capability for its path and allows the route", async () => {
  const capabilities = createPathCapabilityStore(() => "cap-1");
  const issued = capabilities.issue("methodology-document", "/tmp/m.docx", "m.docx");
  const forwarded: unknown[] = [];

  await handleApiRequest(
    { method: "POST", path: "/v1/methodology/extract", body: { source_capability: issued.id } },
    capabilities,
    async (request) => { forwarded.push(request.body); return { ok: true }; },
  );

  expect(forwarded[0]).toEqual({ source_path: "/tmp/m.docx" });
});
```

`apps/desktop/electron/path-capabilities.test.ts` içine ekle:

```typescript
it("issues and consumes a methodology-document capability", () => {
  const store = createPathCapabilityStore(() => "cap-m");
  const issued = store.issue("methodology-document", "/tmp/m.pdf", "m.pdf");

  expect(store.consume(issued.id, "methodology-document")).toBe("/tmp/m.pdf");
});

it("refuses to consume a methodology capability under another scope", () => {
  const store = createPathCapabilityStore(() => "cap-m");
  const issued = store.issue("methodology-document", "/tmp/m.pdf", "m.pdf");

  expect(() => store.consume(issued.id, "data-profile")).toThrow("Invalid path capability");
});
```

Not: yukarıdaki `handleApiRequest` çağrısının imzası bir varsayımdır. Testi yazmadan **önce** `apps/desktop/electron/api-proxy.test.ts` dosyasındaki mevcut testleri oku ve gerçek imzayı oradan kopyala.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:desktop`
Expected: FAIL — `"methodology-document"` scope tipi yok (TypeScript hatası) ve rota allowlist'te değil

- [ ] **Step 3: Widen the capability scope**

`apps/desktop/electron/path-capabilities.ts:1`:

```typescript
export type PathCapabilityScope =
  | "data-profile"
  | "data-import"
  | "project-create"
  | "project-open"
  | "report-save"
  | "methodology-document";
```

- [ ] **Step 4: Allow the route and inject the path**

`apps/desktop/electron/api-proxy.ts:11` — allowlist regex'ine `methodology/extract` ekle:

```typescript
  { method: "POST", route: /^\/v1\/(?:data\/profile|methodology\/extract|projects|projects\/open|plans|plans\/approval|jobs|reports)$/ },
```

`api-proxy.ts:51` civarına, `data/profile` enjeksiyonunun yanına ekle:

```typescript
      if (apiRequest.path === "/v1/methodology/extract")
        inject("source_capability", "source_path", "methodology-document");
```

- [ ] **Step 5: Add the IPC handler**

`apps/desktop/electron/main.ts` içinde `biostat:select-project` handler'ının **hemen öncesine** ekle:

```typescript
  ipcMain.handle("biostat:select-methodology-document", async (event) => {
    assertTrustedSender(event);
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: [{ name: "Methodology document", extensions: ["docx", "pdf", "txt", "md"] }],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    const path = result.filePaths[0];
    return pathCapabilities.issue("methodology-document", path, basename(path));
  });
```

Not: `assertTrustedSender(event)` bir varsayımdır — `main.ts:59`'daki mevcut `select-data-file` handler'ının ilk satırını okuyup **birebir aynı** güvenlik çağrısını kullan.

- [ ] **Step 6: Extend the bridge**

`apps/desktop/electron/bridge.ts:25` — arayüze ekle:

```typescript
  selectMethodologyDocument(): Promise<PathCapability | null>;
```

`bridge.ts:35` — implementasyona ekle:

```typescript
    selectMethodologyDocument: (): Promise<PathCapability | null> =>
      invoke("biostat:select-methodology-document"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `npm run test:desktop`
Expected: PASS

Run: `npm run typecheck --workspace apps/desktop`
Expected: hata yok

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/electron
git commit -m "feat: let the renderer pick a methodology document without seeing its path"
```

---

### Task 7: Renderer API istemcisi

**Files:**
- Modify: `apps/desktop/src/api/types.ts`
- Modify: `apps/desktop/src/api/client.ts:5` (arayüz) ve `:161` civarı (implementasyon)
- Modify: `apps/desktop/src/api/client.test.ts`

**Interfaces:**
- Consumes: Task 6 `bridge.selectMethodologyDocument`, Task 5 rotası
- Produces:
  - `ProposalDto { value: string; confidence: number; evidence: string | null; evidence_offset: number | null; source: string }`
  - `BriefProposalDto { title, question, hypothesis, design: ProposalDto | null; outcome_concepts, exposure_concepts, covariate_concepts: ProposalDto[] }`
  - `MethodologyExtraction { source_sha256, source_format, char_count, truncated, warnings: string[], brief: BriefProposalDto }`
  - `api.selectMethodologyDocument(): Promise<string | null>` — dosya adını döner (yol değil)
  - `api.extractMethodology(): Promise<MethodologyExtraction>`

- [ ] **Step 1: Write the failing test**

`apps/desktop/src/api/client.test.ts` sonuna ekle:

```typescript
it("extracts methodology using the capability issued by the picker", async () => {
  const sent: Array<{ path: string; body: unknown }> = [];
  const bridge = {
    ...stubBridge(),
    selectMethodologyDocument: async () => ({ id: "cap-1", displayName: "protokol.docx" }),
    requestApi: async (request: { path: string; body: unknown }) => {
      sent.push(request);
      return { source_sha256: "a", source_format: "docx", char_count: 10, truncated: false, warnings: [], brief: { design: null } };
    },
  };
  const api = createAnalysisApi(bridge as never);

  const name = await api.selectMethodologyDocument();
  await api.extractMethodology();

  expect(name).toBe("protokol.docx");
  expect(sent.at(-1)?.path).toBe("/v1/methodology/extract");
  expect(sent.at(-1)?.body).toEqual({ source_capability: "cap-1" });
});
```

Not: `stubBridge()` ve `createAnalysisApi` adları varsayımdır — dosyanın mevcut testlerinden gerçek yardımcı adlarını kopyala.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:desktop -- client.test.ts`
Expected: FAIL — `api.selectMethodologyDocument is not a function`

- [ ] **Step 3: Add the DTOs**

`apps/desktop/src/api/types.ts` sonuna ekle:

```typescript
export interface ProposalDto {
  value: string;
  confidence: number;
  evidence: string | null;
  evidence_offset: number | null;
  source: string;
}

export interface BriefProposalDto {
  title: ProposalDto | null;
  question: ProposalDto | null;
  hypothesis: ProposalDto | null;
  design: ProposalDto | null;
  outcome_concepts: ProposalDto[];
  exposure_concepts: ProposalDto[];
  covariate_concepts: ProposalDto[];
}

export interface MethodologyExtraction {
  source_sha256: string;
  source_format: string;
  char_count: number;
  truncated: boolean;
  warnings: string[];
  brief: BriefProposalDto;
}
```

- [ ] **Step 4: Add the client methods**

`apps/desktop/src/api/client.ts` — `AnalysisApi` arayüzüne ekle:

```typescript
  selectMethodologyDocument?(): Promise<string | null>;
  extractMethodology?(): Promise<MethodologyExtraction>;
```

`createAnalysisApi` içinde, `dataFile` değişkeninin yanına ekle:

```typescript
  let methodologyCapability: { id: string; displayName: string } | null = null;
```

`selectDataFile` implementasyonunun yanına ekle:

```typescript
    selectMethodologyDocument: async () => {
      methodologyCapability = await bridge.selectMethodologyDocument();
      return methodologyCapability?.displayName ?? null;
    },
    extractMethodology: async () => {
      if (!methodologyCapability) throw new Error("methodology_document_not_selected");
      return send<MethodologyExtraction>("/v1/methodology/extract", {
        source_capability: methodologyCapability.id,
      });
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm run test:desktop`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/api
git commit -m "feat: call methodology extraction from the renderer api client"
```

---

### Task 8: Çalışma özeti ekranında doküman paneli ve öneriler

**Files:**
- Modify: `apps/desktop/src/features/study/StudyBrief.tsx`
- Modify: `apps/desktop/src/App.tsx:211` (StudyBrief'e `api` prop'u geçirilir)
- Create: `apps/desktop/src/features/study/StudyBrief.test.tsx`
- Modify: `apps/desktop/src/styles/clinical-calm.css` (öneri rozeti)

**Interfaces:**
- Consumes: Task 7 `api.selectMethodologyDocument`, `api.extractMethodology`, `MethodologyExtraction`
- Produces: kullanıcıya görünen davranış — bu planın son task'ı, sonraki task tüketmiyor

- [ ] **Step 1: Write the failing tests**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StudyBrief } from "./StudyBrief";
import type { StudyBrief as StudyBriefDto } from "../../api/types";

const emptyBrief: StudyBriefDto = {
  title: "", question: "", hypothesis: "", design: "cross_sectional",
  outcome_variables: [],
};

function makeApi(overrides: Record<string, unknown> = {}) {
  return {
    selectMethodologyDocument: vi.fn(async () => "protokol.docx"),
    extractMethodology: vi.fn(async () => ({
      source_sha256: "a", source_format: "docx", char_count: 100,
      truncated: false, warnings: [],
      brief: {
        title: null, question: null, hypothesis: null,
        design: { value: "cohort", confidence: 0.7,
                  evidence: "Retrospektif kohort çalışması.", evidence_offset: 7, source: "rule" },
        outcome_concepts: [], exposure_concepts: [], covariate_concepts: [],
      },
    })),
    ...overrides,
  } as never;
}

describe("StudyBrief methodology upload", () => {
  it("applies the proposed design and shows its evidence", async () => {
    const onChange = vi.fn();
    render(<StudyBrief value={emptyBrief} onChange={onChange} language="tr" api={makeApi()} />);

    await userEvent.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

    expect(await screen.findByText("protokol.docx")).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ design: "cohort" }));
    expect(screen.getByText(/Retrospektif kohort çalışması\./)).toBeInTheDocument();
  });

  it("tells the user when a scanned pdf carries no text", async () => {
    const api = makeApi({
      extractMethodology: vi.fn(async () => { throw new Error("methodology_intake_failed:no_extractable_text"); }),
    });
    render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={api} />);

    await userEvent.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/okunabilir metin/i);
  });

  it("warns when the document was truncated", async () => {
    const api = makeApi({
      extractMethodology: vi.fn(async () => ({
        source_sha256: "a", source_format: "txt", char_count: 200000,
        truncated: true, warnings: ["document_truncated"],
        brief: { title: null, question: null, hypothesis: null, design: null,
                 outcome_concepts: [], exposure_concepts: [], covariate_concepts: [] },
      })),
    });
    render(<StudyBrief value={emptyBrief} onChange={vi.fn()} language="tr" api={api} />);

    await userEvent.click(screen.getByRole("button", { name: /metodoloji dokümanı/i }));

    expect(await screen.findByText(/kırpıldı/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:desktop -- StudyBrief.test.tsx`
Expected: FAIL — `StudyBrief` `api` prop'u kabul etmiyor, düğme yok

- [ ] **Step 3: Add the copy strings**

`StudyBrief.tsx` içindeki `text.en` nesnesine ekle:

```typescript
    upload: "Import methodology document",
    uploadHelp: "Word, PDF, text or markdown. Fields below are filled as suggestions you can change.",
    proposed: "from document",
    truncated: "The document was long, so only its first part was read.",
    noSection: "No methods section was found; the beginning of the document was used.",
    errors: {
      no_extractable_text: "This document contains no readable text. A scanned PDF has to be converted to text first.",
      unsupported_format: "This file type is not supported. Use Word, PDF, text or markdown.",
      file_too_large: "This file is too large to read.",
      unreadable_document: "This document could not be read.",
    },
```

`text.tr` nesnesine ekle:

```typescript
    upload: "Metodoloji dokümanı yükle",
    uploadHelp: "Word, PDF, metin veya markdown. Aşağıdaki alanlar öneri olarak doldurulur, değiştirebilirsiniz.",
    proposed: "dokümandan",
    truncated: "Doküman uzun olduğu için yalnızca ilk kısmı okundu.",
    noSection: "Yöntem bölümü bulunamadı; dokümanın başı kullanıldı.",
    errors: {
      no_extractable_text: "Bu dokümanda okunabilir metin yok. Taranmış bir PDF önce metne çevrilmelidir.",
      unsupported_format: "Bu dosya türü desteklenmiyor. Word, PDF, metin veya markdown kullanın.",
      file_too_large: "Bu dosya okunamayacak kadar büyük.",
      unreadable_document: "Bu doküman okunamadı.",
    },
```

- [ ] **Step 4: Implement the panel**

`StudyBrief.tsx` — props arayüzüne `api` ekle:

```typescript
import type { AnalysisApi } from "../../api/client";
import type { MethodologyExtraction } from "../../api/types";
import { useState } from "react";

interface StudyBriefProps {
  value: StudyBriefDto;
  onChange(value: StudyBriefDto): void;
  language: "en" | "tr";
  api?: AnalysisApi;
}
```

Bileşenin gövdesine, `update` tanımının ardına ekle:

```typescript
  const [documentName, setDocumentName] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<MethodologyExtraction | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const importDocument = async () => {
    if (!api?.selectMethodologyDocument || !api.extractMethodology) return;
    setFailure(null);
    try {
      const name = await api.selectMethodologyDocument();
      if (!name) return;
      setDocumentName(name);
      const result = await api.extractMethodology();
      setExtraction(result);
      if (result.brief.design) {
        update("design", result.brief.design.value as StudyDesign);
      }
    } catch (error) {
      const code = error instanceof Error ? error.message.split(":").at(-1) ?? "" : "";
      setFailure(code in copy.errors ? code : "unreadable_document");
      setDocumentName(null);
    }
  };
```

`<header>` ile `<form>` arasına paneli ekle:

```tsx
      <div className="drop-panel">
        <div className="workbook-glyph" aria-hidden="true">DOC</div>
        <div>
          {documentName ? <p className="file-name">{documentName}</p> : null}
          <p className="form-help">{copy.uploadHelp}</p>
          {extraction?.truncated ? <p className="warning-line">{copy.truncated}</p> : null}
          {extraction?.warnings.includes("no_method_section")
            ? <p className="warning-line">{copy.noSection}</p> : null}
        </div>
        <button type="button" className="primary-action" onClick={() => void importDocument()}>
          {copy.upload}
        </button>
      </div>
      {failure ? (
        <div className="error-panel" role="alert">
          <span aria-hidden="true">!</span>
          <p>{copy.errors[failure as keyof typeof copy.errors]}</p>
        </div>
      ) : null}
```

Tasarım alanının etiketinin yanına öneri rozetini ekle:

```tsx
          <label htmlFor="study-design">
            {copy.design}
            {extraction?.brief.design ? (
              <span className="proposal-badge" title={extraction.brief.design.evidence ?? ""}>
                {copy.proposed}
              </span>
            ) : null}
          </label>
```

Ve kanıt cümlesini alanın altında göster:

```tsx
          {extraction?.brief.design?.evidence ? (
            <p className="form-help evidence-quote">{extraction.brief.design.evidence}</p>
          ) : null}
```

- [ ] **Step 5: Pass the api prop**

`apps/desktop/src/App.tsx:211` — `StudyBrief` çağrısına `api={api}` ekle:

```tsx
{project.activeStep === "study" ? <StudyBrief value={project.brief} onChange={changeBrief} language={project.language} api={api} /> : null}
```

- [ ] **Step 6: Add the badge style**

`apps/desktop/src/styles/clinical-calm.css` sonuna ekle:

```css
.proposal-badge {
  margin-left: 0.5rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  background: color-mix(in srgb, currentColor 10%, transparent);
  border: 1px solid color-mix(in srgb, currentColor 25%, transparent);
  cursor: help;
}

.evidence-quote {
  font-style: italic;
  border-left: 2px solid color-mix(in srgb, currentColor 30%, transparent);
  padding-left: 0.6rem;
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `npm run test:desktop`
Expected: PASS

Run: `npm run typecheck --workspace apps/desktop`
Expected: hata yok

- [ ] **Step 8: Run the whole suite**

Run: `npm test`
Expected: PASS — Python ve desktop birlikte

- [ ] **Step 9: Commit**

```bash
git add apps/desktop/src/features/study apps/desktop/src/App.tsx apps/desktop/src/styles/clinical-calm.css
git commit -m "feat: propose study design from an imported methodology document"
```

---

## Sonraki planlar

Bu plan Faz 1'in ilk dikey dilimidir. Kalan iki plan spec'ten türetilecek:

- **Plan 2 — Değişken eşleştirme ve çelişki çözümü:** `match_variables`, bulanık sütun eşleştirme, çelişki tespiti, `planner.build_plan`'ın iki kez çağrılıp bedelin hesaplanması, `DataIntake.tsx` onay bloğu, `confirmed` bayrağının düzeltilmesi (spec §5–§6, Bulgu A-1)
- **Plan 3 — Blocking sözlüğü ve ölçüm düzeneği:** 20 kodluk TR/EN sözlük, `PlanReview.tsx` render'ı, gold set, `scripts/eval-extractors.py`, `LocalExtractor` (Ollama) (spec §7–§8)

`LocalExtractor` bilinçli olarak en sonda: bu planın tamamı LLM'siz çalışır, dolayısıyla model seçimi hiçbir işi bekletmez.
