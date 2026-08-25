"""Behavioral coverage for the deterministic rule-based extractor."""

from __future__ import annotations

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


def test_detects_repeated_measures_in_english() -> None:
    document = make_document("Methods\nA repeated measures ANOVA was used.")

    assert RuleExtractor().extract_brief(document).design.value == "repeated"


# --- FINAL REVIEW: "longitudinal follow-up" is a follow-up SCHEDULE, not a
# design. It was an alternative of the `repeated` pattern, and `repeated` is
# tried before `cohort`, so the single most common observational phrasing —
# "retrospective cohort study with longitudinal follow-up" — classified as
# `repeated`. The consequence is not cosmetic: planner.py branches on
# design == "repeated" into within-subject paired analysis and raises
# unsupported_repeated_design when no pair-id variable exists. The evidence
# sentence returned alongside the answer literally contains "cohort study",
# so the UI rendered a proposal badge whose own quote disproved it.
def test_english_retrospective_cohort_with_longitudinal_follow_up_is_cohort() -> None:
    document = make_document(
        "Methods\nWe conducted a retrospective cohort study with longitudinal follow-up of 24 months."
    )

    design = RuleExtractor().extract_brief(document).design

    assert design is not None
    assert design.value == "cohort"
    assert "cohort study" in design.evidence.lower()


def test_english_prospective_cohort_with_longitudinal_followup_is_cohort() -> None:
    document = make_document(
        "Methods\nA prospective cohort study with longitudinal followup was performed."
    )

    assert RuleExtractor().extract_brief(document).design.value == "cohort"


def test_turkish_cohort_with_longitudinal_follow_up_is_cohort() -> None:
    document = make_document(
        "Yöntem\nRetrospektif kohort çalışması, 24 aylık longitudinal follow-up ile yürütüldü."
    )

    assert RuleExtractor().extract_brief(document).design.value == "cohort"


def test_longitudinal_follow_up_alone_is_not_a_design() -> None:
    """Reordering the patterns would not have been enough.

    With `cohort` merely moved ahead of `repeated`, a sentence carrying the
    follow-up schedule and no design word at all would still come out
    `repeated`. A follow-up schedule is not evidence of a within-subject
    design, so the correct answer is no proposal rather than a wrong one.
    """
    document = make_document("Methods\nLongitudinal follow-up was performed.")

    assert RuleExtractor().extract_brief(document).design is None


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


# --- MEASUREMENT (PMC9801609, gold: case_control): "Hospital-based
# case–control study" uses an EN DASH (U+2013), the character journals
# actually typeset between "case" and "control" — not the ASCII hyphen "-"
# people type by hand. An ASCII-only dash class never matches this sentence
# at all, so case_control never fires and the engine falls through to
# `cohort` on an unrelated "...recruited from a cohort study..." mention
# later in the same methods section. The en dash below is typed literally,
# not escaped, so the test fails the same way real journal text would.
def test_detects_case_control_with_en_dash() -> None:
    document = make_document("Methods\nHospital-based case–control study was conducted.")

    assert RuleExtractor().extract_brief(document).design.value == "case_control"


# --- MEASUREMENT (PMC12170779, gold: cohort): the methods section states its
# own design in the first sentence ("...in their respective cohorts, and a
# completed follow-up...", ~char 185) but, ~2000 characters later, cites an
# unrelated study by name that happens to contain "Case-Control" in its
# title ("MultiCase-Control Study-Spain"). Selecting the first pattern that
# matches ANYWHERE in the text (list order: case_control before cohort) lets
# that citation outrank the study's own design statement. The correct
# behaviour is to prefer whichever pattern matches EARLIEST in the text.
def test_cohort_design_stated_early_outranks_a_later_cited_study_name() -> None:
    padding = "Participants were recruited through routine clinical visits. " * 33
    text = (
        "Methods\n"
        "Participants were followed as members of their respective cohorts, "
        "and a completed follow-up questionnaire was required for inclusion "
        "in the analysis.\n"
        + padding
        + "Our findings are consistent with the MultiCase-Control Study-Spain, "
        "which reported similar associations.\n"
    )
    assert len(padding) > 1900, "padding must place the citation ~2000 chars later"
    document = make_document(text)

    design = RuleExtractor().extract_brief(document).design

    assert design is not None
    assert design.value == "cohort"


# --- MEASUREMENT: same dash defect as case_control, for cross_sectional's
# "cross[\\s-]*sectional" alternative. The en dash is typed literally.
def test_detects_cross_sectional_with_en_dash() -> None:
    document = make_document("Methods\nA cross–sectional survey was conducted.")

    assert RuleExtractor().extract_brief(document).design.value == "cross_sectional"


# --- Task 5: concept extraction (outcome/exposure/covariate). The rule
# engine leaves a field empty rather than guessing, so the third test below
# is as load-bearing as the first two: it checks that a sentence carrying
# NONE of the trigger patterns at all yields nothing. That is NOT the same
# claim as "a trigger word appearing in a sentence can never be mistaken for
# the document's own declaration" — a code-review round after this one
# measured concrete counterexamples (a trigger inside a citation, inside a
# stated limitation, inside a negated verb) and added guards for those
# specific, closed cases below; see the "Fix-round" tests further down.
# Guarding is NOT the same as a general classifier — untested phrasings of
# citation/negation are still unmeasured and may still false-fire.
def test_extracts_a_primary_outcome_concept() -> None:
    document = make_document(
        "Yöntem\nBirincil sonlanım 30 günlük mortalite olarak tanımlandı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [proposal.value for proposal in brief.outcome_concepts] == [
        "30 günlük mortalite"
    ]
    assert brief.outcome_concepts[0].evidence is not None


def test_extracts_a_covariate_list() -> None:
    document = make_document(
        "Yöntem\nModeller yaş, cinsiyet ve vücut kitle indeksi için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [proposal.value for proposal in brief.covariate_concepts] == [
        "yaş",
        "cinsiyet",
        "vücut kitle indeksi",
    ]


def test_a_sentence_without_a_concept_pattern_yields_nothing() -> None:
    document = make_document("Yöntem\nVeriler SPSS 26 ile analiz edildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.outcome_concepts == ()
    assert brief.covariate_concepts == ()


# --- Fix-round (code review of Task 5). Every fix below is governed by one
# ruling: when in doubt, emit nothing. A baseline that stays silent is
# useful; one that invents concepts is worse than none, because a wrong
# concept sends a variable into the wrong analytical role.


# CRITICAL, reviewer-reproduced: `_backward_span` had no bound at all — when
# no "." or "\n" preceded the trigger anywhere in the text, it fell back to
# `text[0:match.end()]`. The reviewer's repro: one long, delimiter-free
# sentence with a recruitment-site list produced 18 "covariates", including
# city names unrelated to the adjustment clause. Fixed by capping the scan
# at CONCEPT_MAX_CHARS * 4 chars (same bound the forward branch uses) and
# returning "" — not a wider fallback — when no delimiter is found inside
# that bound. The padding below pushes the trigger far enough past the only
# preceding delimiter ("\n" after "Yöntem") that it falls OUTSIDE the
# bounded window, so this exercises the "no delimiter inside the bound"
# branch specifically, not just "the window is smaller than before".
def test_backward_scan_is_bounded_and_yields_nothing_without_a_delimiter() -> None:
    cities = ", ".join(
        [
            "Ankara", "İzmir", "Bursa", "Antalya", "Konya", "Adana",
            "Gaziantep", "Mersin", "Kayseri", "Eskişehir", "Diyarbakır",
            "Samsun", "Denizli", "Şanlıurfa", "Malatya", "Erzurum", "Van",
            "Bolu", "Trabzon", "Sivas", "Kocaeli", "Manisa", "Aydın",
            "Balıkesir",
        ]
    )
    text = (
        f"Yöntem\nKatılımcılar {cities} illerinden çok merkezli olarak "
        "toplandı ve yaş için düzeltildi."
    )
    prefix = text[text.index("Katılımcılar") : text.index("için düzeltildi")]
    assert len(prefix) > 240, "prefix must exceed the backward-scan bound"
    document = make_document(text)

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


# IMPORTANT, reviewer-reproduced: `_concepts` had no negative-context guard,
# so a trigger word inside a CITATION to another study's finding was
# extracted as this study's own outcome. Same defect class as the citation
# bug already recorded in the DESIGN_PATTERNS comment (PMC12170779), now
# measured for concept extraction too. `_sentence_around` cannot be used to
# check for "ve ark." / "et al." here: the period inside the abbreviation
# "ark." is itself read as a sentence boundary, so the marker falls OUTSIDE
# the sentence text `_sentence_around` returns for the trigger appearing
# later in the same clause — see `_NEGATIVE_CONTEXT_WINDOW`'s comment.
def test_citation_sentence_does_not_yield_the_cited_studys_outcome() -> None:
    document = make_document(
        "Yöntem\nSmith ve ark. çalışmasında birincil sonlanım noktası 90 "
        "günlük mortalite olarak belirlenmişti. Biz ise hastane içi düşme "
        "oranını inceledik."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.outcome_concepts == ()


# IMPORTANT, reviewer-reproduced: a stated LIMITATION ("...için düzeltme
# YAPILAMAMIŞ olmasıdır" — adjustment for X could NOT be done) is
# semantically inverted from an adjustment being performed, but the old
# code had no way to tell the two apart and extracted a covariate from a
# sentence saying the opposite. `_NEGATIVE_CONTEXT` catches both the
# limitation marker ("kısıtlılığı") and the negated verb ("yapılamamış") in
# this one sentence; either alone would suppress the match.
def test_stated_limitation_does_not_yield_a_covariate() -> None:
    document = make_document(
        "Yöntem\nBu çalışmanın en önemli kısıtlılığı, olası karıştırıcı "
        "faktörlerin tümü için düzeltme yapılamamış olmasıdır."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


# Not on the reviewer's minimum required list, but confirmed by them as a
# real false fire — and one already flagged as an unmeasured risk in the
# original Task 5 report: a BARE adjustment verb with no "için" in front of
# it describes DATA CLEANING ("veri seti düzeltildi" = the dataset was
# corrected), not covariate adjustment. Fixed at the trigger itself
# (_ADJUSTMENT_VERB now requires "için" immediately before the verb) rather
# than via the negative-context guard, because this sentence carries none
# of the three closed guard markers — a narrowing of the pattern, not a
# widening, and one that also fixes it for any other bare-verb sentence,
# not just this one.
def test_data_cleaning_sentence_does_not_yield_a_covariate() -> None:
    document = make_document(
        "Yöntem\nAykırı değerler saptandıktan sonra veri seti düzeltildi "
        "ve analiz tekrarlandı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


# IMPORTANT, reviewer-reproduced: `_TRAILING`'s "olarak\s+\w+" alternative
# was unanchored, so it fired on the FIRST "olarak <word>" found anywhere in
# the candidate — here that is the CONNECTOR right after the trigger ("Ana
# çıktı OLARAK 30 günlük...", meaning "AS the main outcome, ..."), not the
# trailing "... olarak tanımlandı" clause it was written for. The unanchored
# version silently deleted "30" from the front of the value. Fixed by
# anchoring both non-punctuation alternatives to the string's end ($) and
# adding `_LEADING_SCAFFOLD` to strip the leading connector separately.
def test_leading_olarak_connector_does_not_swallow_the_number() -> None:
    document = make_document(
        "Yöntem\nAna çıktı olarak 30 günlük reamisyon oranı belirlendi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert len(brief.outcome_concepts) == 1
    assert brief.outcome_concepts[0].value.startswith("30")
    # NOT asserted: that the trailing bare verb ("belirlendi", with no
    # "olarak" directly before it) is stripped too — `_TRAILING` only
    # strips a trailing verb when "olarak" is directly adjacent to it, the
    # shape test_extracts_a_primary_outcome_concept covers. A closed list
    # of bare trailing verbs was out of scope for this fix; disclosed, not
    # silently hidden.


# IMPORTANT, reviewer-reproduced: "sonlanım noktası" (endpoint) is a very
# common three-word variant of "sonlanım" alone; the two-word form used in
# test_extracts_a_primary_outcome_concept hid this. Without a fix,
# "noktası" leaks into the front of the extracted value. `_LEADING_SCAFFOLD`
# strips it as a known scaffold word attached to the trigger, not the
# concept.
def test_three_word_sonlanim_noktasi_does_not_leak_noktasi() -> None:
    document = make_document(
        "Yöntem\nBirincil sonlanım noktası 30 günlük mortalite olarak "
        "tanımlandı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [p.value for p in brief.outcome_concepts] == ["30 günlük mortalite"]


# IMPORTANT, reviewer-reproduced: the bare "maruziyet" pattern matched
# inside the SUFFIXED form "maruziyeti" (stem + possessive/accusative "-i"),
# ending the match mid-word. The forward span then started on the leftover
# suffix fragment, producing "i değerlendirildi" as an "exposure concept" —
# garbage, not silence. Fixed with a `\b` word-boundary requirement right
# after the stem: "maruziyet" alone (followed by whitespace/punctuation)
# still fires; "maruziyeti"/"maruziyetin"/etc. now do not fire at all,
# which is correct here since there is no forward-extractable concept in
# this sentence anyway (the real subject, "hava kirliliği", precedes the
# trigger — a backward-word-order case this task does not attempt to
# solve for `exposure`, unlike it does for `covariate`).
def test_suffixed_maruziyeti_yields_nothing_rather_than_garbage() -> None:
    document = make_document("Yöntem\nHava kirliliği maruziyeti değerlendirildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.exposure_concepts == ()


# IMPORTANT, reviewer-reproduced (round 1). Round 1's fix for this was a
# STRUCTURAL rule (drop the backward span's first whitespace-separated
# token unconditionally, no subject check at all) rather than the original
# closed word list. "Çalışma" (study) was never in the closed list and this
# structural rule correctly dropped it anyway. Round 2 replaced that
# structural rule with `_drop_leading_subject`'s two-branch version (see
# rule.py) because the unconditional version invented wrong values on a
# different sentence shape — see
# test_unrecognized_leading_word_drops_the_whole_first_item_not_just_the_word
# below. "Çalışma" IS in `_ADJUSTMENT_SUBJECT_WORDS`, so this sentence still
# takes the "strip just the word" branch and the expected output is
# unchanged by the round-2 fix.
def test_adjustment_subject_beyond_the_closed_list_is_still_dropped() -> None:
    document = make_document(
        "Yöntem\nÇalışma yaş, cinsiyet ve sigara kullanımı için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [p.value for p in brief.covariate_concepts] == [
        "yaş",
        "cinsiyet",
        "sigara kullanımı",
    ]


# --- Fix-round 2 (code review of the round-1 fixes). Both residuals below
# were things already flagged as unmeasured risk in the round-1 report;
# the re-reviewer's own probe sentences measured them. Governing ruling is
# unchanged: when in doubt, emit nothing.


# IMPORTANT, re-reviewer-reproduced: round 1's `_LEADING_SUBJECT_TOKEN`
# dropped the backward span's first whitespace-separated token
# UNCONDITIONALLY, with no check for whether that token was actually a
# recognized subject word. "Vücut kitle indeksi" (BMI, one of the most
# common covariates in clinical data) has the identical surface shape as
# "Çalışma yaş" — both are whitespace-joined words with no comma before the
# next delimiter — so the unconditional rule severed it mid-term, turning
# it into ['kitle indeksi', 'yaş', 'cinsiyet']. "kitle indeksi" is not a
# term that exists: a WRONG value, not silence, which is strictly worse
# under this round's ruling than losing "vücut kitle indeksi" outright.
# `_drop_leading_subject` now discards the WHOLE first item instead of
# just its first word whenever the leading word is not a recognized
# subject — see rule.py for the two-branch rule and what it still loses on
# purpose (an item this shape LOSES ITS FIRST ENTRY ENTIRELY when it
# happens to open with an unrecognized word, even in the rare case that
# word really was a legitimate short covariate on its own — not measured
# how often that happens in practice).
def test_unrecognized_leading_word_drops_the_whole_first_item_not_just_the_word() -> None:
    document = make_document(
        "Yöntem\nVücut kitle indeksi, yaş ve cinsiyet için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [p.value for p in brief.covariate_concepts] == ["yaş", "cinsiyet"]
    assert "kitle indeksi" not in [p.value for p in brief.covariate_concepts]


# IMPORTANT, re-reviewer-reproduced: round 1's `_NEGATIVE_CONTEXT` caught
# the negated verb only as literal substrings ("yapılama", "düzeltileme",
# "edilmedi") — spellings, not a pattern. "-madı/-medi" (simple negation,
# definite past) is the standard Turkish negative past tense, more common
# in prose than the "-ama/-eme" (impossibility) forms the substring list
# happened to cover, and it was not one of the three literal spellings, so
# "yapılmadı" slipped through: the trigger's covariate pattern
# ("karıştırıcı") fired and the entire rest of the sentence, including the
# negation, was extracted as one garbage "covariate". Fixed by replacing
# the substring list with a stem+suffix pattern (yapıl-/edil-/düzeltil- +
# either negation form + either past-tense ending) — kept to those three
# stems, not generalized to all Turkish verbs.
def test_yapilmadi_negation_does_not_yield_a_covariate() -> None:
    document = make_document(
        "Yöntem\nYaş, cinsiyet ve BKİ potansiyel karıştırıcı faktörlerdi "
        "ancak hiçbir düzeltme yapılmadı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()
