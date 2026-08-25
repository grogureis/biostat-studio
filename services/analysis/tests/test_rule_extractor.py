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




def test_a_sentence_without_a_concept_pattern_yields_nothing() -> None:
    document = make_document("Yöntem\nVeriler SPSS 26 ile analiz edildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.outcome_concepts == ()
    assert brief.covariate_concepts == ()


# --- Fix-round (code review of Task 5). Every fix below is governed by one
# ruling: when in doubt, emit nothing. A baseline that stays silent is
# useful; one that invents concepts is worse than none, because a wrong
# concept sends a variable into the wrong analytical role.


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
# this one sentence; either alone would suppress the match. This test
# exercises the FORWARD covariate trigger "karıştırıcı" and the
# negative-context guard, both untouched by the round-4 removal below —
# see that section's intro comment for what forward/backward means here.
def test_stated_limitation_does_not_yield_a_covariate() -> None:
    document = make_document(
        "Yöntem\nBu çalışmanın en önemli kısıtlılığı, olası karıştırıcı "
        "faktörlerin tümü için düzeltme yapılamamış olmasıdır."
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
# trigger).
def test_suffixed_maruziyeti_yields_nothing_rather_than_garbage() -> None:
    document = make_document("Yöntem\nHava kirliliği maruziyeti değerlendirildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.exposure_concepts == ()


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
# stems, not generalized to all Turkish verbs. This test exercises the
# FORWARD covariate trigger "karıştırıcı", untouched by the round-4
# removal below.
def test_yapilmadi_negation_does_not_yield_a_covariate() -> None:
    document = make_document(
        "Yöntem\nYaş, cinsiyet ve BKİ potansiyel karıştırıcı faktörlerdi "
        "ancak hiçbir düzeltme yapılmadı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


# --- Fix-round 4 (code review of the round-3 fix): the verb-final backward
# covariate path is REMOVED, not patched a fifth time.
#
# Rounds 1-3 each replaced the previous mechanism for locating where a
# Turkish subject ends before a backward-parsed covariate list (a bounded
# window, a closed subject-word list, a structural first-token drop, a
# two-branch subject rule, a comma-only rule — four distinct mechanisms
# across those rounds; see rule.py's CONCEPT_PATTERNS comment for the full
# account with all four counterexamples). Round 3's own author, probing the
# comma-only rule before reporting it done, found a FIFTH counterexample —
# a multi-comma appositive ("Model, çok değişkenli lojistik regresyon, yaş
# ve cinsiyet için düzeltildi.") that invents "çok değişkenli lojistik
# regresyon" as a covariate — and stopped instead of patching around it, as
# instructed. The conclusion: a regex cannot reliably find where a Turkish
# subject ends. The verb-final trigger ("X, Y için düzeltildi") is deleted
# from CONCEPT_PATTERNS entirely; `_backward_span` and the backward/forward
# branch in `_concepts` are deleted with it.
#
# This is NOT the removal of covariate extraction. Every FORWARD covariate
# trigger — where the concept follows the trigger rather than precedes it —
# is untouched and still works: "kovaryat", "covariates", "adjusted for",
# "karıştırıcı", "confounder" (see test_stated_limitation_does_not_yield_a_
# covariate and test_yapilmadi_negation_does_not_yield_a_covariate above,
# both still exercising a forward trigger + the negative-context guard).
# outcome_concepts and exposure_concepts were never part of this defect
# class either.
#
# The tests below convert six historical counterexamples (rounds 1-3's
# findings, plus the multi-comma appositive that ended the attempt) into
# regression pins for the new silence. If a future change starts extracting
# from a verb-final sentence again, one of these should fail and force that
# change through review rather than landing quietly.


def test_verb_final_covariate_list_yields_nothing() -> None:
    """Was test_extracts_a_covariate_list (Task 5's original positive
    test) through round 3, where it asserted ["cinsiyet", "vücut kitle
    indeksi"] — round 3's comma-only rule dropping "Modeller yaş" as one
    unbroken run before the first comma. Round 4 removes the verb-final
    path entirely, so this sentence now yields nothing at all.
    """
    document = make_document(
        "Yöntem\nModeller yaş, cinsiyet ve vücut kitle indeksi için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_unlisted_subject_yields_nothing() -> None:
    """Was test_adjustment_subject_beyond_the_closed_list_is_still_dropped
    (round 1), which pinned that an unlisted subject word ("Çalışma") did
    not get special leniency. That distinction no longer exists — no
    subject word, listed or not, is ever stripped, because the whole
    verb-final trigger no longer matches.
    """
    document = make_document(
        "Yöntem\nÇalışma yaş, cinsiyet ve sigara kullanımı için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_compound_first_item_yields_nothing() -> None:
    """Was test_unrecognized_leading_word_drops_the_whole_first_item_not_
    just_the_word (round 2): "vücut kitle indeksi" (BMI) as the first,
    comma-free item. Round 1's unconditional first-token drop severed it
    into the invented term "kitle indeksi" — the defect that started this
    whole chain of fixes. Now the sentence yields nothing, so there is
    nothing left to sever.
    """
    document = make_document(
        "Yöntem\nVücut kitle indeksi, yaş ve cinsiyet için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_recognized_subject_word_yields_nothing() -> None:
    """Was test_recognized_subject_word_no_longer_gets_special_treatment
    (round 3): "Model" was in round 2's closed subject-word list, so only
    "Model" got stripped and "performansı" (part of the same compound
    subject, "the model's performance") was kept as an invented covariate.
    """
    document = make_document(
        "Yöntem\nModel performansı, yaş ve cinsiyet için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_ve_joined_subject_yields_nothing() -> None:
    """Was test_ve_joined_subject_is_not_mistaken_for_the_item_boundary
    (round 3): round 2's discard-whole-item branch fell back to "ve"/"ile"
    to find the item boundary, but those words can appear INSIDE the
    subject itself ("Hasta ve hekim değerlendirmesi" = "the patient's and
    physician's assessment"), so it stopped mid-subject and invented
    "hekim değerlendirmesi" as a covariate.
    """
    document = make_document(
        "Yöntem\nHasta ve hekim değerlendirmesi, yaş ve cinsiyet için "
        "düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_no_subject_yields_nothing() -> None:
    """Was test_first_item_before_the_first_comma_is_always_lost_even_
    with_no_subject (round 3): round 3's comma-only rule always discarded
    the text before the first comma, even here where there was no subject
    at all and "yaş" was a real, standalone covariate — a known, disclosed
    loss at the time. Round 4 makes the whole sentence yield nothing
    rather than just its first item.
    """
    document = make_document("Yöntem\nYaş, cinsiyet ve BKİ için düzeltildi.")

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()


def test_verb_final_with_appositive_after_subject_yields_nothing() -> None:
    """THE finding that ended the four-round attempt: round 3's own
    author probed the comma-only rule (per explicit instruction, before
    declaring it done) and found that a comma-separated appositive right
    after the subject — "Model, [çok değişkenli lojistik regresyon],
    yaş ve cinsiyet için düzeltildi." — got the FIRST comma right but not
    the SECOND: "çok değişkenli lojistik regresyon" (describing the model
    type, not a covariate) was invented as one. Reported instead of
    patched, per instruction: "a measured 'the rule engine cannot do
    this' is worth more than a fourth patch." This is the sentence that
    made the removal decision, not just one more counterexample among the
    others in this section.
    """
    document = make_document(
        "Yöntem\nModel, çok değişkenli lojistik regresyon, yaş ve cinsiyet "
        "için düzeltildi."
    )

    brief = RuleExtractor().extract_brief(document)

    assert brief.covariate_concepts == ()
    assert "çok değişkenli lojistik regresyon" not in [
        p.value for p in brief.covariate_concepts
    ]
