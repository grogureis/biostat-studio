"""Behavioral coverage for concept-to-column matching."""

from __future__ import annotations

from biostat_service.extractors.contracts import ColumnSummary
from biostat_service.extractors.matching import best_column, normalize, similarity


def _columns(*names: str) -> tuple[ColumnSummary, ...]:
    return tuple(
        ColumnSummary(name=name, kind="continuous", unique_values=9, non_missing=90)
        for name in names
    )


def test_turkish_folding_survives_dotted_capital_i() -> None:
    assert normalize("İlaç Dozu") == normalize("ilac_dozu")


def test_separators_and_case_do_not_change_a_label() -> None:
    assert normalize("Sistolik KB") == normalize("sistolik kb")
    assert normalize("HbA1c") == normalize("hba1c")


def test_an_abbreviation_matches_its_spelled_out_column() -> None:
    columns = _columns("sistolik_kan_basinci", "yas", "cinsiyet")
    match = best_column("sistolik KB", columns)
    assert match is not None
    assert match[0] == "sistolik_kan_basinci"


def test_an_unrelated_concept_matches_nothing() -> None:
    assert best_column("serum kreatinin", _columns("yas", "cinsiyet")) is None


# --- Code review round 1: a containment floor (0.85 for substring overlap)
# was tried and MEASURED as a false-positive source against real clinical
# column names, then removed from `similarity`. These pin the removal so it
# is not reintroduced in good faith; see the comment in matching.py for the
# full measured list (this covers a representative sample, not all of it).
def test_short_stem_containment_does_not_imply_a_match() -> None:
    assert best_column("yaş", _columns("yasam_suresi")) is None  # age vs survival time
    assert best_column("hasta", _columns("hastane_kodu")) is None  # patient vs hospital code
    assert best_column("kan", _columns("kanser_tanisi")) is None  # blood vs cancer diagnosis


def test_containment_polarity_is_not_confused_with_a_match() -> None:
    # "smoking" is a substring of "nonsmoking_status" — the removed
    # containment floor scored this 0.85, binding a concept to a column
    # whose value means the OPPOSITE of the concept.
    assert best_column("smoking", _columns("nonsmoking_status")) is None


def test_ties_break_alphabetically_for_determinism() -> None:
    # A genuine tie ABOVE MATCH_THRESHOLD: two distinct column names that
    # normalize to the identical key (normalize() folds case away) score
    # exactly 1.0 against the same concept. Regression, code review round 1:
    # the previous version of this test tied on two columns that both
    # scored BELOW threshold, so both calls returned None and the assertion
    # passed as `None == None` without ever reaching the sort's tie-break —
    # this version forces a real tie through it, in both input orders.
    forward = _columns("HASTA_YASI", "hasta_yasi")
    backward = _columns("hasta_yasi", "HASTA_YASI")

    first = best_column("hasta yaşı", forward)
    second = best_column("hasta yaşı", backward)

    assert first == second == ("HASTA_YASI", 1.0)


def test_similarity_is_symmetric_enough_to_be_stable() -> None:
    assert similarity("yaş", "yas") > 0.9
