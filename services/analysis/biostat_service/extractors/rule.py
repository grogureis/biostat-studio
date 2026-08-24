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
                confidence=0.7,
                evidence=evidence,
                evidence_offset=evidence_offset,
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
