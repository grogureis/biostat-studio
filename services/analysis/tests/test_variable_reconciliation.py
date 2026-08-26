"""Behavioral coverage for data-versus-document conflict detection."""

from __future__ import annotations

from biostat_service.data_intake import DataProfile, VariableMetadata
from biostat_service.extractors.contracts import Proposal, RoleProposal
from biostat_service.variable_reconciliation import detect_conflicts


def _profile(kind: str) -> DataProfile:
    return DataProfile(
        source_path=__import__("pathlib").Path("unused.xlsx"),
        source_sha256="a" * 64,
        sheets=("Analysis",),
        selected_sheet="Analysis",
        rows=100,
        columns=1,
        missing_cells=0,
        variables={
            "evre": VariableMetadata(
                source_label="evre",
                original_name="evre",
                display_name="Evre",
                kind=kind,
                non_missing=100,
                missing=0,
                unique_values=4,
            )
        },
        warnings=(),
    )


def _categorical_claim() -> tuple[RoleProposal, ...]:
    return (
        RoleProposal(
            column="evre",
            kind=Proposal(
                value="categorical",
                confidence=0.7,
                source="rule",
                evidence="Hastalar TNM evresine göre I-IV olarak sınıflandırıldı.",
                evidence_offset=120,
            ),
        ),
    )


def test_numeric_column_claimed_categorical_is_a_conflict() -> None:
    conflicts = detect_conflicts(_profile("continuous"), _categorical_claim())
    assert len(conflicts) == 1
    assert conflicts[0].column == "evre"
    assert conflicts[0].data_kind == "continuous"
    assert conflicts[0].document_kind == "categorical"
    assert conflicts[0].evidence is not None


def test_agreement_is_not_a_conflict() -> None:
    assert detect_conflicts(_profile("categorical"), _categorical_claim()) == ()


def test_the_document_may_not_turn_a_category_into_a_measurement() -> None:
    claim = (
        RoleProposal(
            column="evre",
            kind=Proposal(value="continuous", confidence=0.9, source="rule"),
        ),
    )
    assert detect_conflicts(_profile("categorical"), claim) == ()
