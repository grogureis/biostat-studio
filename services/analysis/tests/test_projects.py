"""Behavioral coverage for versioned, local-only project persistence."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from biostat_service.contracts import StudyBrief
from biostat_service.data_intake import profile_excel
from biostat_service.projects import append_audit_event, create_project


def _source_workbook(path: Path, headers: list[object]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Analysis"
    sheet.append(headers)
    sheet.append(["patient-001", 41])
    sheet.append(["patient-002", 52])
    workbook.save(path)
    return path


@pytest.fixture
def brief() -> StudyBrief:
    return StudyBrief(
        title="Cardiovascular outcomes",
        question="Does treatment reduce 30-day cardiovascular events?",
        hypothesis="Treatment is associated with fewer cardiovascular events.",
        design="cohort",
        outcome_variables=["event_30d"],
        exposure_variables=["treatment_group"],
    )


def test_project_manifest_references_source_and_records_audit_event(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Copying or exposing source rows would violate the local-data boundary."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", 2026])
    before = sha256(source.read_bytes()).hexdigest()
    profile = profile_excel(source)

    project = create_project(tmp_path / "cardio.biostat", brief, profile)
    append_audit_event(project, {"type": "data_structure_approved", "actor": "user"})

    manifest_path = project.root / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (project.root / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    manifest_text = manifest_path.read_text(encoding="utf-8")

    assert sha256(source.read_bytes()).hexdigest() == before
    assert manifest["schema_version"] == 1
    assert manifest["source_path"] == str(source.resolve())
    assert manifest["source_sha256"] == profile.source_sha256
    assert manifest["data_profile"]["variables"]["int:2026"]["source_label"] == 2026
    assert manifest["decisions"]["study_brief"]["title"] == "Cardiovascular outcomes"
    assert manifest["generated_artifacts"] == []
    assert events[-1]["type"] == "data_structure_approved"
    assert events[-1]["actor"] == "user"
    assert "patient-001" not in manifest_text
    assert not list(project.root.rglob("*.xlsx"))
    assert not (project.root / "project.json.tmp").exists()
    for directory in ("artifacts", "artifacts/figures", "artifacts/reports", "artifacts/tables"):
        assert (project.root / directory).is_dir()


def test_existing_project_is_preserved_when_schema_or_fingerprint_is_incompatible(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Replacing an incompatible project would destroy its recoverable state."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    profile = profile_excel(source)
    root = tmp_path / "cardio.biostat"
    root.mkdir()
    manifest_path = root / "project.json"
    original = {"schema_version": 99, "source_sha256": "different", "keep": "this"}
    manifest_path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported_project_schema"):
        create_project(root, brief, profile)

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == original


def test_existing_matching_project_is_reopened_without_replacing_manifest(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Reopening the same source must retain past decisions and generated artifacts."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    profile = profile_excel(source)
    root = tmp_path / "cardio.biostat"
    original_project = create_project(root, brief, profile)
    manifest_path = root / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["decisions"]["approved_plan_version"] = 3
    manifest["generated_artifacts"] = ["artifacts/reports/results.docx"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    reopened = create_project(root, brief, profile)

    assert reopened.root == original_project.root
    restored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert restored["decisions"]["approved_plan_version"] == 3
    assert restored["generated_artifacts"] == ["artifacts/reports/results.docx"]


def test_existing_project_rejects_changed_source_fingerprint_without_overwriting_it(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """A changed dataset must not silently inherit decisions from another source."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    first_profile = profile_excel(source)
    root = tmp_path / "cardio.biostat"
    create_project(root, brief, first_profile)
    manifest_path = root / "project.json"
    before = manifest_path.read_text(encoding="utf-8")

    _source_workbook(source, ["patient_id", "age", "follow_up_days"])
    changed_profile = profile_excel(source)

    with pytest.raises(ValueError, match="source_fingerprint_mismatch"):
        create_project(root, brief, changed_profile)

    assert manifest_path.read_text(encoding="utf-8") == before


def test_audit_events_are_appended_without_rewriting_prior_events(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Opening the audit log for overwrite would erase prior user decisions."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    project = create_project(tmp_path / "cardio.biostat", brief, profile_excel(source))

    append_audit_event(project, {"type": "data_imported", "actor": "user"})
    append_audit_event(project, {"type": "data_structure_approved", "actor": "user"})

    events = [
        json.loads(line)
        for line in project.audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["type"] for event in events] == [
        "data_imported",
        "data_structure_approved",
    ]
