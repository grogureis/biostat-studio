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
    pair_id: str | None = None,
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
        "pair_id_variable": pair_id,
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


def test_confirmed_kind_override_drives_planning_and_is_recorded() -> None:
    """Rejecting an explicit kind correction leaves mixed-type columns impossible to resolve."""
    profile = core_profile()
    profile.variables["age_years"] = metadata(
        "age_years", "categorical", unique_values=10, non_missing=10, missing=2
    )
    selected_roles = roles(outcome_kind="continuous")

    plan = build_plan(brief(), profile, selected_roles)

    assert plan.blocking_errors == []
    assert plan.items[-1].method == "welch_t_test"
    assert "approved_kind_override:age_years:categorical:continuous" in plan.warnings


def test_every_plan_output_contract_includes_effect_size_ci_table_and_figure() -> None:
    """Dropping uncertainty or a required artifact would produce incomplete reporting."""
    plan = build_plan(brief(), core_profile(), roles())

    for item in plan.items:
        assert any(output.startswith("effect_size:") for output in item.outputs)
        assert "confidence_interval:95_percent" in item.outputs
        assert any(output.startswith("table:") for output in item.outputs)
        assert any(output.startswith("figure:") for output in item.outputs)


def test_welch_anova_contract_names_the_verified_omnibus_effect() -> None:
    """A pooled omega-squared label would not match unequal-variance execution."""
    profile = core_profile()
    profile.variables["treatment_group"] = metadata(
        "treatment_group", "categorical", unique_values=3
    )
    selected_roles = roles()
    selected_roles["treatment_group"] = VariableRole(
        name="treatment_group",
        role="exposure",
        kind="categorical",
        confirmed=True,
    )

    plan = build_plan(brief(), profile, selected_roles)

    assert plan.items[-1].method == "welch_anova"
    assert "effect_size:welch_cohen_f_squared" in plan.items[-1].outputs
    assert all("omega_squared" not in output for output in plan.items[-1].outputs)


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


def profile_with_continuous_exposure() -> DataProfile:
    profile = core_profile()
    profile.variables["baseline_score"] = metadata(
        "baseline_score", "continuous", unique_values=12
    )
    return profile


def roles_with_pair_id(
    *, outcome: str = "age_years", outcome_kind: str = "continuous"
) -> dict[str, VariableRole]:
    selected = roles(outcome=outcome, outcome_kind=outcome_kind)
    selected["participant_id"] = VariableRole(
        name="participant_id",
        role="pair_id",
        kind="identifier-candidate",
        confirmed=True,
    )
    return selected


@pytest.mark.parametrize(
    ("outcome", "outcome_kind", "covariates", "expected_error"),
    [
        ("age_years", "continuous", ["event_30d"], "unsupported_repeated_adjustment"),
        ("event_30d", "binary", [], "unsupported_repeated_outcome"),
    ],
)
def test_unverified_repeated_models_block_before_ordinary_regression(
    outcome: str,
    outcome_kind: str,
    covariates: list[str],
    expected_error: str,
) -> None:
    """Ordinary regression would ignore within-subject dependence."""
    selected_roles = roles_with_pair_id(
        outcome=outcome, outcome_kind=outcome_kind
    )
    for covariate in covariates:
        selected_roles[covariate] = VariableRole(
            name=covariate,
            role="covariate",
            kind=core_profile().variables[covariate].kind,
            confirmed=True,
        )

    plan = build_plan(
        brief(
            design="repeated",
            outcome=outcome,
            covariates=covariates,
            pair_id="participant_id",
        ),
        core_profile(),
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == [expected_error]


@pytest.mark.parametrize(
    ("pair_id", "selected_roles", "expected_error"),
    [
        (None, roles(), "missing_pair_id_variable"),
        ("missing_id", roles(), "unknown_pair_id_variable:missing_id"),
        ("age_years", roles(), "invalid_pair_id_variable:age_years"),
        ("treatment_group", roles(), "invalid_pair_id_variable:treatment_group"),
        (
            "participant_id",
            {
                **roles(),
                "participant_id": VariableRole(
                    name="participant_id",
                    role="pair_id",
                    kind="identifier-candidate",
                    confirmed=False,
                ),
            },
            "unconfirmed_pair_id_variable:participant_id",
        ),
    ],
)
def test_paired_plan_requires_distinct_confirmed_pair_identifier(
    pair_id: str | None,
    selected_roles: dict[str, VariableRole],
    expected_error: str,
) -> None:
    """A paired method is unexecutable without confirmed subject linkage."""
    plan = build_plan(
        brief(design="repeated", pair_id=pair_id),
        core_profile(),
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == [expected_error]


def test_simple_paired_plan_includes_pair_identifier_and_structure_check() -> None:
    """Dropping the pair identifier or two-condition check would unpair execution."""
    plan = build_plan(
        brief(design="repeated", pair_id="participant_id"),
        core_profile(),
        roles_with_pair_id(),
    )

    assert plan.blocking_errors == []
    assert [item.method for item in plan.items] == [
        "descriptive_summary",
        "paired_t_test",
    ]
    assert all("participant_id" in item.required_variables for item in plan.items)
    assert any(
        "exactly two observations, one per confirmed condition, for each pair"
        in assumption
        for assumption in plan.items[-1].assumptions
    )


def test_paired_plan_rejects_multiple_confirmed_pair_identifiers() -> None:
    """Ambiguous subject linkage must not select one identifier by dictionary order."""
    profile = core_profile()
    profile.variables["household_id"] = metadata(
        "household_id", "identifier-candidate", unique_values=12
    )
    selected_roles = roles_with_pair_id()
    selected_roles["household_id"] = VariableRole(
        name="household_id",
        role="pair_id",
        kind="identifier-candidate",
        confirmed=True,
    )

    plan = build_plan(
        brief(design="repeated", pair_id="participant_id"),
        profile,
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == ["multiple_pair_id_variables"]


def test_paired_plan_requires_exactly_two_confirmed_condition_levels() -> None:
    """A one-level condition cannot produce within-pair differences."""
    profile = core_profile()
    profile.variables["treatment_group"] = metadata(
        "treatment_group", "binary", unique_values=1
    )

    plan = build_plan(
        brief(design="repeated", pair_id="participant_id"),
        profile,
        roles_with_pair_id(),
    )

    assert plan.items == []
    assert plan.blocking_errors == ["unsupported_repeated_design"]


def test_repeated_subject_identifier_may_have_categorical_profile_kind() -> None:
    """Repeated subject IDs naturally need not infer as unique identifier candidates."""
    profile = core_profile()
    profile.variables["participant_id"] = metadata(
        "participant_id", "categorical", unique_values=6
    )
    selected_roles = roles()
    selected_roles["participant_id"] = VariableRole(
        name="participant_id",
        role="pair_id",
        kind="categorical",
        confirmed=True,
    )

    plan = build_plan(
        brief(design="repeated", pair_id="participant_id"),
        profile,
        selected_roles,
    )

    assert plan.blocking_errors == []
    assert plan.items[-1].method == "paired_t_test"


def test_unadjusted_logistic_regression_is_not_labeled_adjusted() -> None:
    """Calling a one-predictor model adjusted misstates its estimand and effect."""
    profile = profile_with_continuous_exposure()
    selected_roles = roles(outcome="event_30d", outcome_kind="binary")
    selected_roles["baseline_score"] = VariableRole(
        name="baseline_score",
        role="exposure",
        kind="continuous",
        confirmed=True,
    )
    plan = build_plan(
        brief(
            outcome="event_30d",
            exposures=["baseline_score"],
            covariates=[],
        ),
        profile,
        selected_roles,
    )

    item = plan.items[-1]
    assert item.method == "logistic_regression"
    assert "Unadjusted association" in item.estimand
    assert "unadjusted" in item.rationale
    assert "effect_size:unadjusted_odds_ratio" in item.outputs
    assert "adjusted" not in " ".join([item.estimand, item.rationale]).lower().replace(
        "unadjusted", ""
    )


def test_regression_with_covariates_retains_adjusted_contract() -> None:
    """Removing adjustment labeling would misstate a covariate-adjusted model."""
    plan = build_plan(
        brief(covariates=["event_30d"]),
        core_profile(),
        roles(),
    )

    item = plan.items[-1]
    assert item.method == "linear_regression"
    assert "Adjusted association" in item.estimand
    assert "effect_size:adjusted_regression_coefficient" in item.outputs


def test_covariates_without_a_primary_exposure_fail_closed() -> None:
    """A covariate must not silently become the primary reported effect."""
    selected_roles = {
        "age_years": VariableRole(
            name="age_years", role="outcome", kind="continuous", confirmed=True
        ),
        "event_30d": VariableRole(
            name="event_30d", role="covariate", kind="binary", confirmed=True
        ),
    }

    plan = build_plan(
        brief(exposures=[], covariates=["event_30d"]),
        core_profile(),
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == ["covariates_without_exposure"]


def test_adjusted_multilevel_primary_exposure_fails_closed() -> None:
    """The result contract cannot truthfully reduce several primary contrasts to one."""
    profile = core_profile()
    profile.variables["treatment_group"] = metadata(
        "treatment_group", "categorical", unique_values=3
    )
    selected_roles = {
        "age_years": VariableRole(
            name="age_years", role="outcome", kind="continuous", confirmed=True
        ),
        "treatment_group": VariableRole(
            name="treatment_group",
            role="exposure",
            kind="categorical",
            confirmed=True,
        ),
        "event_30d": VariableRole(
            name="event_30d", role="covariate", kind="binary", confirmed=True
        ),
    }

    plan = build_plan(
        brief(covariates=["event_30d"]),
        profile,
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == ["multilevel_exposure_adjustment_unsupported"]


def test_multiple_exposures_fail_closed_without_multiplicity_contract() -> None:
    """An unspecified primary contrast must not be labeled as a single analysis."""
    profile = profile_with_continuous_exposure()
    selected_roles = roles()
    selected_roles["baseline_score"] = VariableRole(
        name="baseline_score",
        role="exposure",
        kind="continuous",
        confirmed=True,
    )

    plan = build_plan(
        brief(exposures=["treatment_group", "baseline_score"]),
        profile,
        selected_roles,
    )

    assert plan.items == []
    assert plan.blocking_errors == ["multiple_exposures_unsupported"]


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


def test_method_override_selects_the_documented_alternative() -> None:
    """A confirmed alternative selection must swap the executable method contract."""
    plan = build_plan(
        brief(),
        core_profile(),
        roles(),
        method_overrides={"primary_outcome": "mann_whitney_u"},
    )

    assert plan.blocking_errors == []
    primary = plan.items[-1]
    assert primary.method == "mann_whitney_u"
    assert primary.robust_alternative == "welch_t_test"
    assert "effect_size:rank_biserial_r" in primary.outputs
    assert "Hodges" in primary.estimand
    assert any("tie" in assumption.lower() for assumption in primary.assumptions)


def test_method_override_to_the_primary_method_is_identity() -> None:
    """Re-selecting the already-planned method must not change the plan."""
    baseline = build_plan(brief(), core_profile(), roles())
    unchanged = build_plan(
        brief(),
        core_profile(),
        roles(),
        method_overrides={"primary_outcome": "welch_t_test"},
    )

    assert unchanged == baseline


def test_method_override_outside_the_documented_pair_fails_closed() -> None:
    """Free method selection would bypass the deterministic planning rules."""
    plan = build_plan(
        brief(),
        core_profile(),
        roles(),
        method_overrides={"primary_outcome": "logistic_regression"},
    )

    assert plan.items == []
    assert plan.blocking_errors == ["invalid_method_override:primary_outcome"]

    unknown_item = build_plan(
        brief(),
        core_profile(),
        roles(),
        method_overrides={"secondary_outcome": "mann_whitney_u"},
    )
    assert unknown_item.items == []
    assert unknown_item.blocking_errors == ["unknown_override_item:secondary_outcome"]


def test_kruskal_override_carries_the_holm_multiplicity_contract() -> None:
    """Pairwise post-hoc contrasts require an explicit adjustment strategy."""
    profile = core_profile()
    profile.variables["treatment_group"] = metadata(
        "treatment_group", "categorical", unique_values=3
    )
    selected_roles = roles()
    selected_roles["treatment_group"] = VariableRole(
        name="treatment_group", role="exposure", kind="categorical", confirmed=True
    )

    plan = build_plan(
        brief(),
        profile,
        selected_roles,
        method_overrides={"primary_outcome": "kruskal_wallis"},
    )

    primary = plan.items[-1]
    assert primary.method == "kruskal_wallis"
    assert primary.robust_alternative == "welch_anova"
    assert primary.multiplicity_strategy == "dunn_pairwise_holm_adjusted"
    assert "effect_size:rank_epsilon_squared" in primary.outputs
    assert "table:multi_group_comparison_with_posthoc" in primary.outputs
    assert "confidence_interval:not_available_rank_epsilon_squared" in primary.outputs
    assert "confidence_interval:95_percent" not in primary.outputs


def test_pearson_choice_documents_spearman_alternative_and_override() -> None:
    """The correlation rule must document and accept the rank-based alternative."""
    profile = profile_with_continuous_exposure()
    selected_roles = roles()
    selected_roles["baseline_score"] = VariableRole(
        name="baseline_score", role="exposure", kind="continuous", confirmed=True
    )

    documented = build_plan(
        brief(exposures=["baseline_score"]), profile, selected_roles
    )
    assert documented.items[-1].method == "pearson_or_spearman"
    assert documented.items[-1].robust_alternative == "spearman_rank"

    overridden = build_plan(
        brief(exposures=["baseline_score"]),
        profile,
        selected_roles,
        method_overrides={"primary_outcome": "spearman_rank"},
    )
    primary = overridden.items[-1]
    assert primary.method == "spearman_rank"
    assert primary.robust_alternative == "pearson_or_spearman"
    assert "effect_size:spearman_rho" in primary.outputs


def test_wilcoxon_override_keeps_pair_variables_and_paired_contract() -> None:
    """The paired rank alternative must keep pair linkage requirements intact."""
    plan = build_plan(
        brief(design="repeated", pair_id="participant_id"),
        core_profile(),
        roles_with_pair_id(),
        method_overrides={"primary_outcome": "wilcoxon_signed_rank"},
    )

    primary = plan.items[-1]
    assert primary.method == "wilcoxon_signed_rank"
    assert primary.robust_alternative == "paired_t_test"
    assert "participant_id" in primary.required_variables
    assert "effect_size:matched_rank_biserial_r" in primary.outputs
    assert any("zero" in assumption.lower() for assumption in primary.assumptions)


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
