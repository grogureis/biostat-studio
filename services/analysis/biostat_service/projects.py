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

from biostat_service.contracts import StudyBrief
from biostat_service.data_intake import DataProfile, DataWarning, VariableMetadata


SCHEMA_VERSION = 1
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
METHOD_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


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
                isinstance(method_id, str) and METHOD_ID.fullmatch(method_id)
                for method_id in method_ids_value
            )
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


def _load_existing_manifest(project: LocalProject, profile: DataProfile) -> None:
    try:
        manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_project_manifest") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_project_schema")
    if manifest.get("source_sha256") != profile.source_sha256:
        raise ValueError("source_fingerprint_mismatch")


def create_project(root: Path, brief: StudyBrief, profile: DataProfile) -> LocalProject:
    """Create or reopen one project folder without copying its source dataset."""
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
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_path": str(profile.source_path.resolve()),
        "source_sha256": profile.source_sha256,
        "data_profile": _profile_manifest(profile),
        "decisions": {"study_brief": brief.model_dump(mode="json")},
        "generated_artifacts": [],
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
