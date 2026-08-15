"""Behavioral coverage for immutable Excel profiling."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from hashlib import sha256
from pathlib import Path

from openpyxl import Workbook
import pytest

from biostat_service.data_intake import profile_excel


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "core-study.xlsx"


@pytest.fixture
def core_workbook() -> Path:
    return FIXTURE_PATH


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_workbook(path: Path, headers: list[str], rows: list[list[object]]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quality"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


def test_profile_excel_preserves_source_and_detects_fixture_schema(core_workbook: Path) -> None:
    """A write-capable intake path or wrong schema inference breaks this boundary."""
    before = file_sha256(core_workbook)

    profile = profile_excel(core_workbook, sheet="Analysis")

    assert file_sha256(core_workbook) == before
    assert profile.source_sha256 == before
    assert profile.sheets == ("Analysis",)
    assert profile.selected_sheet == "Analysis"
    assert profile.rows == 12
    assert profile.columns == 5
    assert profile.missing_cells == 1
    assert len(profile.source_sha256) == 64
    assert profile.variables["event_30d"].kind == "binary"
    assert profile.variables["age_years"].kind == "continuous"
    assert profile.variables["visit_date"].kind == "date"
    assert profile.variables["participant_id"].kind == "identifier-candidate"
    assert profile.variables["participant_id"].original_name == "participant_id"
    assert profile.variables["participant_id"].display_name == "Participant id"


def test_profile_excel_emits_value_free_quality_warnings(tmp_path: Path) -> None:
    """Dropping quality checks can expose identifiers or conceal invalid analysis inputs."""
    workbook = write_workbook(
        tmp_path / "quality.xlsx",
        ["empty_column", "patient_id", "measure", "mixed_value", "comment"],
        [
            [None, "patient-001", "1", 1, "first note about recovery"],
            [None, "patient-002", "inf", "two", "second note about recovery"],
            [None, "patient-002", "3", 3, "third note about recovery"],
            [None, "patient-004", "4", "four", "fourth note about recovery"],
            [None, "patient-005", "5", 5, "fifth note about recovery"],
        ],
    )

    profile = profile_excel(workbook)

    warning_codes = {warning.code for warning in profile.warnings}
    assert {"empty_column", "duplicated_identifier", "non_finite_values", "mixed_types", "suspicious_identifier_leakage"} <= warning_codes
    assert profile.variables["comment"].kind == "free-text"
    assert profile.variables["patient_id"].kind == "identifier-candidate"
    assert "patient-001" not in str(asdict(profile))


def test_profile_excel_rejects_unknown_sheet_without_changing_source(core_workbook: Path) -> None:
    """An invalid sheet selection must not fall back silently or alter the workbook."""
    before = file_sha256(core_workbook)

    with pytest.raises(ValueError, match="unknown_sheet"):
        profile_excel(core_workbook, sheet="Not Present")

    assert file_sha256(core_workbook) == before


def test_fixture_complete_case_group_difference_is_documented_value() -> None:
    """Changing fixture values must retain the known later Welch estimate contract."""
    import pandas as pd

    frame = pd.read_excel(FIXTURE_PATH, sheet_name="Analysis")
    means = frame.groupby("treatment_group")["age_years"].mean()

    assert means["Treatment"] - means["Control"] == pytest.approx(-4.1667, abs=1e-4)
