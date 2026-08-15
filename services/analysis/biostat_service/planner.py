"""Deterministic analysis planning from confirmed structured study metadata."""

from __future__ import annotations

from collections.abc import Iterable

from biostat_service.contracts import AnalysisPlan, PlanItem, StudyBrief, VariableRole
from biostat_service.data_intake import DataProfile
from biostat_service.study_model import (
    BlockingPlanError,
    PLAN_VERSION,
    PlanChoice,
    SUPPORTED_STUDY_DESIGNS,
)


GROUP_RULES: dict[tuple[str, int, bool], PlanChoice] = {
    ("continuous", 2, False): PlanChoice("welch_t_test", "mann_whitney_u"),
    ("continuous", 2, True): PlanChoice(
        "paired_t_test", "wilcoxon_signed_rank"
    ),
    ("continuous", 3, False): PlanChoice("welch_anova", "kruskal_wallis"),
    ("binary", 2, False): PlanChoice("chi_square_or_fisher"),
}
ANALYTIC_KINDS = frozenset({"binary", "categorical", "continuous"})


def choose_group_method(outcome_kind: str, groups: int, paired: bool) -> PlanChoice:
    """Choose one explicit group-comparison rule or fail closed."""
    key = (outcome_kind, 3 if groups > 2 else groups, paired)
    try:
        return GROUP_RULES[key]
    except KeyError as exc:
        raise BlockingPlanError("unsupported_or_unconfirmed_design") from exc


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _profile_warnings(profile: DataProfile) -> list[str]:
    return [
        f"data_profile:{warning.code}:{warning.column or 'dataset'}"
        for warning in profile.warnings
    ]


def _validate_role(
    variable: str,
    expected_role: str,
    profile: DataProfile,
    roles: dict[str, VariableRole],
) -> tuple[str | None, str | None]:
    metadata = profile.variables.get(variable)
    if metadata is None:
        return None, f"unknown_variable:{variable}"

    selected = roles.get(variable)
    if selected is None or not selected.confirmed:
        return None, f"unconfirmed_{expected_role}:{variable}"
    if selected.name != variable or selected.role != expected_role:
        return None, f"invalid_{expected_role}_role:{variable}"
    if selected.kind != metadata.kind:
        return None, f"{expected_role}_kind_mismatch:{variable}"
    if selected.kind not in ANALYTIC_KINDS:
        return None, f"unsupported_{expected_role}_kind:{variable}"
    return selected.kind, None


def _validate_pair_id(
    brief: StudyBrief,
    profile: DataProfile,
    roles: dict[str, VariableRole],
) -> str | None:
    pair_id = brief.pair_id_variable
    if pair_id is None:
        return "missing_pair_id_variable"
    if pair_id in brief.outcome_variables or pair_id in brief.exposure_variables:
        return f"invalid_pair_id_variable:{pair_id}"

    metadata = profile.variables.get(pair_id)
    if metadata is None:
        return f"unknown_pair_id_variable:{pair_id}"
    selected = roles.get(pair_id)
    if selected is None or not selected.confirmed:
        return f"unconfirmed_pair_id_variable:{pair_id}"
    if selected.name != pair_id or selected.role not in {"pair_id", "subject_id"}:
        return f"invalid_pair_id_role:{pair_id}"
    if selected.kind != metadata.kind or selected.kind in {"date", "empty"}:
        return f"invalid_pair_id_kind:{pair_id}"

    confirmed_pair_ids = [
        role.name
        for role in roles.values()
        if role.confirmed and role.role in {"pair_id", "subject_id"}
    ]
    if confirmed_pair_ids != [pair_id]:
        return "multiple_pair_id_variables"
    return None


def _descriptive_item(
    variables: list[str], warnings: list[str]
) -> PlanItem:
    return PlanItem(
        id="descriptive_summary",
        estimand=(
            "Distribution, completeness, and uncertainty of the confirmed analysis "
            "variables."
        ),
        method="descriptive_summary",
        rationale=(
            "Summarize the confirmed analysis variables before inferential analysis; "
            "research-question prose does not determine this method."
        ),
        required_variables=variables,
        assumptions=[
            "Variable roles and measurement kinds remain as confirmed in this plan version.",
            "Report denominators and missingness for every summary without imputing values.",
        ],
        robust_alternative=None,
        multiplicity_strategy="not_applicable",
        outputs=[
            "effect_size:standardized_descriptive_estimate",
            "confidence_interval:95_percent",
            "table:descriptive_summary",
            "figure:distribution_overview",
        ],
        warnings=warnings,
    )


def _method_contract(
    choice: PlanChoice, *, adjusted: bool
) -> dict[str, object]:
    contracts: dict[str, dict[str, object]] = {
        "welch_t_test": {
            "estimand": "Difference in outcome means between the two independent groups.",
            "rationale": (
                "Welch's t test estimates an independent two-group mean difference "
                "without requiring equal group variances."
            ),
            "assumptions": [
                "Observations are independent within and between confirmed groups.",
                "Check missingness, outcome scale, distribution shape, and influential outliers.",
                "Use the robust alternative only when distribution, outliers, scale, and estimand support it; a normality p-value alone is insufficient.",
            ],
            "effect": "hedges_g_and_mean_difference",
            "table": "two_group_comparison",
            "figure": "group_distribution_and_effect",
        },
        "paired_t_test": {
            "estimand": "Mean within-pair difference in the confirmed continuous outcome.",
            "rationale": (
                "The repeated design requires a paired analysis of within-pair differences."
            ),
            "assumptions": [
                "Pairs are correctly linked and independent of other pairs.",
                "Confirm exactly two observations, one per confirmed condition, for each pair.",
                "Check missing pairs, difference scale, distribution shape, and influential outliers.",
                "Use the robust alternative only when distribution, outliers, scale, and estimand support it; a normality p-value alone is insufficient.",
            ],
            "effect": "paired_standardized_mean_difference",
            "table": "paired_comparison",
            "figure": "paired_difference_and_effect",
        },
        "welch_anova": {
            "estimand": "Difference in outcome means across the confirmed independent groups.",
            "rationale": (
                "Welch's ANOVA compares more than two independent groups without an "
                "equal-variance requirement."
            ),
            "assumptions": [
                "Observations are independent within and between confirmed groups.",
                "Check missingness, outcome scale, group distributions, and influential outliers.",
                "Use the robust alternative only when distribution, outliers, scale, and estimand support it; a normality p-value alone is insufficient.",
            ],
            "effect": "omega_squared",
            "table": "multi_group_comparison",
            "figure": "group_distribution_and_effect",
        },
        "chi_square_or_fisher": {
            "estimand": "Association between the confirmed binary outcome and group variables.",
            "rationale": (
                "Use Pearson's chi-square when expected-cell conditions hold and Fisher's "
                "exact test otherwise."
            ),
            "assumptions": [
                "Observations are independent and categories are mutually exclusive.",
                "Check sparse and zero cells before choosing chi-square or Fisher's exact calculation.",
            ],
            "effect": "odds_ratio_and_phi",
            "table": "categorical_association",
            "figure": "categorical_effect",
        },
        "pearson_or_spearman": {
            "estimand": "Strength and direction of association between two continuous variables.",
            "rationale": (
                "Choose Pearson or Spearman within the registered method from confirmed "
                "scale, estimand, distribution shape, and outlier checks, never from a "
                "normality p-value alone."
            ),
            "assumptions": [
                "Observations are paired by row and independent across rows.",
                "Check linearity or monotonicity, scale, missingness, distribution shape, and influential outliers.",
            ],
            "effect": "correlation_coefficient",
            "table": "correlation_estimate",
            "figure": "association_scatter",
        },
        "linear_regression": {
            "estimand": (
                f"{'Adjusted' if adjusted else 'Unadjusted'} association with the "
                "confirmed continuous outcome."
            ),
            "rationale": (
                f"A single continuous outcome with an {'adjusted' if adjusted else 'unadjusted'} "
                "confirmed predictor contract requires a linear regression model."
            ),
            "assumptions": [
                "Check linearity, residual distribution, heteroscedasticity, collinearity, and influential observations.",
                "Report heteroscedasticity-consistent uncertainty when diagnostics require it.",
            ],
            "effect": (
                "adjusted_regression_coefficient"
                if adjusted
                else "unadjusted_regression_coefficient"
            ),
            "table": "linear_model_coefficients",
            "figure": (
                "adjusted_effects_and_diagnostics"
                if adjusted
                else "unadjusted_effect_and_diagnostics"
            ),
        },
        "logistic_regression": {
            "estimand": (
                f"{'Adjusted' if adjusted else 'Unadjusted'} association with the "
                "confirmed binary outcome."
            ),
            "rationale": (
                f"A single binary outcome with an {'adjusted' if adjusted else 'unadjusted'} "
                "confirmed predictor contract requires a logistic regression model."
            ),
            "assumptions": [
                "Check outcome coding, separation, sparse data, continuous-predictor linearity on the logit scale, collinearity, and influence.",
                "Escalate separation or non-convergence as an execution error rather than changing the estimand silently.",
            ],
            "effect": "adjusted_odds_ratio" if adjusted else "unadjusted_odds_ratio",
            "table": "logistic_model_coefficients",
            "figure": (
                "adjusted_odds_ratios_and_diagnostics"
                if adjusted
                else "unadjusted_odds_ratio_and_diagnostics"
            ),
        },
    }
    return contracts[choice.method]


def _inferential_item(
    choice: PlanChoice,
    variables: list[str],
    warnings: list[str],
    *,
    adjusted: bool,
) -> PlanItem:
    contract = _method_contract(choice, adjusted=adjusted)
    return PlanItem(
        id="primary_outcome",
        estimand=str(contract["estimand"]),
        method=choice.method,
        rationale=str(contract["rationale"]),
        required_variables=variables,
        assumptions=list(contract["assumptions"]),
        robust_alternative=choice.robust_alternative,
        multiplicity_strategy="not_applicable_single_primary_analysis",
        outputs=[
            f"effect_size:{contract['effect']}",
            "confidence_interval:95_percent",
            f"table:{contract['table']}",
            f"figure:{contract['figure']}",
        ],
        warnings=warnings,
    )


def _primary_choice(
    brief: StudyBrief,
    profile: DataProfile,
    outcome_kind: str,
    exposure_kinds: list[str],
) -> PlanChoice | None:
    exposures = brief.exposure_variables
    covariates = brief.covariates
    predictors = len(exposures) + len(covariates)
    if predictors == 0:
        return None

    if len(exposures) > 1:
        raise BlockingPlanError("multiple_exposures_unsupported")

    if brief.design == "repeated":
        if covariates:
            raise BlockingPlanError("unsupported_repeated_adjustment")
        if len(exposures) != 1:
            raise BlockingPlanError("unsupported_repeated_design")
        if outcome_kind != "continuous":
            raise BlockingPlanError("unsupported_repeated_outcome")
        if exposure_kinds != ["binary"]:
            raise BlockingPlanError("unsupported_repeated_design")
        if profile.variables[exposures[0]].unique_values != 2:
            raise BlockingPlanError("unsupported_repeated_design")
        return choose_group_method(outcome_kind, 2, paired=True)

    if covariates:
        if outcome_kind == "continuous":
            return PlanChoice("linear_regression")
        if outcome_kind == "binary":
            return PlanChoice("logistic_regression")
        raise BlockingPlanError("unsupported_or_unconfirmed_design")

    exposure = exposures[0]
    exposure_kind = exposure_kinds[0]
    if exposure_kind in {"binary", "categorical"}:
        groups = profile.variables[exposure].unique_values
        return choose_group_method(outcome_kind, groups, paired=False)
    if exposure_kind == "continuous" and outcome_kind == "continuous":
        return PlanChoice("pearson_or_spearman")
    if exposure_kind == "continuous" and outcome_kind == "binary":
        return PlanChoice("logistic_regression")
    raise BlockingPlanError("unsupported_or_unconfirmed_design")


def build_plan(
    brief: StudyBrief,
    profile: DataProfile,
    roles: dict[str, VariableRole],
) -> AnalysisPlan:
    """Build a versioned plan without inferring methods from free text."""
    warnings = _profile_warnings(profile)
    blocking_errors: list[str] = []

    if brief.design not in SUPPORTED_STUDY_DESIGNS:
        blocking_errors.append("unsupported_or_unconfirmed_design")
    if len(brief.outcome_variables) != 1:
        blocking_errors.append("unsupported_outcome_count")

    outcome_kind: str | None = None
    if len(brief.outcome_variables) == 1:
        outcome_kind, error = _validate_role(
            brief.outcome_variables[0], "outcome", profile, roles
        )
        if error is not None:
            blocking_errors.append(error)

    exposure_kinds: list[str] = []
    for exposure in brief.exposure_variables:
        kind, error = _validate_role(exposure, "exposure", profile, roles)
        if error is not None:
            blocking_errors.append(error)
        elif kind is not None:
            exposure_kinds.append(kind)
    for covariate in brief.covariates:
        _, error = _validate_role(covariate, "covariate", profile, roles)
        if error is not None:
            blocking_errors.append(error)

    if len(brief.exposure_variables) > 1:
        blocking_errors.append("multiple_exposures_unsupported")

    if brief.design == "repeated":
        repeated_structure_supported = not blocking_errors
        if brief.covariates:
            blocking_errors.append("unsupported_repeated_adjustment")
            repeated_structure_supported = False
        if len(brief.exposure_variables) != 1:
            if len(brief.exposure_variables) <= 1:
                blocking_errors.append("unsupported_repeated_design")
            repeated_structure_supported = False
        if outcome_kind is not None and outcome_kind != "continuous":
            blocking_errors.append("unsupported_repeated_outcome")
            repeated_structure_supported = False
        if exposure_kinds and exposure_kinds != ["binary"]:
            blocking_errors.append("unsupported_repeated_design")
            repeated_structure_supported = False
        if (
            len(brief.exposure_variables) == 1
            and exposure_kinds == ["binary"]
            and profile.variables[brief.exposure_variables[0]].unique_values != 2
        ):
            blocking_errors.append("unsupported_repeated_design")
            repeated_structure_supported = False
        if repeated_structure_supported:
            pair_error = _validate_pair_id(brief, profile, roles)
            if pair_error is not None:
                blocking_errors.append(pair_error)

    if blocking_errors:
        return AnalysisPlan(
            version=PLAN_VERSION,
            blocking_errors=_ordered_unique(blocking_errors),
            warnings=warnings,
        )

    variables = _ordered_unique(
        brief.outcome_variables + brief.exposure_variables + brief.covariates
    )
    if brief.design == "repeated" and brief.pair_id_variable is not None:
        variables.append(brief.pair_id_variable)
    try:
        choice = _primary_choice(brief, profile, outcome_kind or "", exposure_kinds)
    except BlockingPlanError as exc:
        return AnalysisPlan(
            version=PLAN_VERSION,
            blocking_errors=[str(exc)],
            warnings=warnings,
        )

    items = [_descriptive_item(variables, warnings)]
    if choice is not None:
        items.append(
            _inferential_item(
                choice,
                variables,
                warnings,
                adjusted=bool(brief.covariates),
            )
        )
    return AnalysisPlan(version=PLAN_VERSION, items=items, warnings=warnings)
