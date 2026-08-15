"""Reference and safety coverage for scientific analysis execution."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
    assert forward.diagnostics["estimate_direction"] == (
        "first_confirmed_exposure_level_minus_second_confirmed_exposure_level"
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
