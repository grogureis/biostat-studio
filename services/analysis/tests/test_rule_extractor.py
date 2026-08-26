"""Behavioral coverage for the deterministic rule-based extractor."""

from __future__ import annotations

from biostat_service.extractors.contracts import BriefProposal, ColumnSummary, Proposal
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


# --- Fix-round 5 (code review of the round-4 removal): the forward
# covariate path had NO positive regression test. Every covariate
# assertion in this file, after round 4, asserted silence — meaning a
# future change that broke forward extraction (the path round 4 explicitly
# kept working) would pass the whole suite silently. A capability with no
# positive test is a capability that can die quietly.
#
# Both tests below assert what the code ACTUALLY does today, not what it
# ideally should — pinning an ideal would fail immediately and invite
# widening a pattern just to satisfy the test, which is exactly backwards.


def test_english_adjusted_for_list_is_extracted() -> None:
    """The forward covariate path's baseline positive case: concepts
    follow the trigger ("adjusted for X, Y, and Z"), unaffected by the
    verb-final removal in round 4.
    """
    document = make_document(
        "Methods\nModels were adjusted for age, sex, and BMI."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [p.value for p in brief.covariate_concepts] == ["age", "sex", "BMI"]


def test_turkish_kovaryat_olarak_list_is_extracted_with_known_trailing_verb_residue() -> None:
    """Turkish forward covariate reading: "kovaryat" precedes the list
    here ("kovaryat OLARAK yaş, cinsiyet ve sigara kullanımı alındı" =
    "age, sex, and smoking status were taken AS covariates"), unlike the
    verb-final construction round 4 removed.

    PINS REALITY, NOT THE IDEAL: the last item comes out as "sigara
    kullanımı alındı" — the trailing verb "alındı" ("were taken") is
    glued on, not "sigara kullanımı" alone. This is the KNOWN, PARKED
    trailing-bare-verb gap (`_TRAILING` only strips a trailing verb when
    "olarak" is directly adjacent to it, not a bare verb like "alındı" at
    the end of a list) — parked for the whole-branch review, not fixed
    here. Do not "fix" this test by widening `_TRAILING` or adding
    "alındı" to some verb list; that decision belongs to the parked
    whole-branch pass, alongside the English confounder stem-glue defect
    and the other parked minors.
    """
    document = make_document(
        "Yöntem\nKovaryat olarak yaş, cinsiyet ve sigara kullanımı alındı."
    )

    brief = RuleExtractor().extract_brief(document)

    assert [p.value for p in brief.covariate_concepts] == [
        "yaş",
        "cinsiyet",
        "sigara kullanımı alındı",
    ]


def _concept(value: str) -> Proposal:
    return Proposal(value=value, confidence=0.7, source="rule")


def test_match_variables_higher_score_wins_over_earlier_claim() -> None:
    """Regression, code review round 1 on Task 6.

    Before the fix, the FIRST concept to claim a column kept it regardless
    of score: an outcome concept scanned first could plant a merely-close
    match ("sistolik kan basınc", missing the final vowel, scoring ~0.971)
    and a later, EXACT covariate match for the same column ("sistolik KB",
    scoring 1.0 via the abbreviation table) was silently dropped —
    publishing the weaker match's evidence sentence under the wrong role.
    The higher score must win regardless of which role reached the column
    first.
    """
    document = make_document("irrelevant for match_variables")
    concepts = BriefProposal(
        outcome_concepts=(_concept("sistolik kan basınc"),),
        covariate_concepts=(_concept("sistolik KB"),),
    )
    columns = (
        ColumnSummary(
            name="sistolik_kan_basinci",
            kind="continuous",
            unique_values=50,
            non_missing=100,
        ),
    )

    result = RuleExtractor().match_variables(document, concepts, columns)

    assert len(result) == 1
    assert result[0].column == "sistolik_kan_basinci"
    assert result[0].role.value == "covariate"
    assert result[0].role.confidence == 1.0


def test_match_variables_equal_score_falls_back_to_role_priority() -> None:
    """When two concepts score IDENTICALLY for the same column, the
    outcome -> exposure -> covariate scan order breaks the tie: outcome
    (scanned first) keeps its claim over a same-scoring covariate. This is
    the one case where scan order still matters after the higher-score-wins
    fix above.
    """
    document = make_document("irrelevant for match_variables")
    concepts = BriefProposal(
        outcome_concepts=(_concept("sistolik KB"),),
        covariate_concepts=(_concept("sistolik KB"),),
    )
    columns = (
        ColumnSummary(
            name="sistolik_kan_basinci",
            kind="continuous",
            unique_values=50,
            non_missing=100,
        ),
    )

    result = RuleExtractor().match_variables(document, concepts, columns)

    assert len(result) == 1
    assert result[0].role.value == "outcome"


# --- Task 7: kind iddiası (doküman kaynaklı kategorik düzeltme) ---


def _stage_column(**overrides: object) -> ColumnSummary:
    defaults: dict[str, object] = dict(
        name="evre", kind="continuous", unique_values=4, non_missing=100
    )
    defaults.update(overrides)
    return ColumnSummary(**defaults)  # type: ignore[arg-type]


def test_kind_claim_fires_when_the_columns_own_name_carries_classification_language() -> (
    None
):
    """The minimal positive case: the column's bare name, followed by a
    sentence that carries CATEGORICAL_CLAIM language, produces a kind
    proposal — with no role concept involved at all.
    """
    document = make_document(
        "Yöntem\nHastalar evre I-IV olarak sınıflandırıldı."
    )

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(),)
    )

    assert len(result) == 1
    assert result[0].column == "evre"
    assert result[0].role is None
    assert result[0].kind is not None
    assert result[0].kind.value == "categorical"
    assert result[0].kind.source == "rule"
    assert "sınıflandırıldı" in result[0].kind.evidence.lower()


def test_kind_claim_merges_onto_an_existing_role_proposal_for_the_same_column() -> None:
    """Role and kind are independently optional (contracts.py docstring) —
    when a concept match already claimed this column for a role, the kind
    claim must be ADDED to that same RoleProposal, not silently dropped or
    published as a second, conflicting entry for the same column.
    """
    document = make_document(
        "Yöntem\nBirincil sonlanım evre olarak belirlendi. "
        "Hastalar evre I-IV olarak sınıflandırıldı."
    )
    concepts = BriefProposal(outcome_concepts=(_concept("evre"),))
    columns = (_stage_column(),)

    result = RuleExtractor().match_variables(document, concepts, columns)

    assert len(result) == 1
    assert result[0].column == "evre"
    assert result[0].role is not None
    assert result[0].role.value == "outcome"
    assert result[0].kind is not None
    assert result[0].kind.value == "categorical"


def test_kind_claim_ignores_a_sentence_about_a_different_variable() -> None:
    """The column's name appears in the text, but ITS OWN sentence carries
    no classification language — a classification sentence about a
    different variable, isolated from it by a period, must not leak over
    and produce a claim for this column.
    """
    document = make_document(
        "Yöntem\nHastalar yaş gruplarına göre kategorize edildi. "
        "Evre TNM sistemine göre kaydedildi."
    )

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(),)
    )

    assert result == ()


def test_kind_claim_does_not_fire_from_a_cited_studys_classification() -> None:
    """Same false-fire class as CONCEPT_PATTERNS (see _NEGATIVE_CONTEXT):
    a classification stated about ANOTHER study's cohort is not this
    study's own statement about the column.
    """
    document = make_document(
        "Yöntem\nSmith ve ark. çalışmasında hastalar evre I-IV olarak "
        "sınıflandırılmıştı."
    )

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(),)
    )

    assert result == ()


def test_kind_claim_does_not_fire_from_a_stated_limitation() -> None:
    """A limitation sentence typically describes something that was NOT
    done, or done informally — not this study's own method statement."""
    document = make_document(
        "Yöntem\nÇalışmanın bir kısıtlılığı, evre bilgisinin standart bir "
        "sınıflandırma sistemine göre kaydedilmemiş olmasıdır."
    )

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(),)
    )

    assert result == ()


def test_kind_claim_requires_the_bare_column_name_not_a_suffixed_turkish_form() -> None:
    """KNOWN, ACCEPTED SCOPE LIMIT — read before widening the match.

    Turkish is agglutinative: "evre" + the dative suffix "-sine" glues into
    one token, "evresine", with no word boundary between the stem and the
    suffix for a plain regex to find. A prefix match (`evre\\w*`) would
    catch this, but it would ALSO catch unrelated words that happen to
    start with the same stem — "evrensel" ("universal"), "evrimsel"
    ("evolutionary") — which is exactly the class of false positive this
    engine treats as worse than staying silent (spec §5). So the match is
    exact-word-only, and this real, common phrasing is a miss:
    the column is simply not reachable through this sentence, the same
    accepted-narrowness shape as Task 6's yaş/hastanin_yasi finding.
    """
    document = make_document(
        "Yöntem\nHastalar TNM evresine göre I-IV olarak sınıflandırıldı."
    )

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(),)
    )

    assert result == ()


def test_kind_claim_is_silent_when_the_column_name_never_appears() -> None:
    document = make_document("Yöntem\nHastalar yaşa göre iki gruba ayrıldı.")

    result = RuleExtractor().match_variables(
        document, BriefProposal(), (_stage_column(name="merkez_no"),)
    )

    assert result == ()
