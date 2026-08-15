from pydantic import ValidationError

from biostat_service.contracts import StudyBrief


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
