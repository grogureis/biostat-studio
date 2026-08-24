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

# Tasarım sözlüğü. Sıra ÖNEMLİ: daha özgül kalıplar önce denenir, çünkü
# "randomize kontrollü çalışma" hem trial hem cohort kelimesi taşıyabilir.
#
# `repeated` yalnızca tasarımı KESİN olarak söyleyen ifadeleri taşır. Buradan
# "longitudinal follow-?up" çıkarıldı: o bir izlem TAKVİMİdir, tasarım değil.
# "Retrospective cohort study with longitudinal follow-up" gözlemsel klinik
# metodolojinin en yaygın cümlesidir ve `repeated` `cohort`tan önce denendiği
# için `repeated` dönüyordu; üstelik yanıtla birlikte gösterilen evidence
# cümlesi "cohort study" yazıyordu. Sadece sırayı değiştirmek yetmezdi:
# tasarım kelimesi geçmeyen "Longitudinal follow-up was performed." yine
# `repeated` olurdu. Sonuç kozmetik değil — planner.py design == "repeated"
# üzerinden denek-içi eşleştirilmiş analize dallanıyor.
DESIGN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("case_control", r"olgu[\s-]*kontrol|vaka[\s-]*kontrol|case[\s-]*control"),
    ("trial", r"randomize|randomised|randomized|klinik araştırma|controlled trial"),
    ("repeated", r"tekrarl[ıi] ölçüm|tekrarlayan ölçüm|repeated measures"),
    ("cohort", r"kohort|cohort"),
    ("cross_sectional", r"kesitsel|cross[\s-]*sectional"),
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
        for design, pattern in DESIGN_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            evidence = self._sentence_around(text, match.start())
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
                value=design,
                confidence=RULE_CONFIDENCE,
                evidence=evidence,
                evidence_offset=evidence_offset,
                source=self.name,
            )
        return None

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
