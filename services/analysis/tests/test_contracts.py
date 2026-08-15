import pytest
from pydantic import ValidationError

from biostat_service.contracts import AnalysisResult, StudyBrief


def test_study_brief_requires_one_outcome():
    try:
        StudyBrief(
            title="30-day outcome",
            question="Does treatment reduce 30-day events?",
            hypothesis="Treatment is associated with fewer events.",
            design="cohort",
            outcome_variables=[],
            exposure_variables=["treatment"],
            language="en",
        )
    except ValidationError as exc:
        assert "outcome_variables" in str(exc)
    else:
        raise AssertionError("empty outcomes must be rejected")


def test_study_brief_defaults_optional_request_fields():
    brief = StudyBrief(
        title="30-day outcome",
        question="Does treatment reduce 30-day events?",
        hypothesis="Treatment is associated with fewer events.",
        design="cohort",
        outcome_variables=["event_30_day"],
    )

    assert brief.exposure_variables == []
    assert brief.covariates == []
    assert brief.pair_id_variable is None
    assert brief.language == "en"


def test_study_brief_accepts_optional_pair_identifier():
    brief = StudyBrief(
        title="Repeated outcome",
        question="Does the outcome differ between conditions?",
        hypothesis="The paired conditions differ.",
        design="repeated",
        outcome_variables=["score"],
        exposure_variables=["condition"],
        pair_id_variable="participant_id",
    )

    assert brief.pair_id_variable == "participant_id"


def test_analysis_result_serializes_complete_provenance():
    provenance = {
        "data_fingerprint": "83b99e28f455c60f8cbe5e4dfb032beaeda6b51cc06c9f55629f83f103e4a35e",
        "plan_version": 1,
        "exclusions": ["row_12_missing_outcome"],
        "transformations": ["age_years_centered"],
        "random_seed": 20260815,
        "library_versions": {"scipy": "1.13.1", "statsmodels": "0.14.6"},
    }
    result = AnalysisResult(
        id="primary_outcome",
        method="welch_t_test",
        n=11,
        confidence_interval={"level": 0.95, "lower": -8.2, "upper": -0.1},
        effect_size={"name": "hedges_g", "value": -0.6},
        provenance=provenance,
    )

    assert result.model_dump().get("provenance") == provenance


def test_analysis_result_rejects_missing_provenance():
    with pytest.raises(ValidationError) as exc_info:
        AnalysisResult(
            id="primary_outcome",
            method="welch_t_test",
            n=11,
            confidence_interval={"level": 0.95, "lower": -8.2, "upper": -0.1},
            effect_size={"name": "hedges_g", "value": -0.6},
        )

    assert "provenance" in str(exc_info.value)
