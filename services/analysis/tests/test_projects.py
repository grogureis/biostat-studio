"""Behavioral coverage for versioned, local-only project persistence."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from biostat_service.contracts import StudyBrief
from biostat_service.data_intake import DataProfile, VariableMetadata, profile_excel
from biostat_service.methodology_intake import MethodologyDocument
from biostat_service.projects import (
    append_audit_event,
    attach_methodology,
    create_project,
    load_project,
    read_methodology,
    save_project_state,
)


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
    """The manifest and audit must never expose source rows or the original path."""
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
    assert manifest["schema_version"] == 2
    assert manifest["source"]["relative_path"] == "source/source.xlsx"
    assert manifest["source"]["sha256"] == profile.source_sha256
    assert manifest["data_profile"]["variables"]["int:2026"]["source_label"] == 2026
    assert manifest["state"]["study_brief"]["title"] == "Cardiovascular outcomes"
    assert manifest["state"]["reports"] == []
    assert events[-1]["type"] == "data_structure_approved"
    assert events[-1]["actor"] == "user"
    assert "patient-001" not in manifest_text
    assert str(source.resolve()) not in manifest_text
    assert (project.root / "source" / "source.xlsx").is_file()
    assert not (project.root / "project.json.tmp").exists()
    for directory in ("artifacts", "artifacts/figures", "artifacts/reports", "artifacts/tables"):
        assert (project.root / directory).is_dir()


def test_project_manifest_uses_an_immutable_relative_source_snapshot(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "private-patient-source.xlsx", ["patient_id", "age"])
    project = create_project(tmp_path / "durable.biostat", brief, profile_excel(source))

    manifest_text = project.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    snapshot = project.root / manifest["source"]["relative_path"]

    assert manifest["schema_version"] == 2
    assert manifest["source"]["relative_path"] == "source/source.xlsx"
    assert str(source.resolve()) not in manifest_text
    assert snapshot.read_bytes() == source.read_bytes()
    assert sha256(snapshot.read_bytes()).hexdigest() == manifest["source"]["sha256"]


def test_load_project_atomically_migrates_schema_one_without_retaining_source_path(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "legacy-private-source.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "legacy.biostat", brief, profile_excel(source))
    current = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    legacy = {
        "schema_version": 1,
        "source_path": str(source.resolve()),
        "source_sha256": current["source"]["sha256"],
        "data_profile": current["data_profile"],
        "decisions": {"study_brief": brief.model_dump(mode="json")},
        "generated_artifacts": [],
    }
    (project.root / current["source"]["relative_path"]).unlink()
    project.manifest_path.write_text(json.dumps(legacy), encoding="utf-8")

    create_project(project.root, brief, profile_excel(source))
    _, migrated = load_project(project.root)

    migrated_text = project.manifest_path.read_text(encoding="utf-8")
    assert migrated["schema_version"] == 2
    assert migrated["source"]["relative_path"] == "source/source.xlsx"
    assert migrated["state"]["study_brief"] == brief.model_dump(mode="json")
    assert str(source.resolve()) not in migrated_text
    assert (project.root / "source" / "source.xlsx").read_bytes() == source.read_bytes()


def test_project_state_round_trips_atomically_and_rejects_unsafe_artifact_refs(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "source.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "reopen.biostat", brief, profile_excel(source))
    state = {
        "approved_roles": [
            {"name": "outcome", "role": "outcome", "kind": "continuous", "confirmed": True}
        ],
        "plan": None,
        "terminal_jobs": {},
        "reports": [{"job_id": "11111111-1111-4111-8111-111111111111", "language": "en", "relative_path": "artifacts/reports/results-en.docx"}],
    }

    save_project_state(project, state)
    loaded_project, loaded_manifest = load_project(project.root)

    assert loaded_project.root == project.root
    assert loaded_manifest["state"] == state
    assert not list(project.root.glob(".project.json.*.tmp"))

    state["reports"][0]["relative_path"] = "../outside.docx"
    with pytest.raises(ValueError, match="unsafe_project_reference"):
        save_project_state(project, state)


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
    manifest["state"]["approved_plan_version"] = 3
    manifest["state"]["reports"] = [{"relative_path": "artifacts/reports/results.docx"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    reopened = create_project(root, brief, profile)

    assert reopened.root == original_project.root
    restored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert restored["state"]["approved_plan_version"] == 3
    assert restored["state"]["reports"] == [{"relative_path": "artifacts/reports/results.docx"}]


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


def test_audit_method_ids_require_known_unique_identifiers_in_caller_order(
    tmp_path: Path, brief: StudyBrief
) -> None:
    """Identifier-shaped patient or unknown values must not become audit provenance."""
    source = _source_workbook(tmp_path / "cardio.xlsx", ["patient_id", "age"])
    project = create_project(tmp_path / "cardio.biostat", brief, profile_excel(source))

    append_audit_event(
        project,
        {
            "type": "analysis_completed",
            "actor": "system",
            "method_ids": ["logistic_regression", "welch_t_test"],
        },
    )
    for invalid_method_ids in (
        ["patient_001"],
        ["unknown_method"],
        ["welch_t_test", "welch_t_test"],
    ):
        with pytest.raises(TypeError, match="invalid_audit_method_ids"):
            append_audit_event(
                project,
                {
                    "type": "analysis_completed",
                    "actor": "system",
                    "method_ids": invalid_method_ids,
                },
            )

    events = [
        json.loads(line)
        for line in project.audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["method_ids"] for event in events] == [
        ["logistic_regression", "welch_t_test"]
    ]


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
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"typed-header-fixture")
    profile = DataProfile(
        source_path=source,
        source_sha256=sha256(source.read_bytes()).hexdigest(),
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


def _document(text: str = "Yöntem\nRetrospektif kohort çalışması.") -> MethodologyDocument:
    return MethodologyDocument(
        source_sha256="a" * 64,
        source_format="docx",
        text=text,
        char_count=len(text),
        truncated=False,
        warnings=(),
    )


def test_attached_methodology_survives_a_reload(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "data.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "study.biostat", brief, profile_excel(source))

    attach_methodology(project, _document(), "yontem.docx")

    reloaded, manifest = load_project(project.root)
    record = read_methodology(reloaded)
    assert record is not None
    assert record.text == "Yöntem\nRetrospektif kohort çalışması."
    assert record.original_name == "yontem.docx"
    assert record.source_format == "docx"
    assert manifest["methodology"]["relative_path"] == "source/methodology.txt"
    assert manifest["schema_version"] == 2


def test_a_project_without_a_document_reads_as_none(
    tmp_path: Path, brief: StudyBrief
) -> None:
    source = _source_workbook(tmp_path / "data.xlsx", ["group", "outcome"])
    project = create_project(tmp_path / "study.biostat", brief, profile_excel(source))

    assert read_methodology(project) is None
