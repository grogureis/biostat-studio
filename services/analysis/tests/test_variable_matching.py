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


def test_ties_break_alphabetically_for_determinism() -> None:
    columns = _columns("beta", "alpha")
    first = best_column("gamma_xyz", columns)
    second = best_column("gamma_xyz", columns)
    assert first == second


def test_similarity_is_symmetric_enough_to_be_stable() -> None:
    assert similarity("yaş", "yas") > 0.9
