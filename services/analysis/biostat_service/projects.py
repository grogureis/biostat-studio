"""Atomic, local-only project manifests and append-only audit records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from uuid import UUID, uuid4

from biostat_service.contracts import StudyBrief
from biostat_service.data_intake import DataProfile, DataWarning, VariableMetadata
from biostat_service.study_model import VERTICAL_SLICE_METHOD_IDS


SCHEMA_VERSION = 2
METHODOLOGY_RELATIVE = Path("source") / "methodology.txt"
ARTIFACT_DIRECTORIES = (
    Path("artifacts"),
    Path("artifacts") / "figures",
    Path("artifacts") / "reports",
    Path("artifacts") / "tables",
)
AUDIT_EVENT_TYPES = frozenset(
    {
        "data_imported",
        "data_structure_approved",
        "study_brief_updated",
        "plan_generated",
        "plan_approved",
        "analysis_queued",
        "analysis_started",
        "analysis_completed",
        "analysis_failed",
        "analysis_cancelled",
        "artifacts_generated",
        "report_exported",
    }
)
AUDIT_ACTORS = frozenset({"user", "system"})
AUDIT_STATUSES = frozenset(
    {"queued", "running", "completed", "failed", "cancelled", "approved"}
)
AUDIT_EVENT_FIELDS = frozenset(
    {"type", "actor", "plan_version", "data_fingerprint", "status", "method_ids"}
)
FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class LocalProject:
    """References to the files owned by a single local project folder."""

    root: Path

    @property
    def manifest_path(self) -> Path:
        return self.root / "project.json"

    @property
    def audit_path(self) -> Path:
        return self.root / "audit.jsonl"


@dataclass(frozen=True)
class AuditEvent:
    """A fixed, value-free audit record accepted by local project persistence."""

    type: str
    actor: str
    plan_version: int | None = None
    data_fingerprint: str | None = None
    status: str | None = None
    method_ids: tuple[str, ...] | None = None

    @classmethod
    def from_mapping(cls, event: Mapping[str, Any]) -> "AuditEvent":
        if not isinstance(event, Mapping):
            raise TypeError("audit_event_must_be_mapping")
        unknown_fields = set(event) - AUDIT_EVENT_FIELDS
        if unknown_fields:
            raise ValueError("unknown_audit_event_fields")
        missing_fields = {"type", "actor"} - set(event)
        if missing_fields:
            raise ValueError("missing_audit_event_fields")

        event_type = event["type"]
        if not isinstance(event_type, str) or event_type not in AUDIT_EVENT_TYPES:
            raise ValueError("invalid_audit_event_type")
        actor = event["actor"]
        if not isinstance(actor, str) or actor not in AUDIT_ACTORS:
            raise ValueError("invalid_audit_actor")

        plan_version = event.get("plan_version")
        if "plan_version" in event and (
            type(plan_version) is not int or plan_version < 1
        ):
            raise TypeError("invalid_audit_plan_version")

        data_fingerprint = event.get("data_fingerprint")
        if "data_fingerprint" in event and (
            not isinstance(data_fingerprint, str)
            or not FINGERPRINT.fullmatch(data_fingerprint)
        ):
            raise TypeError("invalid_audit_data_fingerprint")

        status = event.get("status")
        if "status" in event and (
            not isinstance(status, str) or status not in AUDIT_STATUSES
        ):
            raise ValueError("invalid_audit_status")

        method_ids_value = event.get("method_ids")
        if "method_ids" not in event:
            method_ids = None
        elif (
            not isinstance(method_ids_value, list)
            or not method_ids_value
            or not all(
                isinstance(method_id, str) and method_id in VERTICAL_SLICE_METHOD_IDS
                for method_id in method_ids_value
            )
            or len(set(method_ids_value)) != len(method_ids_value)
        ):
            raise TypeError("invalid_audit_method_ids")
        else:
            method_ids = tuple(method_ids_value)

        return cls(
            type=event_type,
            actor=actor,
            plan_version=plan_version,
            data_fingerprint=data_fingerprint,
            status=status,
            method_ids=method_ids,
        )

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"type": self.type, "actor": self.actor}
        if self.plan_version is not None:
            record["plan_version"] = self.plan_version
        if self.data_fingerprint is not None:
            record["data_fingerprint"] = self.data_fingerprint
        if self.status is not None:
            record["status"] = self.status
        if self.method_ids is not None:
            record["method_ids"] = list(self.method_ids)
        return record


@dataclass(frozen=True)
class MethodologyRecord:
    """One methodology document as the project durably remembers it."""

    text: str
    source_sha256: str
    source_format: str
    original_name: str
    char_count: int
    truncated: bool


def _json_value(value: Any) -> Any:
    """Return an explicit JSON representation or reject unsupported metadata."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non_finite_metadata")
        return value
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, Path):
        return {"type": "path", "value": str(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("metadata_mapping_keys_must_be_strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return {"type": "tuple", "items": [_json_value(item) for item in value]}
    item = getattr(value, "item", None)
    if callable(item):
        return _json_value(item())
    raise TypeError(f"unsupported_metadata_type:{type(value).__name__}")


def _decoded_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decoded_json_value(item) for item in value]
    if isinstance(value, dict):
        value_type = value.get("type")
        if value_type == "tuple" and set(value) == {"type", "items"}:
            return tuple(_decoded_json_value(item) for item in value["items"])
        if value_type in {"date", "datetime", "path"} and set(value) == {"type", "value"}:
            return value["value"]
        return {key: _decoded_json_value(item) for key, item in value.items()}
    return value


def _variable_manifest(metadata: VariableMetadata) -> dict[str, Any]:
    return {
        "source_label": _json_value(metadata.source_label),
        "original_name": metadata.original_name,
        "display_name": metadata.display_name,
        "kind": metadata.kind,
        "non_missing": metadata.non_missing,
        "missing": metadata.missing,
        "unique_values": metadata.unique_values,
    }


def _warning_manifest(warning: DataWarning) -> dict[str, Any]:
    return {
        "code": warning.code,
        "column": warning.column,
        "message": warning.message,
    }


def _profile_manifest(profile: DataProfile) -> dict[str, Any]:
    return {
        "sheets": list(profile.sheets),
        "selected_sheet": profile.selected_sheet,
        "rows": profile.rows,
        "columns": profile.columns,
        "missing_cells": profile.missing_cells,
        "variables": {
            key: _variable_manifest(metadata)
            for key, metadata in profile.variables.items()
        },
        "warnings": [_warning_manifest(warning) for warning in profile.warnings],
    }


def _serialized_json(value: Mapping[str, Any], *, indent: int | None = None) -> str:
    return json.dumps(
        _json_value(value), ensure_ascii=False, indent=indent, allow_nan=False
    )


def _atomic_text_write(destination: Path, text: str) -> None:
    """Write a sibling temporary file, sync it, then atomically replace destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        try:
            directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_json_write(destination: Path, value: dict[str, Any]) -> None:
    """Persist a JSON manifest without exposing a partially-written destination."""
    _atomic_text_write(destination, _serialized_json(value, indent=2) + "\n")


def _atomic_bytes_write(destination: Path, value: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_file_copy(source: Path, destination: Path) -> None:
    """Copy a completed artifact without exposing a partial destination."""
    source = Path(source)
    if not source.is_file():
        raise ValueError("artifact_source_missing")
    _atomic_bytes_write(Path(destination), source.read_bytes())


def _safe_relative_reference(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("unsafe_project_reference")
    relative = Path(value)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("unsafe_project_reference")
    resolved_root = root.resolve()
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("unsafe_project_reference")
    try:
        candidate.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("unsafe_project_reference") from exc
    return candidate


def _validate_relative_references(root: Path, value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "relative_path":
                _safe_relative_reference(root, item)
            else:
                _validate_relative_references(root, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_relative_references(root, item)


def _create_artifact_directories(root: Path) -> None:
    resolved_root = root.resolve()
    for relative_directory in ARTIFACT_DIRECTORIES:
        directory = root / relative_directory
        if directory.is_symlink():
            raise ValueError("unsafe_artifact_path")
        resolved_directory = directory.resolve(strict=False)
        try:
            resolved_directory.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("unsafe_artifact_path") from exc
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.resolve().is_relative_to(resolved_root):
            raise ValueError("unsafe_artifact_path")


def _read_manifest(project: LocalProject) -> dict[str, Any]:
    try:
        manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_project_manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError("invalid_project_manifest")
    return manifest


def _load_existing_manifest(project: LocalProject, profile: DataProfile) -> None:
    manifest = _read_manifest(project)
    if manifest.get("schema_version") == 1:
        _migrate_schema_one(project, manifest, profile)
        return
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_project_schema")
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("sha256") != profile.source_sha256:
        raise ValueError("source_fingerprint_mismatch")


def _migrate_schema_one(
    project: LocalProject, manifest: Mapping[str, Any], profile: DataProfile
) -> None:
    """Migrate legacy state only with a freshly picker-approved source snapshot."""
    if manifest.get("source_sha256") != profile.source_sha256:
        raise ValueError("source_fingerprint_mismatch")
    data_profile = manifest.get("data_profile")
    decisions = manifest.get("decisions")
    if not isinstance(data_profile, Mapping) or not isinstance(decisions, Mapping):
        raise ValueError("invalid_project_manifest")
    try:
        brief = StudyBrief.model_validate(decisions["study_brief"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_project_manifest") from exc
    snapshot_relative = Path("source") / "source.xlsx"
    snapshot = project.root / snapshot_relative
    if snapshot.is_symlink():
        raise ValueError("unsafe_source_snapshot_path")
    _atomic_bytes_write(snapshot, profile.source_path.read_bytes())
    migrated = {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(uuid4()),
        "source": {
            "relative_path": snapshot_relative.as_posix(),
            "sha256": profile.source_sha256,
            "selected_sheet": profile.selected_sheet,
        },
        "data_profile": dict(data_profile),
        "state": _initial_state(brief),
    }
    atomic_json_write(project.manifest_path, migrated)


def _initial_state(brief: StudyBrief) -> dict[str, Any]:
    return {
        "study_brief": brief.model_dump(mode="json"),
        "approved_roles": None,
        "plan": None,
        "terminal_jobs": {},
        "reports": [],
    }


def load_project(root: Path) -> tuple[LocalProject, dict[str, Any]]:
    """Load and validate a durable project without reading patient rows."""
    project = LocalProject(Path(root))
    manifest = _read_manifest(project)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_project_schema")
    try:
        UUID(str(manifest["project_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_project_manifest") from exc
    source = manifest.get("source")
    state = manifest.get("state")
    if not isinstance(source, dict) or not isinstance(state, dict):
        raise ValueError("invalid_project_manifest")
    source_path = _safe_relative_reference(project.root, source.get("relative_path"))
    fingerprint = source.get("sha256")
    if not isinstance(fingerprint, str) or not FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("invalid_project_manifest")
    if not source_path.is_file():
        raise ValueError("project_source_missing")
    from biostat_service.data_intake import sha256_file

    if sha256_file(source_path) != fingerprint:
        raise ValueError("source_fingerprint_mismatch")
    _validate_relative_references(project.root, manifest)
    return project, manifest


def profile_from_manifest(project: LocalProject, manifest: Mapping[str, Any]) -> DataProfile:
    """Reconstruct structural metadata while keeping patient rows on disk."""
    source = manifest.get("source")
    profile = manifest.get("data_profile")
    if not isinstance(source, Mapping) or not isinstance(profile, Mapping):
        raise ValueError("invalid_project_manifest")
    source_path = _safe_relative_reference(project.root, source.get("relative_path"))
    variables_value = profile.get("variables")
    warnings_value = profile.get("warnings")
    if not isinstance(variables_value, Mapping) or not isinstance(warnings_value, list):
        raise ValueError("invalid_project_manifest")
    try:
        variables = {
            str(key): VariableMetadata(
                source_label=_decoded_json_value(value["source_label"]),
                original_name=str(value["original_name"]),
                display_name=str(value["display_name"]),
                kind=str(value["kind"]),
                non_missing=int(value["non_missing"]),
                missing=int(value["missing"]),
                unique_values=int(value["unique_values"]),
            )
            for key, value in variables_value.items()
        }
        warnings = tuple(
            DataWarning(
                code=str(value["code"]),
                column=None if value.get("column") is None else str(value["column"]),
                message=str(value["message"]),
            )
            for value in warnings_value
        )
        return DataProfile(
            source_path=source_path,
            source_sha256=str(source["sha256"]),
            sheets=tuple(str(item) for item in profile["sheets"]),
            selected_sheet=str(source["selected_sheet"]),
            rows=int(profile["rows"]),
            columns=int(profile["columns"]),
            missing_cells=int(profile["missing_cells"]),
            variables=variables,
            warnings=warnings,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_project_manifest") from exc


def save_project_state(project: LocalProject, state: Mapping[str, Any]) -> None:
    """Atomically replace only the durable workflow state after containment checks."""
    manifest = _read_manifest(project)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_project_schema")
    safe_state = _json_value(dict(state))
    _validate_relative_references(project.root, safe_state)
    manifest["state"] = safe_state
    atomic_json_write(project.manifest_path, manifest)


def create_project(root: Path, brief: StudyBrief, profile: DataProfile) -> LocalProject:
    """Create or reopen one project folder, snapshotting its source workbook."""
    project = LocalProject(Path(root))
    if project.root.exists() and not project.root.is_dir():
        raise ValueError("project_root_not_directory")

    if project.manifest_path.exists():
        _load_existing_manifest(project, profile)
        _create_artifact_directories(project.root)
        if project.audit_path.is_symlink():
            raise ValueError("unsafe_audit_path")
        if not project.audit_path.exists():
            _atomic_text_write(project.audit_path, "")
        return project

    if project.audit_path.exists() or project.audit_path.is_symlink():
        raise ValueError("orphaned_audit_log")
    project.root.mkdir(parents=True, exist_ok=True)
    _create_artifact_directories(project.root)
    snapshot_relative = Path("source") / "source.xlsx"
    snapshot = project.root / snapshot_relative
    if snapshot.exists() or snapshot.is_symlink():
        raise ValueError("unsafe_source_snapshot_path")
    _atomic_bytes_write(snapshot, profile.source_path.read_bytes())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(uuid4()),
        "source": {
            "relative_path": snapshot_relative.as_posix(),
            "sha256": profile.source_sha256,
            "selected_sheet": profile.selected_sheet,
        },
        "data_profile": _profile_manifest(profile),
        "state": _initial_state(brief),
    }
    atomic_json_write(project.manifest_path, manifest)
    _atomic_text_write(project.audit_path, "")
    return project


def append_audit_event(project: LocalProject, event: Mapping[str, Any]) -> None:
    """Durably append one JSON-safe decision or lifecycle event to the audit trail."""
    event_record = AuditEvent.from_mapping(event).as_record()
    event_record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    serialized = _serialized_json(event_record) + "\n"
    project.root.mkdir(parents=True, exist_ok=True)
    if project.audit_path.is_symlink():
        raise ValueError("unsafe_audit_path")
    with project.audit_path.open("a", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())


# MethodologyDocument is kept as Any to avoid circular imports: methodology_intake
# does not import projects at module level today, but if it ever does, a top-level
# import here would create a circular dependency. This deferred-import pattern is the
# same rationale as sha256_file inside load_project (line 436).
def attach_methodology(
    project: LocalProject, document: Any, original_name: str
) -> None:
    """Store the extracted text next to the workbook snapshot, atomically.

    The ORIGINAL .docx/.pdf is deliberately NOT copied (STATE.md 0d): the only
    thing it could yield was text, and the text is already here. Its name and
    sha256 are kept so "which document did this come from" stays answerable.
    """
    destination = _safe_relative_reference(project.root, METHODOLOGY_RELATIVE.as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text_write(destination, document.text)
    manifest = _read_manifest(project)
    manifest["methodology"] = {
        "relative_path": METHODOLOGY_RELATIVE.as_posix(),
        "sha256": document.source_sha256,
        "source_format": document.source_format,
        "original_name": original_name,
        "char_count": document.char_count,
        "truncated": document.truncated,
    }
    _validate_relative_references(project.root, manifest)
    atomic_json_write(project.manifest_path, manifest)


def read_methodology(project: LocalProject) -> MethodologyRecord | None:
    """Read the stored document text, or None when the study has no document."""
    manifest = _read_manifest(project)
    record = manifest.get("methodology")
    if not isinstance(record, Mapping):
        return None
    path = _safe_relative_reference(project.root, record.get("relative_path"))
    if not path.is_file():
        raise ValueError("methodology_document_missing")
    return MethodologyRecord(
        text=path.read_text(encoding="utf-8"),
        source_sha256=str(record.get("sha256", "")),
        source_format=str(record.get("source_format", "")),
        original_name=str(record.get("original_name", "")),
        char_count=int(record.get("char_count", 0)),
        truncated=bool(record.get("truncated", False)),
    )
