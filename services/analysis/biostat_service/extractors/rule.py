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

# Türkçe "X için düzeltildi" (adjusted for X) fiil öbeği. Bir kez tanımlanıp
# hem CONCEPT_PATTERNS'in covariate alt-kalıbında hem _BACKWARD_TRIGGER'da
# kullanılıyor — DASH_CLASS'ın DESIGN_PATTERNS'te tekrar kullanılma
# gerekçesiyle aynı: ikisi birbirinden kayarsa _BACKWARD_TRIGGER.fullmatch
# sessizce hep False döner ve backward-span hiç çalışmaz.
#
# ÖLÇÜLMÜŞ KUSUR (gözden geçirmede bulundu, düzeltildi): önceki kalıp bare
# "düzeltil(di|erek|miş)" idi — "için" şartı yoktu. "Aykırı değerler
# saptandıktan sonra veri seti düzeltildi ve analiz tekrarlandı." cümlesinde
# bu bare fiil ateşleniyordu; ama bu VERİ TEMİZLEME'dir, kovaryat düzeltmesi
# değil. Gerçek "adjusted for X" deyiminde "için" HER ZAMAN fiilin hemen
# önünde; bu şart bir DARALTMA (widening değil) ve o cümleyi baştan eler.
_ADJUSTMENT_VERB = r"i[çc]in\s+d[üu]zeltil(?:di|erek|mi[şs])"

# Kavram kalıpları. Her kalıp, ARDINDAN gelen metnin kavram olduğunu iddia
# eder — TEK istisnayla, bkz. _BACKWARD_TRIGGER. Kalıplar dar: "sonuç" tek
# başına yok (Türkçe'de "sonuç olarak" bağlacı her metodoloji metninde geçer
# ve her seferinde yanlış eşleşirdi).
#
# `exposure`'daki "maruziyet" artık `\b` ile çıpalı. ÖLÇÜLMÜŞ KUSUR: bare
# "maruziyet", "maruziyeti"/"maruziyetin" gibi çekimli biçimlerin İÇİNDE de
# eşleşiyordu (eşleşme "maruziyet" kökünde bitiyor, ekten önce), ve ileri
# yönlü ayrıştırma o zaman "i değerlendirildi" gibi bir ek-artığını kavram
# sanıyordu. `\b`, kökten hemen sonra bir sözcük karakteri geldiğinde
# (yani bir ek varsa) eşleşmeyi TAMAMEN engeller — "maruziyet
# değerlendirildi" gibi çekimsiz biçimler hâlâ ateşlenir, ama "maruziyeti"
# artık hiç ateşlenmez (sessizlik, çöp değil). Diğer Türkçe kökler
# (kovaryat, değişken, çıktı) aynı ek-yapışması riskini taşıyabilir ama
# ÖLÇÜLMEDİ — burada düzeltilmedi, bilinen bir boşluk olarak bırakıldı.
CONCEPT_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "outcome",
        r"(?:birincil|primer|ana)\s+(?:sonlan[ıi]m|son\s+nokta|[çc][ıi]kt[ıi])"
        r"|primary\s+(?:outcome|endpoint)|ba[ğg][ıi]ml[ıi]\s+de[ğg]i[şs]ken",
    ),
    (
        "exposure",
        r"maruziyet\b|ba[ğg][ıi]ms[ıi]z\s+de[ğg]i[şs]ken|exposure(?:\s+variable)?",
    ),
    (
        "covariate",
        rf"kovaryat|covariates?|{_ADJUSTMENT_VERB}"
        r"|adjusted\s+for|kar[ıi][şs]t[ıi]r[ıi]c[ıi]|confounder",
    ),
)

# Bu tek alt-kalıp eşleştiğinde kavram listesi eşleşmenin ÖNÜNDE yer alır:
# Türkçe "yaş, cinsiyet için düzeltildi" = "adjusted for age, sex", ama fiil
# cümlenin SONUNDA. CONCEPT_PATTERNS'teki her diğer tetikleyici (kovaryat,
# covariates, adjusted for, karıştırıcı, confounder, birincil sonlanım,
# maruziyet, ...) ileriye bakar; yalnızca bu fiil öbeği geriye bakar.
_BACKWARD_TRIGGER = re.compile(_ADJUSTMENT_VERB, re.IGNORECASE)

# Bilinen kusur sınıflarına karşı dar bir olumsuz-bağlam kapısı — genel bir
# sınıflandırıcı DEĞİL. Eşleşmenin çevresindeki pencerede (bkz.
# _NEGATIVE_CONTEXT_WINDOW) bunlardan biri varsa eşleşme SESSİZCE atlanır,
# hiçbir aday üretmez.
#   (1) atıf: "Smith VE ARK. çalışmasında..." / "et al." — başka bir
#       çalışmanın kendi beyanı, bu çalışmanınki değil. DESIGN_PATTERNS
#       yorumundaki (PMC12170779) atıf kusuruyla AYNI sınıf.
#   (2) kısıtlılık: "...en önemli KISITLILIĞI, ..." — bir kısıtlılık
#       cümlesi tipik olarak YAPILMAMIŞ bir şeyi anlatır, çalışmanın kendi
#       yönteminin beyanı değil.
#   (3) olumsuz fiil — TEK TEK YAZILMIŞ ("yapılama"/"düzeltileme"/
#       "edilmedi") DEĞİL, gövde+ek KALIBI: yapıl-/edil-/düzeltil- gövdesi
#       + olumsuzluk eki ("ma"/"me", basit olumsuzlama VEYA "ama"/"eme",
#       yapabilirlik-olumsuzlaması) + geçmiş zaman eki (-dı/-di/-du/-dü
#       VEYA -mış/-miş/-muş/-müş). GÖZDEN GEÇİRME TUR 2'DE ÖLÇÜLEN KUSUR:
#       önceki sürüm yalnızca "yapılama" (gövde+"ama", yapabilirlik-
#       olumsuzlaması) alt dizesini taşıyordu; Türkçenin en sık geçmiş
#       zaman OLUMSUZLAMASI olan "-madı/-medi" (basit olumsuzlama) hiç
#       kapsanmıyordu. "Yaş, cinsiyet ve BKİ potansiyel karıştırıcı
#       faktörlerdi ancak hiçbir düzeltme YAPILMADI." böylece kapıdan
#       kaçıyor ve tüm cümle kalıntısı bir "kovaryat" sanılıyordu. Kalıp
#       artık HER İKİ olumsuzlama biçimini de, HER İKİ geçmiş zaman ekini
#       de kapsıyor — "yapılamamış" (eski, hâlâ çalışıyor) ile "yapılmadı"
#       (yeni) aynı alt-kalıpla yakalanıyor.
# ÖLÇÜLMEDİ: bu üç sınıfın dışındaki atıf/olumsuzlama biçimleri yakalanmaz
# (örn. "(Smith et al., 2020)" farklı noktalama kullanabilir, ya da
# "kontrol edilmedi" gibi bu üç gövdenin dışında bir fiil kullanılabilir —
# kasıtlı olarak yalnızca bu üç gövdeye (yapıl-/edil-/düzeltil-) sınırlı
# tutuldu, Türkçedeki her fiile genellenmedi).
_NEGATED_PAST_TENSE = r"(?:d[ıiuü]|m[ıiuü]ş)"
_NEGATIVE_CONTEXT = re.compile(
    r"ve\s+ark\.|et\s+al\."
    r"|k[ıi]s[ıi]tl[ıi]l[ıi]k|limitation"
    rf"|yap[ıi]l(?:ma|ama){_NEGATED_PAST_TENSE}"
    rf"|edil(?:me|eme){_NEGATED_PAST_TENSE}"
    rf"|d[üu]zeltil(?:me|eme){_NEGATED_PAST_TENSE}",
    re.IGNORECASE,
)

# _NEGATIVE_CONTEXT taraması `_sentence_around`'ın döndürdüğü cümle
# ÜZERİNDE DEĞİL, eşleşmenin çevresinde SABİT genişlikte bir pencerede
# çalışır. ÖLÇÜLMÜŞ SEBEP: "Smith ve ark. çalışmasında..." — "ark."
# kısaltmasındaki nokta `_sentence_around` tarafından cümle sonu sanılıyor,
# bu yüzden "ve ark." döndürülen cümlenin DIŞINDA kalıyor ve atıf işareti
# hiç görülmüyordu. Pencere genişliği (200) ÖLÇÜLMEDİ — yalnızca üç örneğin
# gerektirdiği mesafeden (~30 karakter) cömert bir pay bırakacak şekilde
# seçildi. Aşırı geniş bir pencere ilgisiz bir paragraftaki bir atıfı da
# yakalayıp yanlışlıkla bastırabilir, ama bu kapıda yanlış bastırmak
# (sessiz kalmak) yanlış çıkarmaktan daha güvenli bir hata modudur —
# spec §5'in "tahmin etmektense boş bırak" kuralı.
_NEGATIVE_CONTEXT_WINDOW = 200

# Geriye bakan ayrıştırmada, ilk kalemin ÖNÜNDEKİ cümle öznesini (kavramın
# kendisini değil) atmak için kullanılan dar, KAPALI bir özne sözcüğü seti.
# GÖZDEN GEÇİRME TUR 2'DE ÖLÇÜLEN KUSUR (bu sürümde düzeltildi): önceki
# sürüm YAPISAL bir kural kullanıyordu — "boşlukla ayrılmış iki+ sözcük
# görürsen ilkini at, hangi sözcük olduğuna bakma." "Vücut kitle indeksi,
# yaş ve cinsiyet için düzeltildi." cümlesinde bu kural "Vücut"u da attı ve
# ['kitle indeksi', 'yaş', 'cinsiyet'] üretti — "kitle indeksi" var
# OLMAYAN bir terim. Bu, eski kapalı-liste kusurunun (sızdırılmış ama BÜTÜN
# bir özne) tersi, DAHA KÖTÜ bir hata: kısmen kesilmiş, UYDURULMUŞ bir
# değer. Bu turun kuralı şüphede sessizliktir; bu yüzden yapısal kural artık
# YOK — yerine iki dallı bir kural geldi (bkz. `_drop_leading_subject`):
#   - ilk sözcük bu KAPALI listede ise: SADECE o sözcüğü at, kalemin geri
#     kalanını (çok sözcüklü olsa bile) bozmadan bırak.
#   - değilse: ilk sözcüğü kesmeyi DENEMEZ — cümle öznesini çok sözcüklü
#     bir bileşik terimden (aynı yüzey şeklini taşırlar: virgülsüz,
#     boşlukla ayrılmış ardışık sözcükler) sözcüksel bilgi olmadan ayırt
#     edemeyeceği için, İLK KALEMİN TAMAMINI atar — "Vücut kitle indeksi"yi
#     kaybetmek kabul edilebilir, "kitle indeksi" UYDURMAK değil.
# Liste büyümeye açık ama KASITLI OLARAK küçük tutuluyor; her yeni sözcük
# gerçek bir örnekle gerekçelendirilmeli, "olabilir" diye eklenmemeli.
_ADJUSTMENT_SUBJECT_WORDS = frozenset(
    {"modeller", "model", "analizler", "analiz", "çalışma"}
)

# İleri yönlü ayrıştırmada, tetikleyiciden HEMEN sonra gelen ve kavramın
# kendisi OLMAYAN iskele sözcüklerini atar. ÖLÇÜLMÜŞ İKİ KUSUR:
#   - "birincil sonlanım NOKTASI 30 günlük mortalite..." — "noktası"
#     ("sonlanım noktası" = "endpoint") tetikleyicinin doğal bir UZANTISI,
#     "30 günlük mortalite"nin bir parçası değil. Task 5'in tek testi iki
#     sözcüklü biçimi ("sonlanım", "noktası"sız) kullandığı için bu kusur
#     görünmüyordu.
#   - "Ana çıktı OLARAK 30 günlük reamisyon oranı belirlendi." — buradaki
#     "olarak" tetikleyiciden SONRAKİ bir BAĞLAÇTIR ("as the outcome, ..."),
#     _TRAILING'in yakaladığı cümle SONU "... olarak tanımlandı" kalıbıyla
#     KARIŞTIRILMAMALI: ikisi aynı sözcüğü taşır ama gramer rolleri zıttır
#     (biri baş, biri kuyruk). _TRAILING'in ÇIPASIZ eski hâli bu ikisini
#     ayıramıyor ve "30"u sessizce yutuyordu (bkz. _TRAILING).
_LEADING_SCAFFOLD = re.compile(
    r"^\s*nokta(?:s[ıi])?\s+|^\s*(?:olarak|i[çc]in)\s+",
    re.IGNORECASE,
)

# Kalıptan sonra (ya da önce) art arda gelen kavramları ayıran bağlaçlar.
_SPLIT = re.compile(r",|\bve\b|\band\b|\bile\b", re.IGNORECASE)

# Adayın kuyruğundaki gramer artığını temizler: "... olarak tanımlandı",
# "... için düzeltildi", cümle sonu noktalama. HER ÜÇ alternatif de cümle
# SONUNA ($) çıpalı — isim ve bu yorum "kuyruk" (trailing) davranışı vaat
# ediyor. ÖLÇÜLMÜŞ KUSUR (gözden geçirmede bulundu, düzeltildi): çıpasız
# hâliyle, "Ana çıktı OLARAK 30 günlük reamisyon oranı belirlendi."
# tail'inde "olarak\s+\w+" tetikleyiciden hemen SONRAKİ bağlacı ("olarak
# 30") yakalıyor ve "30"u sessizce siliyordu — bu bir kuyruk eşleşmesi
# değildi, adayın BAŞINDA bir eşleşmeydi. Çıpa bunu imkânsız kılıyor:
# alternatif artık yalnızca adayın gerçek sonunda ateşlenebilir. (Baştaki
# "olarak" bağlacı artık `_LEADING_SCAFFOLD` tarafından ayrıca atılıyor.)
_TRAILING = re.compile(
    r"\s*(?:i[çc]in\s+)?d[üu]zeltil\w*\s*$|\s*olarak\s+\w+\s*$|\s*[.;]\s*$",
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
        the Turkish adjustment-verb alternative ("için düzeltildi" /
        "düzeltilerek" / "düzeltilmiş"), whose covariate list sits BEFORE
        it — see `_BACKWARD_TRIGGER`. A match whose surrounding text carries
        a known false-fire marker (`_NEGATIVE_CONTEXT`) is skipped entirely
        before any candidate is built. A trigger that fires but yields no
        candidate inside CONCEPT_MIN/MAX_CHARS contributes nothing: this is
        the "leave it empty rather than guess" rule applied per-candidate,
        not just per-match.
        """
        found: list[Proposal] = []
        seen: set[str] = set()
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if self._negative_context(text, match):
                continue

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
                span = _LEADING_SCAFFOLD.sub("", span, count=1)

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
    def _negative_context(text: str, match: re.Match[str]) -> bool:
        """True when a known false-fire marker (`_NEGATIVE_CONTEXT`) appears near `match`.

        Checked over a bounded window (`_NEGATIVE_CONTEXT_WINDOW`), not
        `_sentence_around`'s sentence — see that constant's comment for why
        a citation marker can fall outside the "sentence" `_sentence_around`
        computes.
        """
        window_start = max(0, match.start() - _NEGATIVE_CONTEXT_WINDOW)
        window_end = min(len(text), match.end() + _NEGATIVE_CONTEXT_WINDOW)
        return _NEGATIVE_CONTEXT.search(text[window_start:window_end]) is not None

    @staticmethod
    def _backward_span(text: str, match: re.Match[str]) -> str:
        """The text preceding a backward trigger, back to the last sentence delimiter.

        Bounded the same way `_sentence_around` and the forward branch are
        (at most CONCEPT_MAX_CHARS * 4 characters back). CRITICAL, MEASURED
        DEFECT — now fixed: the previous version had NO bound at all; when
        no "." or "\\n" preceded the trigger anywhere in the text, it fell
        back to `text[0:match.end()]`. Reproduced: one long sentence with
        several comma lists and no preceding period yielded 18 covariate
        candidates, including city names nowhere near the adjustment
        clause. Per this round's ruling — when in doubt, emit nothing — a
        missing delimiter inside the bound now returns "" rather than
        falling back to ANY wider window, bounded or not.

        `_drop_leading_subject` then removes whatever precedes the
        covariate list at the front of the span; see its comment for what
        it does and does not attempt.
        """
        window_floor = max(0, match.start() - CONCEPT_MAX_CHARS * 4)
        window_start = max(
            text.rfind(".", window_floor, match.start()),
            text.rfind("\n", window_floor, match.start()),
        )
        if window_start < 0:
            return ""
        span = text[window_start + 1 : match.end()]
        return RuleExtractor._drop_leading_subject(span)

    @staticmethod
    def _drop_leading_subject(span: str) -> str:
        """Remove whatever precedes the covariate list at the front of `span`.

        Two branches, chosen so neither branch can INVENT a value:
          - the leading word IS in `_ADJUSTMENT_SUBJECT_WORDS`: strip JUST
            that word, keeping the rest of the first item intact even if
            it is itself a multi-word compound (e.g. "vücut kitle
            indeksi").
          - anything else: a bare leading word cannot be told apart from
            the first word of a genuine multi-word compound term without
            lexical knowledge this engine does not have (both are
            whitespace-joined words with no comma before the next
            delimiter — see the MEASURED counterexample below). Rather
            than guess by cutting mid-term, the WHOLE first item is
            discarded — including the ONLY item, if the span has no
            comma/"ve"/"and"/"ile" at all, which returns "" (silence, not
            a guess at which prefix is real).

        MEASURED (code review round 2): the prior version
        (`_LEADING_SUBJECT_TOKEN`, an unconditional first-token drop with
        no subject check) turned "Vücut kitle indeksi, yaş ve cinsiyet
        için düzeltildi." into ['kitle indeksi', 'yaş', 'cinsiyet'] —
        "kitle indeksi" is not a term that exists. That version traded the
        earlier closed-list defect (a leaked-but-WHOLE subject) for one
        that severs a genuine compound concept mid-term: a WRONG value,
        not silence, which this round's ruling treats as strictly worse
        than losing the item outright.
        """
        leading = re.match(r"^\s*(\w+)\s+", span)
        if leading is None:
            return span
        if leading.group(1).lower() in _ADJUSTMENT_SUBJECT_WORDS:
            return span[leading.end() :]
        delimiter = _SPLIT.search(span)
        if delimiter is None:
            return ""
        return span[delimiter.end() :]

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
