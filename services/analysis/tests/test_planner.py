"""Decision-boundary coverage for deterministic analysis planning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from biostat_service.contracts import StudyBrief, VariableRole
from biostat_service.data_intake import DataProfile, DataWarning, VariableMetadata
from biostat_service.planner import build_plan, choose_group_method
from biostat_service.study_model import (
    BlockingPlanError,
    VERTICAL_SLICE_METHOD_IDS,
)


REFERENCE_PLAN = (
    Path(__file__).resolve().parents[3] / "tests" / "reference" / "core-study.json"
)


@pytest.mark.parametrize(
    ("outcome_kind", "groups", "paired", "expected", "alternative"),
    [
        ("continuous", 2, False, "welch_t_test", "mann_whitney_u"),
        ("continuous", 2, True, "paired_t_test", "wilcoxon_signed_rank"),
        ("continuous", 3, False, "welch_anova", "kruskal_wallis"),
        ("binary", 2, False, "chi_square_or_fisher", None),
    ],
)
def test_primary_group_comparison_rule(
    outcome_kind: str,
    groups: int,
    paired: bool,
    expected: str,
    alternative: str | None,
) -> None:
    """Changing a decision-table branch must select the documented method pair."""
    choice = choose_group_method(outcome_kind, groups, paired)

    assert choice.method == expected
    assert choice.robust_alternative == alternative


@pytest.mark.parametrize(
    ("outcome_kind", "groups", "paired"),
    [
        ("continuous", 1, False),
        ("binary", 3, False),
        ("categorical", 2, True),
        ("unknown", 2, False),
    ],
)
def test_unsupported_group_rule_blocks_instead_of_guessing(
    outcome_kind: str, groups: int, paired: bool
) -> None:
    """A permissive fallback would turn incomplete metadata into a guessed test."""
    with pytest.raises(BlockingPlanError, match="unsupported_or_unconfirmed_design"):
        choose_group_method(outcome_kind, groups, paired)


def metadata(
    name: str,
    kind: str,
    *,
    unique_values: int,
    non_missing: int = 12,
    missing: int = 0,
) -> VariableMetadata:
    return VariableMetadata(
        source_label=name,
        original_name=name,
        display_name=name.replace("_", " ").capitalize(),
        kind=kind,
        non_missing=non_missing,
        missing=missing,
        unique_values=unique_values,
    )


def core_profile(*, warning: DataWarning | None = None) -> DataProfile:
    return DataProfile(
        source_path=Path("/not-serialized/core-study.xlsx"),
        source_sha256="a" * 64,
        sheets=("Analysis",),
        selected_sheet="Analysis",
        rows=12,
        columns=5,
        missing_cells=2,
        variables={
            "participant_id": metadata(
                "participant_id", "identifier-candidate", unique_values=12
            ),
            "treatment_group": metadata(
                "treatment_group", "binary", unique_values=2
            ),
            "age_years": metadata(
                "age_years",
                "continuous",
                unique_values=10,
                non_missing=10,
                missing=2,
            ),
            "event_30d": metadata("event_30d", "binary", unique_values=2),
            "visit_date": metadata("visit_date", "date", unique_values=12),
        },
        warnings=() if warning is None else (warning,),
    )


def brief(
    *,
    design: str = "cohort",
    outcome: str = "age_years",
    exposures: list[str] | None = None,
    covariates: list[str] | None = None,
    question: str = "Does treatment differ in the confirmed outcome?",
    hypothesis: str = "The confirmed groups differ.",
) -> StudyBrief:
    values = {
        "title": "Core study",
        "question": question,
        "hypothesis": hypothesis,
        "design": design,
        "outcome_variables": [outcome],
        "exposure_variables": ["treatment_group"] if exposures is None else exposures,
        "covariates": [] if covariates is None else covariates,
        "language": "en",
    }
    if design in {"cross_sectional", "cohort", "case_control", "trial", "repeated"}:
        return StudyBrief(**values)
    return StudyBrief.model_construct(**values)


def roles(
    *, outcome: str = "age_years", outcome_kind: str = "continuous"
) -> dict[str, VariableRole]:
    selected = {
        outcome: VariableRole(
            name=outcome, role="outcome", kind=outcome_kind, confirmed=True
        ),
    }
    if outcome != "treatment_group":
        selected["treatment_group"] = VariableRole(
            name="treatment_group", role="exposure", kind="binary", confirmed=True
        )
    if outcome != "event_30d":
        selected["event_30d"] = VariableRole(
            name="event_30d", role="covariate", kind="binary", confirmed=True
        )
    return selected


def test_core_plan_matches_value_free_deterministic_snapshot() -> None:
    """Plan drift, nondeterminism, or row-value serialization must break approval."""
    plan = build_plan(brief(), core_profile(), roles())
    serialized = plan.model_dump(mode="json")

    assert serialized == json.loads(REFERENCE_PLAN.read_text(encoding="utf-8"))
    assert "patient-" not in json.dumps(serialized)
    assert [item.id for item in plan.items] == [
        "descriptive_summary",
        "primary_outcome",
    ]
    assert [item.method for item in plan.items] == [
        "descriptive_summary",
        "welch_t_test",
    ]


def test_every_plan_output_contract_includes_effect_size_ci_table_and_figure() -> None:
    """Dropping uncertainty or a required artifact would produce incomplete reporting."""
    plan = build_plan(brief(), core_profile(), roles())

    for item in plan.items:
        assert any(output.startswith("effect_size:") for output in item.outputs)
        assert "confidence_interval:95_percent" in item.outputs
        assert any(output.startswith("table:") for output in item.outputs)
        assert any(output.startswith("figure:") for output in item.outputs)


def test_planner_and_audit_share_one_method_identifier_registry() -> None:
    """A planner-only method identifier would be rejected by the audit boundary."""
    plan = build_plan(brief(), core_profile(), roles())
    planned_ids = {
        identifier
        for item in plan.items
        for identifier in (item.method, item.robust_alternative)
        if identifier is not None
    }

    assert planned_ids <= VERTICAL_SLICE_METHOD_IDS


@pytest.mark.parametrize(
    ("outcome", "outcome_kind", "exposure", "covariates", "expected"),
    [
        ("event_30d", "binary", "treatment_group", [], "chi_square_or_fisher"),
        ("age_years", "continuous", "treatment_group", ["event_30d"], "linear_regression"),
        ("event_30d", "binary", "treatment_group", ["age_years"], "logistic_regression"),
    ],
)
def test_verified_non_group_rules_are_deterministic(
    outcome: str,
    outcome_kind: str,
    exposure: str,
    covariates: list[str],
    expected: str,
) -> None:
    """Wrong type or adjustment branching must not silently change the primary method."""
    selected_roles = roles(outcome=outcome, outcome_kind=outcome_kind)
    selected_roles[exposure] = VariableRole(
        name=exposure,
        role="exposure",
        kind=core_profile().variables[exposure].kind,
        confirmed=True,
    )
    for covariate in covariates:
        selected_roles[covariate] = VariableRole(
            name=covariate,
            role="covariate",
            kind=core_profile().variables[covariate].kind,
            confirmed=True,
        )

    plan = build_plan(
        brief(outcome=outcome, exposures=[exposure], covariates=covariates),
        core_profile(),
        selected_roles,
    )

    assert plan.blocking_errors == []
    assert plan.items[-1].method == expected


def test_two_confirmed_continuous_variables_plan_correlation() -> None:
    """Treating a continuous exposure as a group would choose the wrong estimand."""
    profile = core_profile()
    profile.variables["baseline_score"] = metadata(
        "baseline_score", "continuous", unique_values=12
    )
    selected_roles = roles()
    selected_roles["baseline_score"] = VariableRole(
        name="baseline_score",
        role="exposure",
        kind="continuous",
        confirmed=True,
    )

    plan = build_plan(
        brief(exposures=["baseline_score"]),
        profile,
        selected_roles,
    )

    assert plan.blocking_errors == []
    assert plan.items[-1].method == "pearson_or_spearman"


def test_confirmed_continuous_outcome_without_predictors_gets_descriptive_plan() -> None:
    """A descriptive objective must not acquire an inferential method from free text."""
    plan = build_plan(
        brief(exposures=[], question="Please run an ANOVA anyway."),
        core_profile(),
        roles(),
    )

    assert [item.method for item in plan.items] == ["descriptive_summary"]


@pytest.mark.parametrize(
    ("invalid_brief", "selected_roles", "expected_error"),
    [
        (brief(design="unknown"), roles(), "unsupported_or_unconfirmed_design"),
        (
            brief(),
            {
                **roles(),
                "age_years": VariableRole(
                    name="age_years",
                    role="outcome",
                    kind="continuous",
                    confirmed=False,
                ),
            },
            "unconfirmed_outcome:age_years",
        ),
    ],
)
def test_unknown_design_or_unconfirmed_outcome_returns_blocking_plan(
    invalid_brief: StudyBrief,
    selected_roles: dict[str, VariableRole],
    expected_error: str,
) -> None:
    """Unknown structure must produce a blocking error and no guessed analysis."""
    plan = build_plan(invalid_brief, core_profile(), selected_roles)

    assert expected_error in plan.blocking_errors
    assert plan.items == []


def test_free_text_cannot_change_a_confirmed_structured_decision() -> None:
    """Question wording alone must never override the confirmed design and roles."""
    first = build_plan(brief(), core_profile(), roles())
    second = build_plan(
        brief(
            question="Use a chi-square test because the investigator requested it.",
            hypothesis="This prose asks for regression instead.",
        ),
        core_profile(),
        roles(),
    )

    assert first == second


def test_profile_warnings_are_propagated_without_patient_row_values() -> None:
    """Warnings must remain actionable without copying source-cell values into a plan."""
    profile = core_profile(
        warning=DataWarning(
            code="duplicated_identifier",
            column="participant_id",
            message="Identifier-labelled column contains duplicates.",
        )
    )

    plan = build_plan(brief(), profile, roles())

    assert plan.warnings == ["data_profile:duplicated_identifier:participant_id"]
    assert "patient-" not in json.dumps(plan.model_dump(mode="json"))
