"""Behavioral coverage for data-versus-document conflict detection."""

from __future__ import annotations

from pathlib import Path

from biostat_service.contracts import StudyBrief, VariableRole
from biostat_service.data_intake import DataProfile, VariableMetadata
from biostat_service.extractors.contracts import Proposal, RoleProposal
from biostat_service.variable_reconciliation import detect_conflicts, price_conflicts


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


def _profile_with_outcome() -> DataProfile:
    return DataProfile(
        source_path=Path("unused.xlsx"),
        source_sha256="a" * 64,
        sheets=("Analysis",),
        selected_sheet="Analysis",
        rows=100,
        columns=2,
        missing_cells=0,
        variables={
            "evre": VariableMetadata(
                source_label="evre",
                original_name="evre",
                display_name="Evre",
                kind="continuous",
                non_missing=100,
                missing=0,
                unique_values=4,
            ),
            "sonuc": VariableMetadata(
                source_label="sonuc",
                original_name="sonuc",
                display_name="Sonuç",
                kind="continuous",
                non_missing=100,
                missing=0,
                unique_values=80,
            ),
        },
        warnings=(),
    )


def _brief() -> StudyBrief:
    return StudyBrief(
        title="Evre ve sağkalım",
        question="Evre ile sonuç arasında ilişki var mı?",
        hypothesis="İleri evre daha kötü sonuçla ilişkilidir.",
        design="cohort",
        outcome_variables=["sonuc"],
        exposure_variables=["evre"],
    )


def _unconfirmed_roles() -> dict[str, VariableRole]:
    return {
        "sonuc": VariableRole(
            name="sonuc", role="outcome", kind="continuous", confirmed=False
        ),
        "evre": VariableRole(
            name="evre", role="exposure", kind="continuous", confirmed=False
        ),
    }


def test_the_two_choices_are_priced_by_the_planner_itself() -> None:
    profile = _profile_with_outcome()
    roles = _unconfirmed_roles()
    conflicts = detect_conflicts(profile, _categorical_claim())

    costs = price_conflicts(_brief(), profile, roles, conflicts)

    assert len(costs) == 1
    cost = costs[0]
    assert cost.methods_if_document == ("descriptive_summary", "welch_anova")
    assert cost.methods_if_data == (
        "descriptive_summary",
        "pearson_or_spearman",
    )
    assert cost.blocked_if_document == ()
    assert cost.blocked_if_data == ()


def test_pricing_never_mutates_or_confirms_the_caller_roles() -> None:
    profile = _profile_with_outcome()
    roles = _unconfirmed_roles()
    snapshot = {name: role.model_copy(deep=True) for name, role in roles.items()}

    price_conflicts(
        _brief(), profile, roles, detect_conflicts(profile, _categorical_claim())
    )

    assert roles == snapshot
    assert all(role.confirmed is False for role in roles.values())
