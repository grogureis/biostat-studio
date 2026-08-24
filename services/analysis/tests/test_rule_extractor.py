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


# --- RULING 1: evidence_offset must be recomputed against the ORIGINAL text,
# not derived from an offset into the merged `selected` slice. select_relevant_text
# joins multiple method sections with "\n", so a naive `base + match.start()`
# only happens to work when exactly one section was selected. This test uses
# two disjoint method sections (a main "Yöntem" section, then, after a
# "Bulgular" stop-heading, an "İstatistiksel Analiz" section) where the design
# keyword lives only in the SECOND section — the case the brief's own test
# (single-section) could never catch.
def test_evidence_offset_is_correct_when_the_match_is_in_a_second_merged_section() -> None:
    text = (
        "Yöntem\n"
        "Hastalar hastaneye başvuru sırasına göre kaydedildi.\n"
        "Bulgular\n"
        "Toplam 120 hasta değerlendirildi.\n"
        "İstatistiksel Analiz\n"
        "Retrospektif kohort çalışması yürütüldü.\n"
    )
    document = make_document(text)

    design = RuleExtractor().extract_brief(document).design

    assert design is not None
    assert design.value == "cohort"
    assert design.evidence_offset is not None
    assert text[design.evidence_offset:].startswith(design.evidence)


# --- RULING 2: BriefProposal must carry through the warnings that
# select_relevant_text emits (e.g. "no_method_section"), so a later task can
# surface them to the user instead of them being silently discarded.
def test_warnings_are_populated_when_no_method_section_is_found() -> None:
    document = make_document("Bu belge herhangi bir yöntem başlığı içermiyor.")

    result = RuleExtractor().extract_brief(document)

    assert result.warnings == ("no_method_section",)
