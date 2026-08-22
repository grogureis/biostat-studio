"""Reference and safety coverage for scientific analysis execution."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biostat_service import analyses as analysis_module
from biostat_service.analyses import (
    ALTERNATIVE_METADATA_ONLY,
    METHODS,
    AnalysisExecutionError,
    run_plan,
)
from biostat_service.contracts import AnalysisPlan, PlanItem


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "core-study.xlsx"


def item(
    identifier: str,
    method: str,
    variables: list[str],
    *,
    robust_alternative: str | None = None,
) -> PlanItem:
    return PlanItem(
        id=identifier,
        estimand="Confirmed structured estimand.",
        method=method,
        rationale="Confirmed structured rationale.",
        required_variables=variables,
        assumptions=["Confirmed assumptions."],
        robust_alternative=robust_alternative,
        outputs=["effect_size:required", "confidence_interval:95_percent"],
    )


@pytest.fixture
def core_frame() -> pd.DataFrame:
    return pd.read_excel(FIXTURE_PATH, sheet_name="Analysis")


@pytest.fixture
def approved_plan() -> AnalysisPlan:
    return AnalysisPlan(
        version=1,
        items=[
            item("descriptive_summary", "descriptive_summary", ["age_years", "treatment_group"]),
            item(
                "primary_outcome",
                "welch_t_test",
                ["age_years", "treatment_group"],
                robust_alternative="mann_whitney_u",
            ),
        ],
    )


def test_welch_result_matches_reference(
    core_frame: pd.DataFrame, approved_plan: AnalysisPlan
) -> None:
    """A wrong group direction, missing-data rule, or test formula breaks the reference."""
    bundle = run_plan(core_frame, approved_plan)
    result = bundle.results["primary_outcome"]

    assert result.method == "welch_t_test"
    assert result.n == 11
    assert result.estimate == pytest.approx(-4.1667, abs=1e-4)
    assert result.confidence_interval.level == 0.95
    assert result.confidence_interval.lower == pytest.approx(-8.7143, abs=1e-4)
    assert result.confidence_interval.upper == pytest.approx(0.3810, abs=1e-4)
    assert result.p_value == pytest.approx(0.06802620194372311)
    assert result.effect_size.name == "hedges_g"
    assert result.effect_size.value == pytest.approx(-1.1381247948159288)
    assert result.diagnostics["counts"] == {"input": 12, "used": 11, "missing": 1}
    uncertainty = result.diagnostics["effect_size_uncertainty"]
    assert uncertainty["standard_error"] == pytest.approx(0.6151959612398401)
    assert uncertainty["confidence_interval"]["lower"] == pytest.approx(
        -2.3438867222805144
    )
    assert uncertainty["confidence_interval"]["upper"] == pytest.approx(
        0.0676371326486569
    )
    assert result.diagnostics["effect_size_uncertainty"]["formula"] == (
        "J=1-3/(4*(n1+n2)-9); g=J*(mean1-mean2)/sp; "
        "SE(g)=J*sqrt((n1+n2)/(n1*n2)+d^2/(2*(n1+n2-2)))"
    )


def test_welch_is_row_order_and_report_language_invariant(
    core_frame: pd.DataFrame, approved_plan: AnalysisPlan
) -> None:
    """Row presentation and translated prose must not change scientific quantities."""
    turkish_plan = deepcopy(approved_plan)
    for planned_item in turkish_plan.items:
        planned_item.estimand = "Doğrulanmış yapısal tahmin hedefi."
        planned_item.rationale = "Doğrulanmış yapısal gerekçe."

    first = run_plan(core_frame, approved_plan).results["primary_outcome"]
    second = run_plan(
        core_frame.sample(frac=1, random_state=20260815).reset_index(drop=True),
        turkish_plan,
    ).results["primary_outcome"]

    assert second.estimate == first.estimate
    assert second.p_value == first.p_value
    assert second.confidence_interval == first.confidence_interval
    assert second.effect_size == first.effect_size
    assert second.provenance.data_fingerprint == first.provenance.data_fingerprint


def test_ordered_categories_define_effect_direction(core_frame: pd.DataFrame) -> None:
    """Reversing a confirmed category order must reverse the reported contrast."""
    plan = AnalysisPlan(items=[item("primary_outcome", "welch_t_test", ["age_years", "treatment_group"])])
    treatment_first = core_frame.copy()
    treatment_first["treatment_group"] = pd.Categorical(
        treatment_first["treatment_group"], categories=["Treatment", "Control"], ordered=True
    )
    control_first = core_frame.copy()
    control_first["treatment_group"] = pd.Categorical(
        control_first["treatment_group"], categories=["Control", "Treatment"], ordered=True
    )

    forward = run_plan(treatment_first, plan).results["primary_outcome"]
    reverse = run_plan(control_first, plan).results["primary_outcome"]

    assert forward.estimate == pytest.approx(-4.1667, abs=1e-4)
    assert reverse.estimate == pytest.approx(4.1667, abs=1e-4)
    assert reverse.effect_size.value == pytest.approx(-forward.effect_size.value)
    assert reverse.provenance.data_fingerprint != forward.provenance.data_fingerprint
    assert forward.diagnostics["estimate_direction"] == (
        "first_ordered_exposure_level_minus_second_ordered_exposure_level"
    )


def test_every_result_has_value_free_reproducibility_metadata(
    core_frame: pd.DataFrame, approved_plan: AnalysisPlan
) -> None:
    """Missing provenance or leaked paths/rows would make a result unsafe to audit."""
    bundle = run_plan(core_frame, approved_plan)
    serialized = bundle.model_dump(mode="json")

    assert set(bundle.reproducibility) >= {"python", "numpy", "pandas", "scipy", "statsmodels"}
    assert len(bundle.provenance.data_fingerprint) == 64
    assert bundle.provenance.plan_version == approved_plan.version
    for result in bundle.results.values():
        assert result.provenance.data_fingerprint == bundle.provenance.data_fingerprint
        assert result.provenance.plan_version == approved_plan.version
        assert result.provenance.library_versions == bundle.reproducibility
    assert str(FIXTURE_PATH) not in str(serialized)
    assert "P001" not in str(serialized)


def test_fingerprint_includes_dtype_and_ordered_category_metadata() -> None:
    """Scientific type or level-order changes must alter provenance even when values do not."""
    plan = AnalysisPlan(items=[item("summary", "descriptive_summary", ["value", "group"])])
    integer = pd.DataFrame(
        {
            "value": pd.Series([1, 2, 3, 4], dtype="int64"),
            "group": pd.Categorical(
                ["a", "b", "a", "b"], categories=["a", "b"], ordered=True
            ),
        }
    )
    floating = integer.copy()
    floating["value"] = floating["value"].astype("float64")
    reversed_order = integer.copy()
    reversed_order["group"] = pd.Categorical(
        reversed_order["group"], categories=["b", "a"], ordered=True
    )

    fingerprints = {
        run_plan(frame, plan).provenance.data_fingerprint
        for frame in (integer, floating, reversed_order)
    }

    assert len(fingerprints) == 3


def test_descriptive_summary_reports_variable_specific_denominators() -> None:
    """Missingness in one variable must not reduce another variable's descriptive denominator."""
    frame = pd.DataFrame(
        {
            "first": [1.0, 2.0, np.nan, 4.0],
            "second": [10.0, np.nan, 30.0, 40.0],
        }
    )
    plan = AnalysisPlan(
        items=[item("summary", "descriptive_summary", ["first", "second"])]
    )

    result = run_plan(frame, plan).results["summary"]

    assert result.n == 4
    assert result.diagnostics["counts"] == {"input": 4, "used": 4, "missing": 0}
    assert result.diagnostics["variable_summaries"] == {
        "first": {
            "non_missing": 3,
            "missing": 1,
            "unique": 3,
            "mean": pytest.approx(7 / 3),
            "standard_deviation": pytest.approx(1.5275252316519465),
        },
        "second": {
            "non_missing": 3,
            "missing": 1,
            "unique": 3,
            "mean": pytest.approx(80 / 3),
            "standard_deviation": pytest.approx(15.275252316519467),
        },
    }
    assert result.exclusions == ["available_case:input=4;used=4;missing=0"]
    assert result.provenance.transformations == ["available_case_by_variable"]


def test_non_finite_values_are_rejected_without_exposing_the_value(
    core_frame: pd.DataFrame, approved_plan: AnalysisPlan
) -> None:
    """Infinity must not reach a package calculation or appear in an error payload."""
    core_frame.loc[0, "age_years"] = np.inf

    with pytest.raises(AnalysisExecutionError, match="non_finite_input:age_years") as exc_info:
        run_plan(core_frame, approved_plan)

    assert "inf" not in str(exc_info.value).replace("non_finite", "")
    assert "P001" not in str(exc_info.value)


def test_blocking_and_unverified_selected_methods_fail_before_execution(
    core_frame: pd.DataFrame,
) -> None:
    """A blocked or alternative-only plan must not be treated as executable."""
    with pytest.raises(AnalysisExecutionError, match="plan_has_blocking_errors"):
        run_plan(core_frame, AnalysisPlan(blocking_errors=["unconfirmed_outcome"]),)

    unknown_method = AnalysisPlan(
        items=[item("primary_outcome", "invented_method", ["age_years", "treatment_group"])]
    )
    with pytest.raises(AnalysisExecutionError, match="unknown_selected_method:invented_method"):
        run_plan(core_frame, unknown_method)

    unknown_alternative = AnalysisPlan(
        items=[
            item(
                "primary_outcome",
                "welch_t_test",
                ["age_years", "treatment_group"],
                robust_alternative="invented_fallback",
            )
        ]
    )
    with pytest.raises(AnalysisExecutionError, match="unknown_robust_alternative"):
        run_plan(core_frame, unknown_alternative)

    assert not ALTERNATIVE_METADATA_ONLY
    for method in ("mann_whitney_u", "wilcoxon_signed_rank", "kruskal_wallis", "spearman_rank"):
        assert method in METHODS


def mann_whitney_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "score": [1.1, 2.3, 2.9, 3.6, 4.5, 5.1, 0.8, 1.4, 1.9, 2.2, 2.5],
            "arm": ["B"] * 6 + ["A"] * 5,
        }
    )


def test_mann_whitney_matches_independent_reference() -> None:
    """Rank-sum wiring, shift estimate, CI, and effect direction must match the reference."""
    plan = AnalysisPlan(items=[item("primary_outcome", "mann_whitney_u", ["score", "arm"])])

    result = run_plan(mann_whitney_frame(), plan).results["primary_outcome"]

    assert result.method == "mann_whitney_u"
    assert result.n == 11
    assert result.estimate == pytest.approx(1.5)
    assert result.p_value == pytest.approx(0.08225108225108226)
    assert result.confidence_interval.lower == pytest.approx(-0.3)
    assert result.confidence_interval.upper == pytest.approx(3.2)
    assert result.effect_size.name == "rank_biserial_r"
    assert result.effect_size.value == pytest.approx(0.6666666666666667)
    assert result.diagnostics["counts"] == {"input": 11, "used": 11, "missing": 0}
    assert result.diagnostics["group_sizes"] == [6, 5]
    assert result.diagnostics["u_statistic"] == pytest.approx(25.0)
    assert result.diagnostics["p_value_method"] == "exact"
    assert result.diagnostics["estimate_direction"] == (
        "first_ordered_exposure_level_minus_second_ordered_exposure_level"
    )
    assert result.diagnostics["confidence_interval_method"] == (
        "hodges_lehmann_order_statistic_normal_approximation"
    )


def test_mann_whitney_uses_asymptotic_method_when_values_tie() -> None:
    """Tied pooled values must switch the exact p-value path off deterministically."""
    frame = mann_whitney_frame()
    frame.loc[6, "score"] = 1.1
    plan = AnalysisPlan(items=[item("primary_outcome", "mann_whitney_u", ["score", "arm"])])

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.diagnostics["p_value_method"] == "asymptotic"
    assert result.p_value is not None and 0.0 <= result.p_value <= 1.0


def test_mann_whitney_rejects_degenerate_groups() -> None:
    """One-observation groups or a constant outcome cannot support the test."""
    tiny = pd.DataFrame({"score": [1.0, 2.0, 3.0], "arm": ["B", "B", "A"]})
    plan = AnalysisPlan(items=[item("primary_outcome", "mann_whitney_u", ["score", "arm"])])
    with pytest.raises(AnalysisExecutionError, match="insufficient_group_observations"):
        run_plan(tiny, plan)

    constant = pd.DataFrame({"score": [2.0] * 6, "arm": ["B", "B", "B", "A", "A", "A"]})
    with pytest.raises(AnalysisExecutionError, match="insufficient_variation"):
        run_plan(constant, plan)


def wilcoxon_frame(post_scores: list[float]) -> pd.DataFrame:
    pre_scores = [12.0, 11.2, 14.5, 9.0, 13.0, 10.5, 12.4, 11.5, 15.0]
    pairs = [f"p{index}" for index in range(1, 10)]
    return pd.DataFrame(
        {
            "pair_id": pairs * 2,
            "condition": ["pre"] * 9 + ["post"] * 9,
            "score": pre_scores + post_scores,
        }
    )


def test_wilcoxon_signed_rank_matches_independent_reference() -> None:
    """Signed-rank wiring, pseudomedian, CI, and effect must match the reference."""
    frame = wilcoxon_frame([10.1, 11.9, 12.1, 8.6, 10.4, 10.0, 11.0, 10.0, 12.2])
    plan = AnalysisPlan(
        items=[item("primary_outcome", "wilcoxon_signed_rank", ["score", "condition", "pair_id"])]
    )

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.method == "wilcoxon_signed_rank"
    assert result.n == 9
    assert result.estimate == pytest.approx(1.5)
    assert result.p_value == pytest.approx(0.01953125)
    assert result.confidence_interval.lower == pytest.approx(0.4)
    assert result.confidence_interval.upper == pytest.approx(2.4)
    assert result.effect_size.name == "matched_rank_biserial_r"
    assert result.effect_size.value == pytest.approx(0.8666666666666667)
    assert result.diagnostics["pairs"] == 9
    assert result.diagnostics["pairs_used_for_test"] == 9
    assert result.diagnostics["zero_differences_dropped"] == 0
    assert result.diagnostics["w_statistic"] == pytest.approx(3.0)
    assert result.diagnostics["p_value_method"] == "exact"
    assert result.diagnostics["estimate_direction"] == (
        "first_ordered_exposure_level_minus_second_ordered_exposure_level"
    )
    assert "zero_differences_dropped" not in result.warnings


def test_wilcoxon_drops_zero_differences_with_a_warning() -> None:
    """Zero within-pair differences must be excluded, counted, and flagged."""
    frame = wilcoxon_frame([10.0, 11.2, 12.0, 8.5, 10.5, 10.0, 11.0, 10.0, 12.5])
    plan = AnalysisPlan(
        items=[item("primary_outcome", "wilcoxon_signed_rank", ["score", "condition", "pair_id"])]
    )

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.n == 9
    assert result.diagnostics["pairs_used_for_test"] == 8
    assert result.diagnostics["zero_differences_dropped"] == 1
    assert result.diagnostics["p_value_method"] == "approx"
    assert result.p_value == pytest.approx(0.013676686898827124)
    assert result.estimate == pytest.approx(1.6)
    assert result.confidence_interval.lower == pytest.approx(0.95)
    assert result.confidence_interval.upper == pytest.approx(2.5)
    assert result.effect_size.value == pytest.approx(1.0)
    assert "zero_differences_dropped" in result.warnings


def test_wilcoxon_rejects_all_zero_differences() -> None:
    """Identical paired measurements cannot support a signed-rank test."""
    frame = wilcoxon_frame([12.0, 11.2, 14.5, 9.0, 13.0, 10.5, 12.4, 11.5, 15.0])
    plan = AnalysisPlan(
        items=[item("primary_outcome", "wilcoxon_signed_rank", ["score", "condition", "pair_id"])]
    )

    with pytest.raises(AnalysisExecutionError, match="insufficient_variation"):
        run_plan(frame, plan)


def kruskal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "score": [
                7.1, 8.4, 9.2, 6.8, 7.7,
                5.9, 6.3, 7.0, 6.1,
                4.2, 5.1, 4.8, 5.5, 4.9,
            ],
            "site": ["C"] * 5 + ["B"] * 4 + ["A"] * 5,
        }
    )


def test_kruskal_wallis_matches_independent_reference() -> None:
    """Omnibus H, epsilon-squared, and the Dunn/Holm table must match the reference."""
    plan = AnalysisPlan(items=[item("primary_outcome", "kruskal_wallis", ["score", "site"])])

    result = run_plan(kruskal_frame(), plan).results["primary_outcome"]

    assert result.method == "kruskal_wallis"
    assert result.n == 14
    assert result.estimate == pytest.approx(0.8257142857142857)
    assert result.p_value == pytest.approx(0.003920921519003687)
    assert result.confidence_interval.lower is None
    assert result.confidence_interval.upper is None
    assert result.effect_size.name == "rank_epsilon_squared"
    assert result.effect_size.value == pytest.approx(0.8257142857142857)
    assert result.diagnostics["h_statistic"] == pytest.approx(11.082857142857144)
    assert result.diagnostics["degrees_freedom"] == 2
    assert result.diagnostics["group_sizes"] == [5, 4, 5]
    posthoc = result.diagnostics["posthoc"]
    assert posthoc["method"] == "dunn"
    assert posthoc["adjustment"] == "holm"
    comparisons = posthoc["comparisons"]
    assert [(entry["first"], entry["second"]) for entry in comparisons] == [
        ("C", "B"),
        ("C", "A"),
        ("B", "A"),
    ]
    assert comparisons[0]["z"] == pytest.approx(1.4432107063270918)
    assert comparisons[0]["p_value"] == pytest.approx(0.1489611244738834)
    assert comparisons[0]["p_adjusted"] == pytest.approx(0.18104248921069596)
    assert comparisons[1]["z"] == pytest.approx(3.3260873624811995)
    assert comparisons[1]["p_value"] == pytest.approx(0.0008807431907417271)
    assert comparisons[1]["p_adjusted"] == pytest.approx(0.0026422295722251813)
    assert comparisons[2]["z"] == pytest.approx(1.692654532112021)
    assert comparisons[2]["p_value"] == pytest.approx(0.09052124460534798)
    assert comparisons[2]["p_adjusted"] == pytest.approx(0.18104248921069596)
    assert comparisons[1]["rank_mean_difference"] == pytest.approx(8.8)
    assert "posthoc_with_nonsignificant_omnibus" not in result.warnings


def test_kruskal_flags_posthoc_when_omnibus_is_not_significant() -> None:
    """Pairwise contrasts after a null omnibus must carry an explicit caution."""
    frame = pd.DataFrame(
        {
            "score": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5, 1.2, 2.2, 3.2],
            "site": ["C", "C", "C", "B", "B", "B", "A", "A", "A"],
        }
    )
    plan = AnalysisPlan(items=[item("primary_outcome", "kruskal_wallis", ["score", "site"])])

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.p_value is not None and result.p_value >= 0.05
    assert "posthoc_with_nonsignificant_omnibus" in result.warnings


def test_kruskal_rejects_constant_outcome() -> None:
    """A constant outcome across all groups cannot support a rank test."""
    frame = pd.DataFrame(
        {"score": [3.0] * 9, "site": ["C", "C", "C", "B", "B", "B", "A", "A", "A"]}
    )
    plan = AnalysisPlan(items=[item("primary_outcome", "kruskal_wallis", ["score", "site"])])

    with pytest.raises(AnalysisExecutionError, match="insufficient_variation"):
        run_plan(frame, plan)


def test_spearman_matches_independent_reference() -> None:
    """Rank correlation, p-value, and the Fieller-based CI must match the reference."""
    frame = pd.DataFrame(
        {
            "y": [2.1, 1.8, 3.5, 3.9, 5.2, 4.8, 6.9, 7.4],
            "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )
    plan = AnalysisPlan(items=[item("primary_outcome", "spearman_rank", ["y", "x"])])

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.method == "spearman_rank"
    assert result.n == 8
    assert result.estimate == pytest.approx(0.9523809523809524)
    assert result.p_value == pytest.approx(0.00026040002438725105)
    assert result.confidence_interval.lower == pytest.approx(0.741574098598738)
    assert result.confidence_interval.upper == pytest.approx(0.9920139764772767)
    assert result.effect_size.name == "spearman_rho"
    assert result.effect_size.value == pytest.approx(result.estimate)
    assert result.diagnostics["selected_test"] == "spearman"
    assert result.diagnostics["confidence_interval_method"] == "fisher_z_fieller_se"


def test_spearman_requires_minimum_observations_and_variation() -> None:
    """Tiny or constant samples cannot support an interpretable rank correlation."""
    plan = AnalysisPlan(items=[item("primary_outcome", "spearman_rank", ["y", "x"])])
    tiny = pd.DataFrame({"y": [1.0, 2.0, 3.0], "x": [1.0, 2.0, 3.0]})
    with pytest.raises(AnalysisExecutionError, match="insufficient_correlation_observations"):
        run_plan(tiny, plan)

    constant = pd.DataFrame({"y": [1.0, 1.0, 1.0, 1.0], "x": [1.0, 2.0, 3.0, 4.0]})
    with pytest.raises(AnalysisExecutionError, match="insufficient_variation"):
        run_plan(constant, plan)


def test_paired_execution_requires_one_observation_per_condition_per_pair() -> None:
    """Duplicate or absent pair conditions must not be analyzed as independent rows."""
    frame = pd.DataFrame(
        {
            "pair_id": ["p1", "p1", "p2", "p2"],
            "condition": pd.Categorical(
                ["after", "before", "after", "before"],
                categories=["after", "before"],
                ordered=True,
            ),
            "score": [8.0, 5.0, 7.0, 6.0],
        }
    )
    plan = AnalysisPlan(
        items=[item("primary_outcome", "paired_t_test", ["score", "condition", "pair_id"])]
    )

    result = run_plan(frame, plan).results["primary_outcome"]
    assert result.n == 2
    assert result.estimate == pytest.approx(2.0)
    assert result.diagnostics["counts"] == {"input": 4, "used": 4, "missing": 0}

    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(AnalysisExecutionError, match="invalid_pair_structure") as exc_info:
        run_plan(duplicated, plan)
    assert "p1" not in str(exc_info.value)


def test_paired_complete_case_excludes_the_whole_incomplete_pair() -> None:
    """Dropping only one condition would break pairing instead of excluding that pair."""
    frame = pd.DataFrame(
        {
            "pair_id": ["p1", "p1", "p2", "p2", "p3", "p3"],
            "condition": pd.Categorical(
                ["after", "before"] * 3,
                categories=["after", "before"],
                ordered=True,
            ),
            "score": [8.0, 5.0, 7.0, 6.0, np.nan, 4.0],
        }
    )
    plan = AnalysisPlan(
        items=[item("primary_outcome", "paired_t_test", ["score", "condition", "pair_id"])]
    )

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.n == 2
    assert result.estimate == pytest.approx(2.0)
    assert result.diagnostics["counts"] == {"input": 6, "used": 4, "missing": 2}
    assert result.exclusions == ["paired_complete_case:input=6;used=4;missing=2"]


def test_paired_hedges_g_uncertainty_matches_literal_reference() -> None:
    """Paired effect uncertainty must use pair differences, not independent groups."""
    before = np.asarray([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    differences = np.asarray([1.0, 2.0, 2.0, 3.0, 4.0, 5.0])
    frame = pd.DataFrame(
        {
            "pair_id": np.repeat(["p1", "p2", "p3", "p4", "p5", "p6"], 2),
            "condition": pd.Categorical(
                ["after", "before"] * 6,
                categories=["after", "before"],
                ordered=True,
            ),
            "score": np.column_stack([before + differences, before]).reshape(-1),
        }
    )
    plan = AnalysisPlan(
        items=[item("primary_outcome", "paired_t_test", ["score", "condition", "pair_id"])]
    )

    result = run_plan(frame, plan).results["primary_outcome"]
    uncertainty = result.diagnostics["effect_size_uncertainty"]

    assert result.estimate == pytest.approx(2.8333333333333335)
    assert result.effect_size.name == "paired_hedges_g_z"
    assert result.effect_size.value == pytest.approx(1.6209439646701582)
    assert uncertainty["standard_error"] == pytest.approx(0.6172002479204776)
    assert uncertainty["confidence_interval"]["lower"] == pytest.approx(
        0.4112537074968299
    )
    assert uncertainty["confidence_interval"]["upper"] == pytest.approx(
        2.8306342218434866
    )
    assert "sd(within_pair_difference)" in uncertainty["formula"]


def test_welch_anova_reports_one_coherent_omnibus_effect() -> None:
    """An omnibus p-value must not be paired with a selected extrema contrast."""
    frame = pd.DataFrame(
        {
            "y": [1.0, 2.0, 3.0, 4.0, 4.0, 5.0, 7.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
            "group": ["a"] * 4 + ["b"] * 5 + ["c"] * 6,
        }
    )
    plan = AnalysisPlan(items=[item("primary_outcome", "welch_anova", ["y", "group"])])

    result = run_plan(frame, plan).results["primary_outcome"]
    serialized = result.model_dump(mode="json")

    assert result.estimate == pytest.approx(4.055235558515066)
    assert result.effect_size.name == "welch_cohen_f_squared"
    assert result.effect_size.value == pytest.approx(result.estimate)
    assert result.confidence_interval.lower == pytest.approx(0.6779268924602048)
    assert result.confidence_interval.upper == pytest.approx(8.840249727223844)
    assert result.p_value == pytest.approx(0.00025918299423306263)
    assert result.diagnostics["welch_f"] == pytest.approx(28.045165117241773)
    assert result.diagnostics["degrees_freedom"] == pytest.approx(
        [2.0, 7.891927036304011]
    )
    assert result.diagnostics["confidence_interval_method"] == (
        "statsmodels_noncentral_f_inversion"
    )
    assert "pairwise" not in str(serialized).lower()
    assert "largest" not in str(serialized).lower()
    assert "omega" not in str(serialized).lower()


def test_result_boundary_rejects_non_finite_published_diagnostics() -> None:
    """A nested effect interval must not bypass central finite-result validation."""
    context = analysis_module._ExecutionContext(
        fingerprint="a" * 64,
        plan_version=1,
        versions={"scipy": "test"},
    )
    planned = item("primary_outcome", "welch_t_test", ["y", "group"])

    with pytest.raises(
        AnalysisExecutionError, match="non_finite_result:diagnostics.effect_size_uncertainty.standard_error"
    ):
        analysis_module._result(
            item=planned,
            context=context,
            n=4,
            estimate=1.0,
            p_value=0.5,
            interval=(0.0, 2.0),
            effect_name="hedges_g",
            effect_value=1.0,
            diagnostics={"effect_size_uncertainty": {"standard_error": np.inf}},
            exclusions=[],
            transformations=[],
        )

    with pytest.raises(AnalysisExecutionError, match="invalid_p_value"):
        analysis_module._result(
            item=planned,
            context=context,
            n=4,
            estimate=1.0,
            p_value=1.01,
            interval=(0.0, 2.0),
            effect_name="hedges_g",
            effect_value=1.0,
            diagnostics={},
            exclusions=[],
            transformations=[],
        )


def test_finite_extreme_inputs_fail_closed_without_non_finite_payload() -> None:
    """Finite source values that overflow arithmetic must not serialize as valid science."""
    frame = pd.DataFrame(
        {
            "y": [1.0e308, 9.9e307, 9.8e307, -1.0e308, -9.9e307, -9.8e307],
            "group": [1, 1, 1, 0, 0, 0],
        }
    )
    plan = AnalysisPlan(items=[item("primary_outcome", "welch_t_test", ["y", "group"])])

    with pytest.raises(AnalysisExecutionError, match="non_finite") as exc_info:
        run_plan(frame, plan)

    assert "1e+308" not in str(exc_info.value).lower()


@pytest.mark.parametrize(
    ("method", "frame", "variables"),
    [
        (
            "welch_anova",
            pd.DataFrame({"y": [1.0, 2.0, 4.0, 5.0, 8.0, 9.0], "group": ["a", "a", "b", "b", "c", "c"]}),
            ["y", "group"],
        ),
        (
            "chi_square_or_fisher",
            pd.DataFrame({"event": [1, 1, 0, 0, 1, 0, 1, 0], "group": [1, 0, 1, 0, 1, 0, 1, 0]}),
            ["event", "group"],
        ),
        (
            "pearson_or_spearman",
            pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0, 5.0], "x": [2.0, 1.0, 4.0, 3.0, 5.0]}),
            ["y", "x"],
        ),
        (
            "linear_regression",
            pd.DataFrame({"y": [1.0, 2.1, 2.9, 4.2, 5.1, 5.9], "x": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]}),
            ["y", "x"],
        ),
        (
            "logistic_regression",
            pd.DataFrame(
                {
                    "event": [0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1],
                    "x": [-2.0, -1.5, -1.0, -0.5, 0.0, 0.4, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5],
                }
            ),
            ["event", "x"],
        ),
    ],
)
def test_every_planner_emitted_inferential_method_has_a_finite_executor(
    method: str, frame: pd.DataFrame, variables: list[str]
) -> None:
    """A planner-selected method without finite scientific outputs is not executable."""
    plan = AnalysisPlan(items=[item("primary_outcome", method, variables)])

    result = run_plan(frame, plan).results["primary_outcome"]

    assert result.method == method
    assert result.n > 0
    assert result.p_value is not None and 0.0 <= result.p_value <= 1.0
    assert result.estimate is not None and np.isfinite(result.estimate)
    assert result.confidence_interval.lower is not None
    assert result.confidence_interval.upper is not None
    assert np.isfinite(result.confidence_interval.lower)
    assert np.isfinite(result.confidence_interval.upper)


def test_independent_group_method_does_not_use_an_identifier_column() -> None:
    """Adding pair-like metadata must not change an independent-group result."""
    frame = pd.DataFrame(
        {
            "score": [1.0, 2.0, 4.0, 5.0],
            "group": [1, 1, 0, 0],
            "pair_id": ["p1", "p2", "p1", "p2"],
        }
    )
    plain = AnalysisPlan(items=[item("primary_outcome", "welch_t_test", ["score", "group"])])
    with_identifier = AnalysisPlan(
        items=[item("primary_outcome", "welch_t_test", ["score", "group", "pair_id"])]
    )

    first = run_plan(frame, plain).results["primary_outcome"]
    second = run_plan(frame, with_identifier).results["primary_outcome"]

    assert second.estimate == first.estimate
    assert second.p_value == first.p_value
    assert second.n == first.n


def test_logistic_separation_is_a_structured_failure_not_a_valid_result() -> None:
    """Perfect separation must retain a machine-readable issue and return no estimate."""
    frame = pd.DataFrame(
        {
            "event": [0, 0, 0, 0, 1, 1, 1, 1],
            "x": [-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0],
        }
    )
    plan = AnalysisPlan(
        items=[item("primary_outcome", "logistic_regression", ["event", "x"])]
    )

    with pytest.raises(AnalysisExecutionError, match="logistic_regression_non_convergence") as exc_info:
        run_plan(frame, plan)

    assert {
        "code": "model_convergence_failure",
        "method": "logistic_regression",
        "category": "non_convergence_or_separation",
    } in exc_info.value.warnings
    assert {
        "code": "library_warning",
        "method": "logistic_regression",
        "category": "PerfectSeparationWarning",
    } in exc_info.value.warnings
    assert all(set(detail) == {"code", "method", "category"} for detail in exc_info.value.warnings)
