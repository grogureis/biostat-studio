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

# Kavram kalıpları. Her kalıp, ARDINDAN gelen metnin kavram olduğunu iddia
# eder — TEK istisnayla, bkz. _BACKWARD_TRIGGER. Kalıplar dar: "sonuç" tek
# başına yok (Türkçe'de "sonuç olarak" bağlacı her metodoloji metninde geçer
# ve her seferinde yanlış eşleşirdi).
CONCEPT_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "outcome",
        r"(?:birincil|primer|ana)\s+(?:sonlan[ıi]m|son\s+nokta|[çc][ıi]kt[ıi])"
        r"|primary\s+(?:outcome|endpoint)|ba[ğg][ıi]ml[ıi]\s+de[ğg]i[şs]ken",
    ),
    (
        "exposure",
        r"maruziyet|ba[ğg][ıi]ms[ıi]z\s+de[ğg]i[şs]ken|exposure(?:\s+variable)?",
    ),
    (
        "covariate",
        r"kovaryat|covariates?|d[üu]zeltil(?:di|erek|mi[şs])|adjusted\s+for"
        r"|kar[ıi][şs]t[ıi]r[ıi]c[ıi]|confounder",
    ),
)

# Bu tek alt-kalıp eşleştiğinde kavram listesi eşleşmenin ÖNÜNDE yer alır:
# Türkçe "yaş, cinsiyet için düzeltildi" = "adjusted for age, sex", ama fiil
# cümlenin SONUNDA. CONCEPT_PATTERNS'teki her diğer tetikleyici (kovaryat,
# covariates, adjusted for, karıştırıcı, confounder, birincil sonlanım,
# maruziyet, ...) ileriye bakar; yalnızca bu fiil çekimleri geriye bakar.
_BACKWARD_TRIGGER = re.compile(r"d[üu]zeltil(?:di|erek|mi[şs])", re.IGNORECASE)

# Geriye bakan ayrıştırmada, listenin ÖNÜNDEKİ cümle öznesini (fiilin
# kendisini değil, cümlenin gerçek öznesini) kavram sanmamak için atılan
# dar, kapalı bir sözcük seti. Ölçüldü: "Modeller yaş, cinsiyet ... için
# düzeltildi" cümlesinde regex "Modeller"i "yaş" ile GRAMER OLARAK ayırt
# edemez — ikisi de virgülsüz, tek boşlukla ayrılmış sözcükler, tıpkı
# "vücut kitle indeksi" gibi (o da içeride virgülsüz, boşlukla ayrılmış üç
# sözcük). Sözcüksel bir liste dışında ayırma yolu yok. Bu listenin
# dışındaki öznelerde yanlış davranır (özneyi kavram sayar) — bu genelleme
# ÖLÇÜLMEDİ, yalnızca bu kalıbın kapsadığı örnekler için doğrulandı.
_ADJUSTMENT_SUBJECT = re.compile(
    r"^\s*(?:modeller|model|analizler|analiz)\s+",
    re.IGNORECASE,
)

# Kalıptan sonra (ya da önce) art arda gelen kavramları ayıran bağlaçlar.
_SPLIT = re.compile(r",|\bve\b|\band\b|\bile\b", re.IGNORECASE)

# Adayın kuyruğundaki gramer artığını temizler: "... olarak tanımlandı",
# "... için düzeltildi", cümle sonu noktalama.
_TRAILING = re.compile(
    r"\s*(?:i[çc]in\s+)?d[üu]zeltil\w*|\s*olarak\s+\w+|\s*[.;]\s*$",
    re.IGNORECASE,
)

# Bir kavram adı için makul uzunluk penceresi. Alt sınır: tek harfli parçalar
# ayrıştırma artığıdır. Üst sınır: 60 karakteri aşan bir parça artık bir
# değişken adı değil, cümlenin geri kalanıdır.
CONCEPT_MIN_CHARS = 2
CONCEPT_MAX_CHARS = 60


class RuleExtractor:
    """Keyword-based extractor with no external dependency."""

    name = "rule"

    def available(self) -> bool:
        return True

    def extract_brief(self, document: MethodologyDocument) -> BriefProposal:
        selected, warnings = select_relevant_text(document.text, SELECTION_BUDGET)

        return BriefProposal(
            design=self._design(document.text, selected),
            outcome_concepts=self._concepts(
                document.text, selected, CONCEPT_PATTERNS[0][1]
            ),
            exposure_concepts=self._concepts(
                document.text, selected, CONCEPT_PATTERNS[1][1]
            ),
            covariate_concepts=self._concepts(
                document.text, selected, CONCEPT_PATTERNS[2][1]
            ),
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

    def _concepts(
        self, original_text: str, text: str, pattern: str
    ) -> tuple[Proposal, ...]:
        """Extract concept names anchored to one trigger pattern, or nothing.

        Every trigger in `pattern` places its concept AFTER itself, except
        the Turkish adjustment-verb alternative ("düzeltildi" /
        "düzeltilerek" / "düzeltilmiş"), whose covariate list sits BEFORE
        it — see `_BACKWARD_TRIGGER`. A trigger that fires but yields no
        candidate inside CONCEPT_MIN/MAX_CHARS contributes nothing: this is
        the "leave it empty rather than guess" rule applied per-candidate,
        not just per-sentence.
        """
        found: list[Proposal] = []
        seen: set[str] = set()
        for match in re.finditer(pattern, text, re.IGNORECASE):
            sentence = self._sentence_around(text, match.start())
            # Same reasoning as `_design`: `text` may be a non-contiguous
            # merge of several method sections, so the offset published to
            # the HTTP response is relocated in `original_text` — the only
            # copy where an offset is guaranteed to mean what it says.
            located = original_text.find(sentence)
            evidence_offset = located if located >= 0 else None

            if _BACKWARD_TRIGGER.fullmatch(match.group()):
                span = self._backward_span(text, match)
            else:
                span = text[match.end() : match.end() + CONCEPT_MAX_CHARS * 4]
                span = span.split(".")[0]

            for raw in _SPLIT.split(span):
                candidate = _TRAILING.sub("", raw).strip(" \t:,–—-")
                if not CONCEPT_MIN_CHARS <= len(candidate) <= CONCEPT_MAX_CHARS:
                    continue
                if candidate.lower() in seen:
                    continue
                seen.add(candidate.lower())
                found.append(
                    Proposal(
                        value=candidate,
                        confidence=RULE_CONFIDENCE,
                        source=self.name,
                        evidence=sentence[:EVIDENCE_MAX_CHARS],
                        evidence_offset=evidence_offset,
                    )
                )
        return tuple(found)

    @staticmethod
    def _backward_span(text: str, match: re.Match[str]) -> str:
        """The text preceding a backward trigger, back to the last sentence delimiter.

        Measured: "Modeller yaş, cinsiyet ve vücut kitle indeksi için
        düzeltildi." — a bare regex cannot tell the clause's own subject
        ("Modeller") from a list item ("vücut kitle indeksi"): both are
        whitespace-joined words with no comma or "ve" between them, so
        there is no delimiter-based way to draw the line.
        `_ADJUSTMENT_SUBJECT` strips a short, closed set of known subject
        words seen in this exact construction; sentences using a different
        subject word will still leak it into the first candidate (not
        measured).
        """
        window_start = max(
            text.rfind(".", 0, match.start()), text.rfind("\n", 0, match.start())
        )
        window_start = window_start + 1 if window_start >= 0 else 0
        span = text[window_start : match.end()]
        return _ADJUSTMENT_SUBJECT.sub("", span, count=1)

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
