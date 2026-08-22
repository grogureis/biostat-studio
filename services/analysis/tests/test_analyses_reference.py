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

    alternative = AnalysisPlan(
        items=[item("primary_outcome", "mann_whitney_u", ["age_years", "treatment_group"])]
    )
    with pytest.raises(AnalysisExecutionError, match="unverified_selected_method:mann_whitney_u"):
        run_plan(core_frame, alternative)

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

    assert "mann_whitney_u" in ALTERNATIVE_METADATA_ONLY
    assert "mann_whitney_u" not in METHODS


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
