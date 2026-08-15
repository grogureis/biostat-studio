"""Behavioral coverage for versioned, local-only project persistence."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from biostat_service.contracts import StudyBrief
from biostat_service.data_intake import DataProfile, VariableMetadata, profile_excel
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


def test_orphaned_audit_log_is_preserved_and_rejected_for_recovery(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Reinitializing an orphaned audit log would irreversibly lose prior decisions."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    root = tmp_path / "cardio.biostat"
    root.mkdir()
    audit_path = root / "audit.jsonl"
    original_audit = b'{"type":"data_imported","actor":"user"}\n'
    audit_path.write_bytes(original_audit)

    with pytest.raises(ValueError, match="orphaned_audit_log"):
        create_project(root, brief, profile_excel(source))

    assert audit_path.read_bytes() == original_audit
    assert not (root / "project.json").exists()


def test_audit_event_rejects_unknown_or_nested_patient_payloads(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Permitting arbitrary event fields would let patient values enter the audit trail."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    project = create_project(tmp_path / "cardio.biostat", brief, profile_excel(source))

    with pytest.raises(ValueError, match="unknown_audit_event_fields"):
        append_audit_event(
            project,
            {
                "type": "data_imported",
                "actor": "user",
                "row_values": ["patient-001"],
            },
        )
    with pytest.raises(TypeError, match="invalid_audit_method_ids"):
        append_audit_event(
            project,
            {
                "type": "analysis_completed",
                "actor": "system",
                "method_ids": ["welch_t_test", {"patient": "patient-001"}],
            },
        )
    with pytest.raises(TypeError, match="invalid_audit_plan_version"):
        append_audit_event(
            project,
            {"type": "plan_approved", "actor": "user", "plan_version": None},
        )

    assert project.audit_path.read_text(encoding="utf-8") == ""


def test_audit_event_accepts_only_typed_safe_provenance_fields(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Analysis provenance must remain auditable without carrying row-level data."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    profile = profile_excel(source)
    project = create_project(tmp_path / "cardio.biostat", brief, profile)

    append_audit_event(
        project,
        {
            "type": "analysis_completed",
            "actor": "system",
            "plan_version": 2,
            "data_fingerprint": profile.source_sha256,
            "status": "completed",
            "method_ids": ["welch_t_test", "mann_whitney_u"],
        },
    )

    event = json.loads(project.audit_path.read_text(encoding="utf-8"))
    assert event["plan_version"] == 2
    assert event["data_fingerprint"] == profile.source_sha256
    assert event["method_ids"] == ["welch_t_test", "mann_whitney_u"]
    assert event["recorded_at"].endswith("+00:00")


def test_project_rejects_symlinked_artifact_root_without_touching_outside_directory(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Following a project-owned symlink would write generated files outside the project."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    root = tmp_path / "cardio.biostat"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    (root / "artifacts").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe_artifact_path"):
        create_project(root, brief, profile_excel(source))

    assert (root / "artifacts").is_symlink()
    assert [path.name for path in outside.iterdir()] == ["keep.txt"]
    assert not (root / "project.json").exists()


def test_reopen_rejects_symlinked_audit_path_without_touching_outside_file(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Returning a project with a symlinked audit log would defer an unsafe write."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    profile = profile_excel(source)
    root = tmp_path / "cardio.biostat"
    project = create_project(root, brief, profile)
    outside_audit = tmp_path / "outside-audit.jsonl"
    outside_audit.write_text('{"keep":"outside"}\n', encoding="utf-8")
    project.audit_path.unlink()
    project.audit_path.symlink_to(outside_audit)

    with pytest.raises(ValueError, match="unsafe_audit_path"):
        create_project(root, brief, profile)

    assert outside_audit.read_text(encoding="utf-8") == '{"keep":"outside"}\n'


def test_project_manifest_encodes_tuple_source_labels_without_losing_type(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Treating tuple labels as arrays would lose a valid typed source identifier."""
    profile = DataProfile(
        source_path=tmp_path / "source.xlsx",
        source_sha256="a" * 64,
        sheets=("Analysis",),
        selected_sheet="Analysis",
        rows=2,
        columns=1,
        missing_cells=0,
        variables={
            "tuple:visit-2": VariableMetadata(
                source_label=("visit", 2),
                original_name="('visit', 2)",
                display_name="Visit 2",
                kind="continuous",
                non_missing=2,
                missing=0,
                unique_values=2,
            )
        },
        warnings=(),
    )

    project = create_project(tmp_path / "cardio.biostat", brief, profile)

    manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    assert manifest["data_profile"]["variables"]["tuple:visit-2"]["source_label"] == {
        "type": "tuple",
        "items": ["visit", 2],
    }
