"""Deterministic keyword-and-pattern extractor.

This engine is the always-available floor: it needs no model, no network and
no setup, and it is the baseline a language model must beat on the gold set.
It leaves a field empty rather than guessing.
"""

from __future__ import annotations

import re

from ..methodology_intake import MethodologyDocument, select_relevant_text
from .contracts import EVIDENCE_MAX_CHARS, BriefProposal, Proposal


# Modele/kurala giden metin bütçesi. 12_000 karakter ~3 sayfa yoğun metin;
# bir metodoloji bölümü bunun altında kalır ve küçük yerel modellerin bağlamına
# da sığar (spec §5, bağlam bütçesi).
SELECTION_BUDGET = 12_000

# Dash class for compound terms like "case-control" / "cross-sectional".
# Journals typeset these with an EN DASH (U+2013), not the ASCII hyphen "-"
# people type by hand. Measured on PMC9801609 ("Hospital-based
# case–control study"): an ASCII-only "[\s-]*" class never matched the en
# dash, so case_control never fired and the engine fell through to `cohort`
# via an unrelated "...recruited from a cohort study..." mention later in
# the same text. Covers the Unicode dash block U+2010 HYPHEN through U+2015
# HORIZONTAL BAR (which includes the en dash U+2013 and em dash U+2014) plus
# the ASCII hyphen, so any dash style a journal uses is matched. Defined
# once here so every pattern that needs a dash reuses this instead of
# drifting out of sync.
DASH_CLASS = "\\-\u2010-\u2015"

# Tasarım sözlüğü. `_design` artık listedeki İLK eşleşeni değil, metinde EN
# ERKEN geçen eşleşmeyi seçiyor: metodoloji bölümleri kendi tasarımını
# genelde en başta söyler, metnin ilerisinde aynı anahtar kelimenin tekrar
# geçmesi çoğunlukla bir ATIF ya da karşılaştırmadır. Ölçüm: PMC12170779
# (altın yanıt: cohort) karakter ~185'te "...their respective cohorts..."
# diyerek kendi tasarımını söylüyor, ama karakter ~2690'da "MultiCase-Control
# Study-Spain" adlı başka bir çalışmadan bahsediyor — yalnızca liste sırasına
# bakan eski mantık case_control'ü cohort'tan önce dener, atıfı kazandırır ve
# yanlış yanıt üretirdi. Liste sırası ARTIK SADECE iki kalıp metinde tam aynı
# ofsette eşleştiğinde eşitlik bozucu (tie-break) olarak kullanılıyor.
#
# `repeated` yalnızca tasarımı KESİN olarak söyleyen ifadeleri taşır. Buradan
# "longitudinal follow-?up" çıkarıldı: o bir izlem TAKVİMİdir, tasarım değil.
# "Retrospective cohort study with longitudinal follow-up" gözlemsel klinik
# metodolojinin en yaygın cümlesidir; kalıp geniş tutulsaydı bu cümlede
# `repeated` ile `cohort` yakın ofsetlerde eşleşir ve hangisinin kazanacağı
# metne bağlı kırılgan bir yarışa dönerdi. Kalıbı dar tutmak bu yarışı baştan
# önlüyor: tasarım kelimesi hiç geçmeyen "Longitudinal follow-up was
# performed." hâlâ None dönüyor. Sonuç kozmetik değil — planner.py
# design == "repeated" üzerinden denek-içi eşleştirilmiş analize dallanıyor.
DESIGN_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "case_control",
        rf"olgu[\s{DASH_CLASS}]*kontrol|vaka[\s{DASH_CLASS}]*kontrol|case[\s{DASH_CLASS}]*control",
    ),
    ("trial", r"randomize|randomised|randomized|klinik araştırma|controlled trial"),
    ("repeated", r"tekrarl[ıi] ölçüm|tekrarlayan ölçüm|repeated measures"),
    ("cohort", r"kohort|cohort"),
    ("cross_sectional", rf"kesitsel|cross[\s{DASH_CLASS}]*sectional"),
)

# Sabit bir sentinel: "bir kalıp eşleşti ama bağlamı doğrulayamadım" demektir.
# KALİBRE EDİLMİŞ BİR OLASILIK DEĞİLDİR. Her kural önerisi, eşleşmenin
# kalitesinden bağımsız olarak aynı değeri alır — tek kelimelik zayıf bir
# eşleşme de, cümlenin tamamını doğrulayan güçlü bir eşleşme de 0.7 döner.
# Bu sayı renderer'a `confidence` olarak serileştiriliyor ve spec §6/§11 toplu
# kabul (bulk-accept) eşiğini tam da buna karşı planlıyor. Gold-set ölçümü
# yapılmadan bu değer bir eşik girdisi olarak KULLANILMAMALIDIR: kalibre
# edilmemiş bir sabite karşı kurulan eşik, iş yapıyormuş gibi görünüp hiçbir
# şey elemeyen bir güvenlik kapısıdır.
RULE_CONFIDENCE = 0.7


class RuleExtractor:
    """Keyword-based extractor with no external dependency."""

    name = "rule"

    def available(self) -> bool:
        return True

    def extract_brief(self, document: MethodologyDocument) -> BriefProposal:
        selected, warnings = select_relevant_text(document.text, SELECTION_BUDGET)

        return BriefProposal(
            design=self._design(document.text, selected),
            warnings=warnings,
        )

    def _design(self, original_text: str, text: str) -> Proposal | None:
        # Pick the pattern whose match starts EARLIEST in `text`, not the
        # first pattern in DESIGN_PATTERNS order that matches anywhere.
        # Methods sections state their own design up front; a keyword that
        # recurs later is usually a citation or a comparison to another
        # study (see the DESIGN_PATTERNS comment for the measured case).
        # Scanning in list order and only replacing `best` on a STRICTLY
        # earlier offset means that when two patterns match at the exact
        # same offset, the one earlier in DESIGN_PATTERNS wins — the
        # documented tie-break, and it is applied the same way regardless
        # of dict/set iteration, so the result is deterministic.
        best_design: str | None = None
        best_match: re.Match[str] | None = None
        for design, pattern in DESIGN_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            if best_match is None or match.start() < best_match.start():
                best_design, best_match = design, match

        if best_match is None:
            return None

        evidence = self._sentence_around(text, best_match.start())
        # `text` (the selected slice) is not a contiguous substring of
        # `original_text` in general — select_relevant_text can merge
        # several method sections joined by "\n". Locating the evidence
        # sentence directly in the original text is the only offset that
        # is guaranteed correct regardless of how many sections were
        # merged. find() returns -1 when the sentence can't be located
        # (e.g. it was truncated at the selection budget boundary); store
        # None rather than a bogus negative offset.
        found = original_text.find(evidence)
        evidence_offset = found if found >= 0 else None
        return Proposal(
            value=best_design,
            confidence=RULE_CONFIDENCE,
            evidence=evidence,
            evidence_offset=evidence_offset,
            source=self.name,
        )

    @staticmethod
    def _sentence_around(text: str, index: int) -> str:
        """The sentence containing `index`, searched only within a bounded window.

        Sentence delimiters are looked for within ±EVIDENCE_MAX_CHARS of the
        match. Searching the whole document instead means that a text carrying
        no "." or newline near the match — a pasted table, a bullet list, OCR
        output with punctuation stripped — falls back to the entire document,
        and that evidence is published in the HTTP response. When no delimiter
        exists inside the window the text is cut at the window edge and marked
        with "…" so the reader can see the evidence was clipped.
        """
        window_start = max(0, index - EVIDENCE_MAX_CHARS)
        window_end = min(len(text), index + EVIDENCE_MAX_CHARS)

        opening = max(
            text.rfind(".", window_start, index), text.rfind("\n", window_start, index)
        )
        start = opening + 1 if opening >= 0 else window_start

        closing = [
            position
            for position in (
                text.find(".", index, window_end),
                text.find("\n", index, window_end),
            )
            if position != -1
        ]
        if closing:
            return text[start: min(closing) + 1].strip()

        # No delimiter ahead. Reaching window_end is the document's own end
        # only when the window got there; otherwise the sentence is clipped.
        clipped = text[start:window_end].strip()
        return f"{clipped}…" if window_end < len(text) else clipped
