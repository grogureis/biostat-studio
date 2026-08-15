"""Deterministic execution of approved statistical analysis plans.

Hypothesis tests and model fits delegate to SciPy or statsmodels.  The small
formulae implemented here are estimands, confidence intervals, and effect-size
standardisation that those libraries do not expose as one stable result object.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from hashlib import sha256
import platform
import warnings as python_warnings

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
import scipy
from scipy import stats
import statsmodels
import statsmodels.api as sm
from statsmodels.stats.oneway import (
    anova_oneway,
    confint_effectsize_oneway,
    effectsize_oneway,
)

from biostat_service.contracts import (
    AnalysisPlan,
    AnalysisProvenance,
    AnalysisResult,
    ConfidenceInterval,
    EffectSize,
    PlanItem,
)


CONFIDENCE_LEVEL = 0.95
ALPHA = 1.0 - CONFIDENCE_LEVEL
ALTERNATIVE_METADATA_ONLY = frozenset(
    {"mann_whitney_u", "wilcoxon_signed_rank", "kruskal_wallis"}
)


class AnalysisExecutionError(ValueError):
    """A stable, value-free failure at the approved-plan execution boundary."""

    def __init__(
        self, message: str, *, warnings: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__(message)
        self.warnings = list(warnings or [])


class AnalysisBundle(BaseModel):
    """A result collection with bundle-level reproducibility metadata."""

    results: dict[str, AnalysisResult]
    reproducibility: dict[str, str] = Field(min_length=1)
    provenance: AnalysisProvenance
    warnings: list[dict[str, str]] = Field(default_factory=list)


class _ExecutionContext:
    def __init__(
        self,
        *,
        fingerprint: str,
        plan_version: int,
        versions: dict[str, str],
    ) -> None:
        self.fingerprint = fingerprint
        self.plan_version = plan_version
        self.versions = versions


Executor = Callable[[pd.DataFrame, PlanItem, _ExecutionContext], AnalysisResult]


def runtime_versions() -> dict[str, str]:
    """Return path-free versions of every runtime used for scientific results."""
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
    }


def _data_fingerprint(frame: pd.DataFrame) -> str:
    """Hash values and scientific dtype metadata independently of row order."""
    if frame.columns.has_duplicates:
        raise AnalysisExecutionError("duplicate_column_names")
    ordered_columns = sorted(frame.columns, key=lambda value: f"{type(value).__name__}:{value!s}")
    canonical = frame.loc[:, ordered_columns]
    try:
        row_hashes = pd.util.hash_pandas_object(canonical, index=False, categorize=True)
    except (TypeError, ValueError) as exc:
        raise AnalysisExecutionError("unhashable_input_values") from exc
    digest = sha256()
    digest.update(str(canonical.shape).encode("utf-8"))
    for column in ordered_columns:
        digest.update(f"{type(column).__name__}:{column!s}\0".encode("utf-8"))
        series = canonical[column]
        digest.update(
            f"dtype:{type(series.dtype).__name__}:{series.dtype!s}\0".encode("utf-8")
        )
        if isinstance(series.dtype, pd.CategoricalDtype):
            digest.update(f"ordered:{series.dtype.ordered}\0".encode("utf-8"))
            categories = pd.Index(series.dtype.categories)
            digest.update(
                f"category_dtype:{categories.dtype!s};count:{len(categories)}\0".encode(
                    "utf-8"
                )
            )
            category_hashes = pd.util.hash_pandas_object(
                categories, index=False, categorize=False
            )
            digest.update(category_hashes.to_numpy(dtype=np.uint64).tobytes())
    digest.update(np.sort(row_hashes.to_numpy(dtype=np.uint64)).tobytes())
    return digest.hexdigest()


def _safe_float(value: object, code: str) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalysisExecutionError(code) from exc
    if not np.isfinite(converted):
        raise AnalysisExecutionError(code)
    return converted


def _p_value(value: object) -> float:
    p_value = _safe_float(value, "non_finite_p_value")
    if not 0.0 <= p_value <= 1.0:
        raise AnalysisExecutionError("invalid_p_value")
    return p_value


def _sort_key(value: object) -> str:
    return f"{type(value).__name__}:{value!s}"


def _levels(series: pd.Series, *, expected: int | None = None) -> tuple[list[object], str]:
    values = series.dropna()
    if isinstance(series.dtype, pd.CategoricalDtype) and series.dtype.ordered:
        present = set(values.tolist())
        levels = [level for level in series.dtype.categories if level in present]
        strategy = "ordered_categorical"
    else:
        levels = sorted(values.unique().tolist(), key=_sort_key, reverse=True)
        strategy = "deterministic_descending"
    if expected is not None and len(levels) != expected:
        raise AnalysisExecutionError(f"expected_{expected}_levels")
    return levels, strategy


def _required_variables(item: PlanItem, minimum: int, *, maximum: int | None = None) -> list[str]:
    variables = list(item.required_variables)
    if len(variables) < minimum or (maximum is not None and len(variables) > maximum):
        raise AnalysisExecutionError(f"invalid_required_variables:{item.method}")
    if len(set(variables)) != len(variables):
        raise AnalysisExecutionError(f"duplicate_required_variables:{item.method}")
    return variables


def _complete_case(
    frame: pd.DataFrame,
    variables: Sequence[str],
    *,
    numeric: Sequence[str] = (),
) -> tuple[pd.DataFrame, dict[str, int], list[str]]:
    missing_columns = [name for name in variables if name not in frame.columns]
    if missing_columns:
        raise AnalysisExecutionError(f"unknown_required_variable:{missing_columns[0]}")

    selected = frame.loc[:, list(variables)].copy()
    for name in variables:
        series = selected[name]
        if pd.api.types.is_numeric_dtype(series):
            observed = series.dropna().to_numpy(dtype=float)
            if observed.size and not np.isfinite(observed).all():
                raise AnalysisExecutionError(f"non_finite_input:{name}")
    for name in numeric:
        try:
            converted = pd.to_numeric(selected[name], errors="raise")
        except (TypeError, ValueError) as exc:
            raise AnalysisExecutionError(f"invalid_numeric_input:{name}") from exc
        observed = converted.dropna().to_numpy(dtype=float)
        if observed.size and not np.isfinite(observed).all():
            raise AnalysisExecutionError(f"non_finite_input:{name}")
        selected[name] = converted

    complete = selected.dropna(axis=0, how="any")
    if not complete.empty:
        ordering = pd.util.hash_pandas_object(complete, index=False, categorize=True)
        complete = complete.iloc[np.argsort(ordering.to_numpy(), kind="stable")].reset_index(drop=True)
    counts = {
        "input": int(len(frame)),
        "used": int(len(complete)),
        "missing": int(len(frame) - len(complete)),
    }
    exclusions = [
        f"complete_case:input={counts['input']};used={counts['used']};missing={counts['missing']}"
    ]
    return complete, counts, exclusions


def _provenance(
    context: _ExecutionContext,
    exclusions: list[str],
    transformations: list[str],
) -> AnalysisProvenance:
    return AnalysisProvenance(
        data_fingerprint=context.fingerprint,
        plan_version=context.plan_version,
        exclusions=exclusions,
        transformations=transformations,
        random_seed=None,
        library_versions=context.versions,
    )


def _validate_finite_payload(value: object, path: str) -> None:
    """Reject non-finite numeric publication fields at the central boundary."""
    if value is None or isinstance(value, (str, bytes, bool)):
        return
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            raise AnalysisExecutionError(f"non_finite_result:{path}")
        return
    if isinstance(value, (int, np.integer)):
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite_payload(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple, np.ndarray)):
        for index, nested in enumerate(value):
            _validate_finite_payload(nested, f"{path}.{index}")


def _result(
    *,
    item: PlanItem,
    context: _ExecutionContext,
    n: int,
    estimate: float | None,
    p_value: float | None,
    interval: tuple[float | None, float | None],
    effect_name: str,
    effect_value: float | None,
    diagnostics: dict[str, object],
    exclusions: list[str],
    transformations: list[str],
    warnings: list[str] | None = None,
) -> AnalysisResult:
    _validate_finite_payload(estimate, "estimate")
    _validate_finite_payload(p_value, "p_value")
    if p_value is not None:
        _p_value(p_value)
    _validate_finite_payload(interval[0], "confidence_interval.lower")
    _validate_finite_payload(interval[1], "confidence_interval.upper")
    _validate_finite_payload(effect_value, "effect_size.value")
    _validate_finite_payload(diagnostics, "diagnostics")
    return AnalysisResult(
        id=item.id,
        method=item.method,
        n=n,
        estimate=estimate,
        p_value=p_value,
        confidence_interval=ConfidenceInterval(
            level=CONFIDENCE_LEVEL, lower=interval[0], upper=interval[1]
        ),
        effect_size=EffectSize(name=effect_name, value=effect_value),
        provenance=_provenance(context, exclusions, transformations),
        diagnostics=diagnostics,
        exclusions=exclusions,
        warnings=list(item.warnings) + (warnings or []),
    )


def run_descriptive_summary(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 1)
    complete, counts, exclusions = _complete_case(frame, variables)
    summaries: dict[str, dict[str, float | int | str | None]] = {}
    first_estimate: float | None = None
    first_interval: tuple[float | None, float | None] = (None, None)
    for name in variables:
        series = complete[name]
        non_missing = series
        summary: dict[str, float | int | str | None] = {
            "non_missing": int(non_missing.shape[0]),
            "missing": counts["missing"],
            "unique": int(non_missing.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(series) and not non_missing.empty:
            values = np.sort(non_missing.to_numpy(dtype=float))
            if not np.isfinite(values).all():
                raise AnalysisExecutionError(f"non_finite_input:{name}")
            mean = _safe_float(np.mean(values), "non_finite_descriptive_estimate")
            summary["mean"] = mean
            summary["standard_deviation"] = (
                _safe_float(np.std(values, ddof=1), "non_finite_descriptive_variance")
                if values.size > 1
                else None
            )
            if first_estimate is None:
                first_estimate = mean
                if values.size > 1:
                    se = float(np.std(values, ddof=1) / np.sqrt(values.size))
                    critical = float(stats.t.ppf(1 - ALPHA / 2, values.size - 1))
                    first_interval = (mean - critical * se, mean + critical * se)
        else:
            summary["kind"] = "categorical"
        summaries[name] = summary
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=first_estimate,
        p_value=None,
        interval=first_interval,
        effect_name="standardized_descriptive_estimate",
        effect_value=None,
        diagnostics={"counts": counts, "variable_summaries": summaries},
        exclusions=exclusions,
        transformations=["complete_case_for_joint_summary"],
    )


def run_welch_t(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, exposure = variables[:2]
    complete, counts, exclusions = _complete_case(
        frame, [outcome, exposure], numeric=[outcome]
    )
    levels, order_strategy = _levels(complete[exposure], expected=2)
    groups = [
        np.sort(complete.loc[complete[exposure] == level, outcome].to_numpy(dtype=float))
        for level in levels
    ]
    if any(group.size < 2 for group in groups):
        raise AnalysisExecutionError("insufficient_group_observations")
    first, second = groups
    n1, n2 = int(first.size), int(second.size)
    mean1, mean2 = float(np.mean(first)), float(np.mean(second))
    var1, var2 = float(np.var(first, ddof=1)), float(np.var(second, ddof=1))
    standard_error = float(np.sqrt(var1 / n1 + var2 / n2))
    if standard_error == 0:
        raise AnalysisExecutionError("zero_standard_error")
    degrees_freedom = (var1 / n1 + var2 / n2) ** 2 / (
        (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
    )
    estimate = mean1 - mean2
    critical = float(stats.t.ppf(1 - ALPHA / 2, degrees_freedom))
    test = stats.ttest_ind(first, second, equal_var=False, nan_policy="raise")

    pooled_sd = float(
        np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    )
    if pooled_sd == 0:
        raise AnalysisExecutionError("zero_pooled_standard_deviation")
    cohen_d = estimate / pooled_sd
    correction = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    hedges_g = correction * cohen_d
    hedges_se = correction * np.sqrt(
        (n1 + n2) / (n1 * n2) + cohen_d**2 / (2.0 * (n1 + n2 - 2))
    )
    normal_critical = float(stats.norm.ppf(1 - ALPHA / 2))
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=_safe_float(estimate, "non_finite_estimate"),
        p_value=_p_value(test.pvalue),
        interval=(estimate - critical * standard_error, estimate + critical * standard_error),
        effect_name="hedges_g",
        effect_value=_safe_float(hedges_g, "non_finite_effect_size"),
        diagnostics={
            "counts": counts,
            "group_sizes": [n1, n2],
            "test_statistic": _safe_float(test.statistic, "non_finite_test_statistic"),
            "degrees_freedom": _safe_float(degrees_freedom, "non_finite_degrees_freedom"),
            "exposure_level_order": order_strategy,
            "estimate_direction": "first_confirmed_exposure_level_minus_second_confirmed_exposure_level",
            "effect_size_uncertainty": {
                "standard_error": _safe_float(hedges_se, "non_finite_effect_size_uncertainty"),
                "confidence_interval": {
                    "level": CONFIDENCE_LEVEL,
                    "lower": hedges_g - normal_critical * hedges_se,
                    "upper": hedges_g + normal_critical * hedges_se,
                },
                "formula": (
                    "J=1-3/(4*(n1+n2)-9); g=J*(mean1-mean2)/sp; "
                    "SE(g)=J*sqrt((n1+n2)/(n1*n2)+d^2/(2*(n1+n2-2)))"
                ),
            },
        },
        exclusions=exclusions,
        transformations=[
            "complete_case",
            "first_confirmed_exposure_level_minus_second_confirmed_exposure_level",
        ],
    )


def run_paired_t(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 3, maximum=3)
    outcome, condition, pair_id = variables
    missing_columns = [name for name in variables if name not in frame.columns]
    if missing_columns:
        raise AnalysisExecutionError(f"unknown_required_variable:{missing_columns[0]}")
    structure = frame.loc[:, [condition, pair_id]]
    if structure.isna().any(axis=None):
        raise AnalysisExecutionError("invalid_pair_structure")
    levels, order_strategy = _levels(structure[condition], expected=2)
    pair_sizes = structure.groupby(pair_id, observed=True, sort=False).size()
    pair_conditions = structure.groupby(pair_id, observed=True, sort=False)[condition].nunique()
    if (
        pair_sizes.empty
        or not bool((pair_sizes == 2).all())
        or not bool((pair_conditions == 2).all())
    ):
        raise AnalysisExecutionError("invalid_pair_structure")
    complete, counts, exclusions = _complete_case(
        frame, variables, numeric=[outcome]
    )
    pair_sizes = complete.groupby(pair_id, observed=True, sort=False).size()
    pair_conditions = complete.groupby(pair_id, observed=True, sort=False)[condition].nunique()
    complete_pair_ids = pair_sizes.index[(pair_sizes == 2) & (pair_conditions == 2)]
    complete = complete.loc[complete[pair_id].isin(complete_pair_ids)].copy()
    counts["used"] = int(len(complete))
    counts["missing"] = counts["input"] - counts["used"]
    exclusions = [
        f"paired_complete_case:input={counts['input']};used={counts['used']};missing={counts['missing']}"
    ]
    pair_values = sorted(complete[pair_id].unique().tolist(), key=_sort_key)
    first = np.asarray(
        [
            complete.loc[
                (complete[pair_id] == pair) & (complete[condition] == levels[0]), outcome
            ].iloc[0]
            for pair in pair_values
        ],
        dtype=float,
    )
    second = np.asarray(
        [
            complete.loc[
                (complete[pair_id] == pair) & (complete[condition] == levels[1]), outcome
            ].iloc[0]
            for pair in pair_values
        ],
        dtype=float,
    )
    if first.size < 2:
        raise AnalysisExecutionError("insufficient_paired_observations")
    differences = np.sort(first - second)
    estimate = float(np.mean(differences))
    difference_sd = float(np.std(differences, ddof=1))
    if difference_sd == 0:
        raise AnalysisExecutionError("zero_paired_standard_deviation")
    standard_error = difference_sd / np.sqrt(differences.size)
    degrees_freedom = differences.size - 1
    critical = float(stats.t.ppf(1 - ALPHA / 2, degrees_freedom))
    test = stats.ttest_rel(first, second, nan_policy="raise")
    cohen_dz = estimate / difference_sd
    correction = 1.0 - 3.0 / (4.0 * differences.size - 5.0)
    hedges_g = correction * cohen_dz
    hedges_se = correction * np.sqrt(
        1.0 / differences.size + cohen_dz**2 / (2.0 * (differences.size - 1))
    )
    normal_critical = float(stats.norm.ppf(1 - ALPHA / 2))
    return _result(
        item=item,
        context=context,
        n=int(differences.size),
        estimate=_safe_float(estimate, "non_finite_estimate"),
        p_value=_p_value(test.pvalue),
        interval=(estimate - critical * standard_error, estimate + critical * standard_error),
        effect_name="paired_hedges_g_z",
        effect_value=_safe_float(hedges_g, "non_finite_effect_size"),
        diagnostics={
            "counts": counts,
            "pairs": int(differences.size),
            "test_statistic": _safe_float(test.statistic, "non_finite_test_statistic"),
            "degrees_freedom": int(degrees_freedom),
            "exposure_level_order": order_strategy,
            "estimate_direction": "first_confirmed_exposure_level_minus_second_confirmed_exposure_level",
            "effect_size_uncertainty": {
                "standard_error": _safe_float(hedges_se, "non_finite_effect_size_uncertainty"),
                "confidence_interval": {
                    "level": CONFIDENCE_LEVEL,
                    "lower": hedges_g - normal_critical * hedges_se,
                    "upper": hedges_g + normal_critical * hedges_se,
                },
                "formula": (
                    "J=1-3/(4*(n_pairs-1)-1); "
                    "g_z=J*mean(within_pair_difference)/sd(within_pair_difference); "
                    "SE(g_z)=J*sqrt(1/n_pairs+d_z^2/(2*(n_pairs-1)))"
                ),
            },
        },
        exclusions=exclusions,
        transformations=["complete_case", "pair_alignment", "within_pair_difference"],
    )


def run_welch_anova(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, exposure = variables[:2]
    complete, counts, exclusions = _complete_case(
        frame, [outcome, exposure], numeric=[outcome]
    )
    levels, order_strategy = _levels(complete[exposure])
    if len(levels) < 3:
        raise AnalysisExecutionError("expected_at_least_3_levels")
    groups = [
        np.sort(complete.loc[complete[exposure] == level, outcome].to_numpy(dtype=float))
        for level in levels
    ]
    if any(group.size < 2 for group in groups):
        raise AnalysisExecutionError("insufficient_group_observations")
    analysis = anova_oneway(groups, use_var="unequal", welch_correction=True)
    means = np.asarray([np.mean(group) for group in groups], dtype=float)
    variances = np.asarray([np.var(group, ddof=1) for group in groups], dtype=float)
    sizes = np.asarray([group.size for group in groups], dtype=int)
    estimate = _safe_float(
        effectsize_oneway(means, variances, sizes, use_var="unequal"),
        "non_finite_welch_effect_size",
    )
    effect_interval = confint_effectsize_oneway(
        analysis.statistic,
        (analysis.df_num, analysis.df_denom),
        alpha=ALPHA,
        nobs=int(np.sum(sizes)),
    ).f2
    effect_lower = _safe_float(
        effect_interval[0], "non_finite_welch_effect_confidence_interval"
    )
    effect_upper = _safe_float(
        effect_interval[1], "non_finite_welch_effect_confidence_interval"
    )
    if effect_lower < 0 or effect_upper < effect_lower:
        raise AnalysisExecutionError("invalid_welch_effect_confidence_interval")
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=estimate,
        p_value=_p_value(analysis.pvalue),
        interval=(effect_lower, effect_upper),
        effect_name="welch_cohen_f_squared",
        effect_value=estimate,
        diagnostics={
            "counts": counts,
            "group_sizes": sizes.tolist(),
            "welch_f": _safe_float(analysis.statistic, "non_finite_test_statistic"),
            "degrees_freedom": [
                _safe_float(analysis.df_num, "non_finite_degrees_freedom"),
                _safe_float(analysis.df_denom, "non_finite_degrees_freedom"),
            ],
            "exposure_level_order": order_strategy,
            "effect_parameter": "welch_cohen_f_squared",
            "effect_size_definition": (
                "statsmodels.effectsize_oneway(means, variances, group_sizes, "
                "use_var='unequal'); f_squared=noncentrality/total_n"
            ),
            "confidence_interval_method": "statsmodels_noncentral_f_inversion",
        },
        exclusions=exclusions,
        transformations=["complete_case", "welch_unequal_variance_weights"],
    )


def run_categorical_association(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, exposure = variables[:2]
    complete, counts, exclusions = _complete_case(frame, [outcome, exposure])
    outcome_levels, outcome_strategy = _levels(complete[outcome], expected=2)
    exposure_levels, exposure_strategy = _levels(complete[exposure], expected=2)
    table = np.asarray(
        [
            [
                int(((complete[outcome] == outcome_level) & (complete[exposure] == exposure_level)).sum())
                for exposure_level in exposure_levels
            ]
            for outcome_level in outcome_levels
        ],
        dtype=int,
    )
    if np.any(table.sum(axis=0) == 0) or np.any(table.sum(axis=1) == 0):
        raise AnalysisExecutionError("empty_contingency_margin")
    chi_square, chi_p, _, expected = stats.chi2_contingency(table, correction=False)
    if bool(np.any(expected < 5)):
        raw_odds_ratio, selected_p = stats.fisher_exact(table, alternative="two-sided")
        selected_test = "fisher_exact"
    else:
        raw_odds_ratio = table[0, 0] * table[1, 1] / (table[0, 1] * table[1, 0])
        selected_p = chi_p
        selected_test = "pearson_chi_square"
    corrected = table.astype(float)
    correction_applied = bool(np.any(corrected == 0))
    if correction_applied:
        corrected += 0.5
    odds_ratio = float(corrected[0, 0] * corrected[1, 1] / (corrected[0, 1] * corrected[1, 0]))
    log_standard_error = float(np.sqrt(np.sum(1.0 / corrected)))
    critical = float(stats.norm.ppf(1 - ALPHA / 2))
    lower = float(np.exp(np.log(odds_ratio) - critical * log_standard_error))
    upper = float(np.exp(np.log(odds_ratio) + critical * log_standard_error))
    phi = float(np.sqrt(chi_square / counts["used"]))
    result_warnings = ["zero_cell_odds_ratio_corrected"] if correction_applied else []
    if not np.isfinite(raw_odds_ratio):
        result_warnings.append("fisher_odds_ratio_non_finite")
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=_safe_float(odds_ratio, "non_finite_estimate"),
        p_value=_p_value(selected_p),
        interval=(lower, upper),
        effect_name="odds_ratio",
        effect_value=_safe_float(odds_ratio, "non_finite_effect_size"),
        diagnostics={
            "counts": counts,
            "selected_test": selected_test,
            "minimum_expected_count": _safe_float(np.min(expected), "non_finite_expected_count"),
            "phi": _safe_float(phi, "non_finite_phi"),
            "outcome_level_order": outcome_strategy,
            "exposure_level_order": exposure_strategy,
            "estimate_direction": "first_confirmed_levels_odds_ratio",
            "zero_cell_correction": 0.5 if correction_applied else 0.0,
        },
        exclusions=exclusions,
        transformations=["complete_case", "binary_indicator_coding"],
        warnings=result_warnings,
    )


def run_correlation(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, exposure = variables[:2]
    complete, counts, exclusions = _complete_case(
        frame, [outcome, exposure], numeric=[outcome, exposure]
    )
    if counts["used"] < 4:
        raise AnalysisExecutionError("insufficient_correlation_observations")
    ordered = complete.sort_values([exposure, outcome], kind="mergesort")
    x = ordered[exposure].to_numpy(dtype=float)
    y = ordered[outcome].to_numpy(dtype=float)
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise AnalysisExecutionError("insufficient_variation")
    analysis = stats.pearsonr(x, y)
    estimate = _safe_float(analysis.statistic, "non_finite_estimate")
    clipped = float(np.clip(estimate, -1.0 + np.finfo(float).eps, 1.0 - np.finfo(float).eps))
    fisher_z = float(np.arctanh(clipped))
    z_se = 1.0 / np.sqrt(counts["used"] - 3)
    critical = float(stats.norm.ppf(1 - ALPHA / 2))
    lower = float(np.tanh(fisher_z - critical * z_se))
    upper = float(np.tanh(fisher_z + critical * z_se))
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=estimate,
        p_value=_p_value(analysis.pvalue),
        interval=(lower, upper),
        effect_name="pearson_r",
        effect_value=estimate,
        diagnostics={
            "counts": counts,
            "selected_test": "pearson",
            "confidence_interval_method": "fisher_z",
        },
        exclusions=exclusions,
        transformations=["complete_case", "rowwise_pairing"],
    )


def _design_matrix(
    complete: pd.DataFrame, predictors: Sequence[str]
) -> tuple[pd.DataFrame, str, list[str]]:
    encoded: dict[str, np.ndarray] = {}
    transformations: list[str] = []
    primary_term: str | None = None
    for predictor_index, name in enumerate(predictors, start=1):
        series = complete[name]
        if pd.api.types.is_numeric_dtype(series):
            values = series.to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise AnalysisExecutionError(f"non_finite_input:{name}")
            term = f"predictor_{predictor_index}"
            encoded[term] = values
            transformations.append(f"numeric_predictor:{predictor_index}")
            if primary_term is None:
                primary_term = term
            continue
        levels, _ = _levels(series)
        if len(levels) < 2:
            raise AnalysisExecutionError(f"insufficient_predictor_variation:{name}")
        reference = levels[-1]
        for contrast_index, level in enumerate(levels[:-1], start=1):
            term = f"predictor_{predictor_index}_contrast_{contrast_index}"
            encoded[term] = (series == level).to_numpy(dtype=float)
            if primary_term is None:
                primary_term = term
        transformations.append(f"categorical_indicator_coding:{predictor_index}:reference_last")
    if primary_term is None:
        raise AnalysisExecutionError("missing_predictors")
    matrix = pd.DataFrame(encoded, index=complete.index)
    matrix = sm.add_constant(matrix, has_constant="add")
    if np.linalg.matrix_rank(matrix.to_numpy(dtype=float)) < matrix.shape[1]:
        raise AnalysisExecutionError("rank_deficient_design_matrix")
    return matrix, primary_term, transformations


def run_linear_regression(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, predictors = variables[0], variables[1:]
    complete, counts, exclusions = _complete_case(
        frame, variables, numeric=[outcome]
    )
    matrix, primary_term, encoding = _design_matrix(complete, predictors)
    if counts["used"] <= matrix.shape[1]:
        raise AnalysisExecutionError("insufficient_regression_observations")
    response = complete[outcome].to_numpy(dtype=float)
    fitted = sm.OLS(response, matrix).fit(cov_type="HC3")
    coefficient = _safe_float(fitted.params[primary_term], "non_finite_estimate")
    interval = fitted.conf_int(alpha=ALPHA).loc[primary_term]
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=coefficient,
        p_value=_p_value(fitted.pvalues[primary_term]),
        interval=(
            _safe_float(interval.iloc[0], "non_finite_confidence_interval"),
            _safe_float(interval.iloc[1], "non_finite_confidence_interval"),
        ),
        effect_name="regression_coefficient",
        effect_value=coefficient,
        diagnostics={
            "counts": counts,
            "covariance_type": "HC3",
            "model_degrees_freedom": _safe_float(fitted.df_model, "non_finite_degrees_freedom"),
            "residual_degrees_freedom": _safe_float(fitted.df_resid, "non_finite_degrees_freedom"),
            "r_squared": _safe_float(fitted.rsquared, "non_finite_r_squared"),
            "condition_number": _safe_float(fitted.condition_number, "non_finite_condition_number"),
            "primary_coefficient": "first_confirmed_predictor_contrast",
        },
        exclusions=exclusions,
        transformations=["complete_case", *encoding],
    )


def run_logistic_regression(
    frame: pd.DataFrame, item: PlanItem, context: _ExecutionContext
) -> AnalysisResult:
    variables = _required_variables(item, 2)
    outcome, predictors = variables[0], variables[1:]
    complete, counts, exclusions = _complete_case(frame, variables)
    outcome_levels, outcome_strategy = _levels(complete[outcome], expected=2)
    response = (complete[outcome] == outcome_levels[0]).to_numpy(dtype=float)
    if min(int(np.sum(response)), int(response.size - np.sum(response))) < 2:
        raise AnalysisExecutionError("insufficient_binary_outcome_events")
    matrix, primary_term, encoding = _design_matrix(complete, predictors)
    if counts["used"] <= matrix.shape[1]:
        raise AnalysisExecutionError("insufficient_regression_observations")
    try:
        fitted = sm.Logit(response, matrix).fit(disp=False, maxiter=100)
    except (np.linalg.LinAlgError, statsmodels.tools.sm_exceptions.PerfectSeparationError) as exc:
        raise AnalysisExecutionError(
            "logistic_regression_fit_failed",
            warnings=[
                {
                    "code": "model_fit_failure",
                    "method": "logistic_regression",
                    "category": "perfect_separation_or_singular_information",
                }
            ],
        ) from exc
    if not bool(fitted.mle_retvals.get("converged", False)):
        raise AnalysisExecutionError(
            "logistic_regression_non_convergence",
            warnings=[
                {
                    "code": "model_convergence_failure",
                    "method": "logistic_regression",
                    "category": "non_convergence_or_separation",
                }
            ],
        )
    coefficient = _safe_float(fitted.params[primary_term], "non_finite_log_odds")
    estimate = _safe_float(np.exp(coefficient), "non_finite_estimate")
    raw_interval = fitted.conf_int(alpha=ALPHA).loc[primary_term]
    lower = _safe_float(np.exp(raw_interval.iloc[0]), "non_finite_confidence_interval")
    upper = _safe_float(np.exp(raw_interval.iloc[1]), "non_finite_confidence_interval")
    return _result(
        item=item,
        context=context,
        n=counts["used"],
        estimate=estimate,
        p_value=_p_value(fitted.pvalues[primary_term]),
        interval=(lower, upper),
        effect_name="odds_ratio",
        effect_value=estimate,
        diagnostics={
            "counts": counts,
            "converged": True,
            "iterations": int(fitted.mle_retvals.get("iterations", 0)),
            "log_likelihood": _safe_float(fitted.llf, "non_finite_log_likelihood"),
            "outcome_level_order": outcome_strategy,
            "outcome_coding": "first_confirmed_level_is_event",
            "primary_coefficient": "first_confirmed_predictor_contrast",
        },
        exclusions=exclusions,
        transformations=["complete_case", "binary_outcome_coding", *encoding],
    )


METHODS: dict[str, Executor] = {
    "descriptive_summary": run_descriptive_summary,
    "welch_t_test": run_welch_t,
    "paired_t_test": run_paired_t,
    "welch_anova": run_welch_anova,
    "chi_square_or_fisher": run_categorical_association,
    "pearson_or_spearman": run_correlation,
    "linear_regression": run_linear_regression,
    "logistic_regression": run_logistic_regression,
}


def run_plan(frame: pd.DataFrame, plan: AnalysisPlan) -> AnalysisBundle:
    """Execute only approved, verified methods and return auditable result objects."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame_must_be_dataframe")
    if plan.blocking_errors:
        raise AnalysisExecutionError("plan_has_blocking_errors")
    identifiers = [item.id for item in plan.items]
    if len(set(identifiers)) != len(identifiers):
        raise AnalysisExecutionError("duplicate_plan_item_id")
    for item in plan.items:
        if item.blocking_errors:
            raise AnalysisExecutionError(f"plan_item_has_blocking_errors:{item.id}")
        if item.method in ALTERNATIVE_METADATA_ONLY:
            raise AnalysisExecutionError(f"unverified_selected_method:{item.method}")
        if item.method not in METHODS:
            raise AnalysisExecutionError(f"unknown_selected_method:{item.method}")
        if (
            item.robust_alternative is not None
            and item.robust_alternative not in ALTERNATIVE_METADATA_ONLY
        ):
            raise AnalysisExecutionError(
                f"unknown_robust_alternative:{item.robust_alternative}"
            )

    versions = runtime_versions()
    context = _ExecutionContext(
        fingerprint=_data_fingerprint(frame),
        plan_version=plan.version,
        versions=versions,
    )
    results: dict[str, AnalysisResult] = {}
    bundle_warning_details: list[dict[str, str]] = []
    for item in plan.items:
        with python_warnings.catch_warnings(record=True) as caught:
            python_warnings.simplefilter("always")
            try:
                result = METHODS[item.method](frame, item, context)
            except AnalysisExecutionError as exc:
                exc.warnings.extend(
                    {
                        "code": "library_warning",
                        "method": item.method,
                        "category": warning.category.__name__,
                    }
                    for warning in caught
                    if not any(
                        detail.get("category") == warning.category.__name__
                        for detail in exc.warnings
                    )
                )
                raise
        if caught:
            details = [
                {
                    "code": "library_warning",
                    "method": item.method,
                    "category": warning.category.__name__,
                }
                for warning in caught
            ]
            severe_categories = {
                "ConvergenceWarning",
                "PerfectSeparationWarning",
            }
            if any(detail["category"] in severe_categories for detail in details):
                raise AnalysisExecutionError(
                    f"invalid_model_fit:{item.method}", warnings=details
                )
            result.warnings.extend(
                f"library_warning:{detail['category']}:{item.method}" for detail in details
            )
            result.diagnostics["warning_details"] = details
            bundle_warning_details.extend(details)
        results[item.id] = result

    all_exclusions = list(
        dict.fromkeys(exclusion for result in results.values() for exclusion in result.exclusions)
    )
    bundle_provenance = _provenance(
        context,
        all_exclusions,
        ["deterministic_complete_case_execution"],
    )
    return AnalysisBundle(
        results=results,
        reproducibility=versions,
        provenance=bundle_provenance,
        warnings=bundle_warning_details,
    )
