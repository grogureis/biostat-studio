"""Authenticated local API assembly for the BioStat analysis service."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from threading import Lock
from typing import Annotated, Any, List, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from uvicorn import Config, Server

from .analyses import AnalysisBundle, run_plan
from .contracts import AnalysisPlan, StudyBrief, VariableRole
from .data_intake import DataProfile, canonicalize_frame_columns, profile_excel
from .power import PowerRequest, PowerValidationError, compute_power
from .jobs import JobManager, JobState, StagedJobResult
from .planner import build_plan
from .projects import (
    LocalProject,
    append_audit_event,
    atomic_file_copy,
    create_project,
    load_project,
    profile_from_manifest,
    save_project_state,
)
from .reporting import build_results_docx
from .security import require_loopback, require_session, session_token
from .visuals import FigureArtifact, build_figures


API_VERSION = 1


class ReadinessServer(Server):
    """Uvicorn server that reports its ephemeral loopback port after binding."""

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            socket = self.servers[0].sockets[0]
            port = socket.getsockname()[1]
            print(json.dumps({"port": port, "api": API_VERSION}), flush=True)


class ProjectRequest(BaseModel):
    source_path: str = Field(min_length=1)
    project_root: Optional[str] = None
    brief: StudyBrief


class DataProfileRequest(BaseModel):
    source_path: str = Field(min_length=1)


class OpenProjectRequest(BaseModel):
    project_root: str = Field(min_length=1)


SAFE_METHOD_IDENTIFIER = r"^[a-z0-9_]{1,64}$"


class PlanRequest(BaseModel):
    project_id: UUID
    method_overrides: dict[
        Annotated[str, Field(pattern=SAFE_METHOD_IDENTIFIER)],
        Annotated[str, Field(pattern=SAFE_METHOD_IDENTIFIER)],
    ] = Field(default_factory=dict)


class DataApprovalRequest(BaseModel):
    roles: list[VariableRole] = Field(default_factory=list)


class RunAnalysisRequest(BaseModel):
    project_id: UUID
    approved_plan_revision: UUID
    approved_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanApprovalRequest(BaseModel):
    project_id: UUID
    revision: UUID
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReportRequest(BaseModel):
    project_id: UUID
    job_id: UUID
    language: Literal["en", "tr"]
    destination: str = Field(min_length=1)


@dataclass
class ProjectContext:
    project: LocalProject
    profile: DataProfile
    brief: StudyBrief
    data_structure_approved: bool = False
    approved_roles: dict[str, VariableRole] | None = None
    plan: AnalysisPlan | None = None
    plan_revision: UUID | None = None
    plan_digest: str | None = None
    approved_plan_revision: UUID | None = None
    approved_plan_digest: str | None = None
    bundle: AnalysisBundle | None = None
    figures: list[FigureArtifact] | None = None
    job_ids: set[UUID] = field(default_factory=set)
    job_outputs: dict[UUID, "JobOutput"] = field(default_factory=dict)
    terminal_jobs: dict[UUID, JobState] = field(default_factory=dict)
    report_refs: list[dict[str, str]] = field(default_factory=list)
    state_lock: Any = field(default_factory=Lock, repr=False)


@dataclass(frozen=True)
class JobOutput:
    plan: AnalysisPlan
    brief: StudyBrief
    bundle: AnalysisBundle
    figures: tuple[FigureArtifact, ...]
    revision: UUID
    digest: str


def _job_result_payload(bundle: AnalysisBundle) -> dict[str, Any]:
    return {
        "results": [result.model_dump(mode="json") for result in bundle.results.values()],
        "warnings": bundle.warnings,
    }


def _context_state(context: ProjectContext) -> dict[str, Any]:
    plan_record = None
    if context.plan is not None and context.plan_revision is not None and context.plan_digest:
        plan_record = {
            "content": context.plan.model_dump(mode="json"),
            "revision": str(context.plan_revision),
            "digest": context.plan_digest,
            "approved": (
                context.approved_plan_revision == context.plan_revision
                and context.approved_plan_digest == context.plan_digest
            ),
        }
    terminal_jobs: dict[str, Any] = {
        str(job_id): {
            "status": "completed",
            "result": _job_result_payload(output.bundle),
            "output": {
                "plan": output.plan.model_dump(mode="json"),
                "brief": output.brief.model_dump(mode="json"),
                "bundle": output.bundle.model_dump(mode="json"),
                "revision": str(output.revision),
                "digest": output.digest,
            },
        }
        for job_id, output in context.job_outputs.items()
    }
    terminal_jobs.update({
        str(job_id): {
            "status": state.status,
            "result": None,
            "error_code": state.error_code,
            "diagnostics": list(state.diagnostics),
        }
        for job_id, state in context.terminal_jobs.items()
        if state.status in {"failed", "cancelled"}
    })
    return {
        "study_brief": context.brief.model_dump(mode="json"),
        "approved_roles": (
            [role.model_dump(mode="json") for role in context.approved_roles.values()]
            if context.approved_roles is not None
            else None
        ),
        "plan": plan_record,
        "terminal_jobs": terminal_jobs,
        "reports": list(context.report_refs),
    }


def _persist_context(context: ProjectContext) -> None:
    save_project_state(context.project, _context_state(context))


def _restore_context(project: LocalProject, manifest: dict[str, Any]) -> ProjectContext:
    state = manifest["state"]
    brief = StudyBrief.model_validate(state["study_brief"])
    approved_roles_value = state.get("approved_roles")
    approved_roles = None
    if approved_roles_value is not None:
        approved_roles = {
            role.name: role for role in (
                VariableRole.model_validate(value) for value in approved_roles_value
            )
        }
    context = ProjectContext(
        project=project,
        profile=profile_from_manifest(project, manifest),
        brief=brief,
        data_structure_approved=approved_roles is not None,
        approved_roles=approved_roles,
        report_refs=[dict(value) for value in state.get("reports", [])],
    )
    plan_value = state.get("plan")
    if plan_value is not None:
        context.plan = AnalysisPlan.model_validate(plan_value["content"])
        context.plan_revision = UUID(plan_value["revision"])
        context.plan_digest = str(plan_value["digest"])
        if context.plan_digest != _plan_digest(context.plan):
            raise ValueError("plan_digest_mismatch")
        if plan_value.get("approved") is True:
            context.approved_plan_revision = context.plan_revision
            context.approved_plan_digest = context.plan_digest
    for job_id_value, terminal in state.get("terminal_jobs", {}).items():
        job_id = UUID(job_id_value)
        if terminal.get("status") != "completed":
            terminal_state = JobState(
                id=job_id,
                status=str(terminal["status"]),
                result=None,
                error_code=terminal.get("error_code"),
                progress=100,
                diagnostics=tuple(terminal.get("diagnostics", [])),
            )
            context.job_ids.add(job_id)
            context.terminal_jobs[job_id] = terminal_state
            continue
        output_value = terminal["output"]
        output = JobOutput(
            plan=AnalysisPlan.model_validate(output_value["plan"]),
            brief=StudyBrief.model_validate(output_value["brief"]),
            bundle=AnalysisBundle.model_validate(output_value["bundle"]),
            figures=(),
            revision=UUID(output_value["revision"]),
            digest=str(output_value["digest"]),
        )
        _validate_restored_output(output, terminal.get("result"))
        context.job_ids.add(job_id)
        context.job_outputs[job_id] = output
        context.bundle = output.bundle
    return context


def _profile_payload(profile: DataProfile) -> dict[str, Any]:
    """Expose structural metadata only; never source values or a local path."""
    return {
        "sheets": list(profile.sheets),
        "selected_sheet": profile.selected_sheet,
        "rows": profile.rows,
        "columns": profile.columns,
        "missing_cells": profile.missing_cells,
        "variables": {
            name: {
                "display_name": variable.display_name,
                "kind": variable.kind,
                "non_missing": variable.non_missing,
                "missing": variable.missing,
                "unique_values": variable.unique_values,
            }
            for name, variable in profile.variables.items()
        },
        "warnings": [
            {"code": warning.code, "column": warning.column, "message": warning.message}
            for warning in profile.warnings
        ],
    }


def _job_payload(job: JobState) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error_code": job.error_code,
        "message": job.message,
        "diagnostics": list(job.diagnostics),
    }


def _plan_digest(plan: AnalysisPlan) -> str:
    canonical = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _validate_restored_output(output: JobOutput, stored_result: Any) -> None:
    """Reject corrupted durable output before it can become reportable."""
    if output.digest != _plan_digest(output.plan):
        raise ValueError("job_plan_digest_mismatch")
    provenance = output.bundle.provenance
    fingerprint = provenance.data_fingerprint
    if (
        len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
        or provenance.plan_version != output.plan.version
    ):
        raise ValueError("job_provenance_mismatch")
    planned_methods = {item.method for item in output.plan.items}
    for result in output.bundle.results.values():
        result_provenance = result.provenance
        if (
            result_provenance.data_fingerprint != provenance.data_fingerprint
            or result_provenance.plan_version != provenance.plan_version
            or result_provenance.library_versions != provenance.library_versions
            or result.method not in planned_methods
        ):
            raise ValueError("job_provenance_mismatch")
    if stored_result != _job_result_payload(output.bundle):
        raise ValueError("job_result_mismatch")


def _validated_roles(
    context: ProjectContext, submitted: list[VariableRole]
) -> dict[str, VariableRole]:
    if not submitted:
        raise HTTPException(status_code=422, detail="explicit_variable_snapshot_required")
    roles = {role.name: role for role in submitted}
    if len(roles) != len(submitted) or set(roles) != set(context.profile.variables):
        raise HTTPException(status_code=422, detail="complete_variable_snapshot_required")
    allowed_roles = {"outcome", "exposure", "covariate", "pair_id", "none", "exclude"}
    allowed_kinds = {"continuous", "binary", "categorical", "date", "identifier", "exclude"}
    if any(
        not role.confirmed
        or role.role not in allowed_roles
        or role.kind not in allowed_kinds
        for role in roles.values()
    ):
        raise HTTPException(status_code=422, detail="unconfirmed_variable_roles")
    expected = {
        **{name: "outcome" for name in context.brief.outcome_variables},
        **{name: "exposure" for name in context.brief.exposure_variables},
        **{name: "covariate" for name in context.brief.covariates},
    }
    if context.brief.pair_id_variable:
        expected[context.brief.pair_id_variable] = "pair_id"
    if any(name not in roles or roles[name].role != role for name, role in expected.items()):
        raise HTTPException(status_code=422, detail="study_role_mismatch")
    warnings_by_column = {
        (warning.column, warning.code) for warning in context.profile.warnings
    }
    for name, role in roles.items():
        metadata = context.profile.variables[name]
        if (
            metadata.kind == "identifier-candidate"
            or (name, "suspicious_identifier_leakage") in warnings_by_column
        ) and role.role not in {"pair_id", "exclude"}:
            raise HTTPException(status_code=422, detail="unresolved_identifier_role")
        if (name, "mixed_types") in warnings_by_column and role.kind == metadata.kind:
            raise HTTPException(status_code=422, detail="unresolved_mixed_type")
    return roles


def _apply_approved_kinds(
    frame: pd.DataFrame, context: ProjectContext
) -> pd.DataFrame:
    if context.approved_roles is None:
        return frame
    converted = frame.copy()
    for name, role in context.approved_roles.items():
        if role.role in {"none", "exclude", "pair_id"}:
            continue
        metadata = context.profile.variables[name]
        if role.kind == metadata.kind:
            continue
        if name not in converted.columns:
            raise ValueError("approved_variable_missing")
        if role.kind == "continuous":
            converted[name] = pd.to_numeric(converted[name], errors="coerce")
        elif role.kind in {"binary", "categorical"}:
            converted[name] = converted[name].astype("string")
        else:
            raise ValueError("unsupported_approved_kind")
    return converted


def _read_frame(context: ProjectContext) -> pd.DataFrame:
    """Read fresh source bytes and reject modification after profiling."""
    source = context.profile.source_path
    before = sha256(source.read_bytes()).hexdigest()
    if before != context.profile.source_sha256:
        raise ValueError("source_file_changed")
    frame = pd.read_excel(source, sheet_name=context.profile.selected_sheet)
    if sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("source_file_changed")
    return _apply_approved_kinds(canonicalize_frame_columns(frame), context)


def _get_context(projects: dict[UUID, ProjectContext], project_id: UUID) -> ProjectContext:
    try:
        return projects[project_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


def _approved_execution_snapshot(
    context: ProjectContext, request: RunAnalysisRequest
) -> tuple[AnalysisPlan, StudyBrief, UUID, str]:
    with context.state_lock:
        if (
            context.plan is None
            or request.approved_plan_revision != context.plan_revision
            or request.approved_plan_digest != context.plan_digest
            or request.approved_plan_revision != context.approved_plan_revision
            or request.approved_plan_digest != context.approved_plan_digest
        ):
            raise HTTPException(status_code=409, detail="approved_plan_required")
        if context.plan.blocking_errors:
            raise HTTPException(status_code=422, detail="plan_has_blocking_errors")
        if context.plan_revision is None or context.plan_digest is None:
            raise HTTPException(status_code=409, detail="approved_plan_required")
        return (
            context.plan.model_copy(deep=True),
            context.brief.model_copy(deep=True),
            context.plan_revision,
            context.plan_digest,
        )


def create_app() -> FastAPI:
    """Create a local-only API without public docs or data-bearing error messages."""
    session_token()
    projects: dict[UUID, ProjectContext] = {}
    manager = JobManager(max_workers=1)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            manager.shutdown()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.projects = projects
    app.state.job_manager = manager

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(
        _request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        fields = []
        for error in exception.errors():
            location = [str(part) for part in error.get("loc", ()) if part != "body"]
            field_name = ".".join(location)
            safe_field = (
                field_name
                if field_name.replace("_", "").replace("-", "").replace(".", "").isalnum()
                else "request"
            )
            error_type = str(error.get("type", "invalid"))
            safe_code = error_type if error_type.replace("_", "").isalnum() else "invalid"
            fields.append({"field": safe_field, "code": safe_code})
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "fields": fields,
                }
            },
        )

    @app.get("/health", dependencies=[Depends(require_loopback)])
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "biostat-analysis", "api": API_VERSION}

    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_session)])

    @v1.get("/session")
    def session() -> dict[str, int]:
        return {"api": API_VERSION}

    @v1.post("/power")
    def power_calculation(request: PowerRequest) -> dict[str, Any]:
        try:
            result = compute_power(request)
        except PowerValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @v1.post("/data/profile")
    def data_profile(request: DataProfileRequest) -> dict[str, Any]:
        try:
            return _profile_payload(profile_excel(Path(request.source_path)))
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(status_code=422, detail="data_profile_failed")

    @v1.post("/projects")
    def create_local_project(request: ProjectRequest) -> dict[str, Any]:
        try:
            profile = profile_excel(Path(request.source_path))
            root = (
                Path(request.project_root)
                if request.project_root
                else profile.source_path.with_suffix(".biostat")
            )
            project = create_project(root, request.brief, profile)
            append_audit_event(project, {"type": "data_imported", "actor": "user"})
            _, manifest = load_project(project.root)
            profile = profile_from_manifest(project, manifest)
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(status_code=422, detail="project_creation_failed")
        project_id = UUID(manifest["project_id"])
        projects[project_id] = ProjectContext(
            project=project, profile=profile, brief=request.brief
        )
        return {"id": str(project_id), "profile": _profile_payload(profile)}

    @v1.post("/projects/open")
    def open_local_project(request: OpenProjectRequest) -> dict[str, Any]:
        try:
            project, manifest = load_project(Path(request.project_root))
            project_id = UUID(manifest["project_id"])
            context = _restore_context(project, manifest)
        except (OSError, KeyError, TypeError, ValueError):
            raise HTTPException(status_code=422, detail="project_open_failed")
        if project_id in projects:
            raise HTTPException(status_code=409, detail="project_already_open")
        projects[project_id] = context
        for job_id, output in context.job_outputs.items():
            manager.restore_terminal(
                JobState(
                    id=job_id,
                    status="completed",
                    result=_job_result_payload(output.bundle),
                    progress=100,
                )
            )
        for job_id, state in context.terminal_jobs.items():
            manager.restore_terminal(state)
        completed_job_id = next(reversed(context.job_outputs), None)
        return {
            "id": str(project_id),
            "profile": _profile_payload(context.profile),
            "brief": context.brief.model_dump(mode="json"),
            "roles": (
                [role.model_dump(mode="json") for role in context.approved_roles.values()]
                if context.approved_roles is not None else []
            ),
            "plan": (
                {
                    **context.plan.model_dump(mode="json"),
                    "revision": str(context.plan_revision),
                    "digest": context.plan_digest,
                }
                if context.plan is not None else None
            ),
            "approved_plan": context.approved_plan_revision is not None,
            "completed_job_id": str(completed_job_id) if completed_job_id else None,
            "results": (
                _job_result_payload(context.job_outputs[completed_job_id].bundle)["results"]
                if completed_job_id else []
            ),
        }

    @v1.post("/plans")
    def create_plan(request: PlanRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        with context.state_lock:
            if not context.data_structure_approved or context.approved_roles is None:
                raise HTTPException(
                    status_code=409, detail="data_structure_approval_required"
                )
            plan = build_plan(
                context.brief,
                context.profile,
                context.approved_roles,
                request.method_overrides or None,
            )
            context.plan = plan
            context.plan_revision = uuid4()
            context.plan_digest = _plan_digest(plan)
            context.approved_plan_revision = None
            context.approved_plan_digest = None
            plan_event: dict[str, Any] = {
                "type": "plan_generated",
                "actor": "user" if request.method_overrides else "system",
                "plan_version": plan.version,
            }
            planned_methods = list(dict.fromkeys(item.method for item in plan.items))
            if planned_methods:
                plan_event["method_ids"] = planned_methods
            append_audit_event(context.project, plan_event)
            _persist_context(context)
            return {
                **plan.model_dump(mode="json"),
                "revision": str(context.plan_revision),
                "digest": context.plan_digest,
            }

    @v1.post("/plans/approval")
    def approve_plan(request: PlanApprovalRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        with context.state_lock:
            if (
                context.plan is None
                or request.revision != context.plan_revision
                or request.digest != context.plan_digest
            ):
                raise HTTPException(status_code=409, detail="plan_revision_mismatch")
            context.approved_plan_revision = request.revision
            context.approved_plan_digest = request.digest
            append_audit_event(
                context.project,
                {
                    "type": "plan_approved",
                    "actor": "user",
                    "plan_version": context.plan.version,
                    "status": "approved",
                },
            )
            _persist_context(context)
        return {"approved": True, "revision": str(request.revision), "digest": request.digest}

    @v1.post("/projects/{project_id}/data-approval")
    def approve_data_structure(
        project_id: UUID, request: DataApprovalRequest
    ) -> dict[str, bool]:
        context = _get_context(projects, project_id)
        with context.state_lock:
            if not context.data_structure_approved:
                roles = _validated_roles(context, request.roles)
                append_audit_event(
                    context.project,
                    {"type": "data_structure_approved", "actor": "user"},
                )
                context.approved_roles = roles
                context.data_structure_approved = True
                _persist_context(context)
        return {"approved": True}

    @v1.post("/jobs")
    def create_job(request: RunAnalysisRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        plan, brief, revision, digest = _approved_execution_snapshot(context, request)
        job_id = uuid4()
        staging_root = context.project.root / "artifacts" / f".staging-{job_id}"
        final_root = context.project.root / "artifacts" / "jobs" / str(job_id)

        def run(is_cancelled, update_progress) -> StagedJobResult | dict[str, Any]:
            if is_cancelled():
                return {}
            update_progress(20, "reading_data")
            frame = _read_frame(context)
            if is_cancelled():
                return {}
            update_progress(45, "analysis_running")
            bundle = run_plan(frame, plan)
            if is_cancelled():
                return {}
            update_progress(70, "figures_building")
            if staging_root.exists() or staging_root.is_symlink():
                raise ValueError("unsafe_job_staging_path")

            def cleanup() -> None:
                if staging_root.exists():
                    shutil.rmtree(staging_root)

            try:
                figures = build_figures(
                    frame, plan, bundle, staging_root / "figures", brief.language
                )
            except Exception:
                cleanup()
                raise
            if is_cancelled():
                return StagedJobResult(result={}, publish=lambda: None, cleanup=cleanup)
            update_progress(90, "publishing")

            published_figures = tuple(
                replace(
                    figure,
                    png_path=final_root / figure.png_path.relative_to(staging_root),
                    svg_path=(
                        final_root / figure.svg_path.relative_to(staging_root)
                        if figure.svg_path is not None
                        else None
                    ),
                )
                for figure in figures
            )
            output = JobOutput(
                plan=plan,
                brief=brief,
                bundle=bundle,
                figures=published_figures,
                revision=revision,
                digest=digest,
            )

            def publish() -> None:
                jobs_root = final_root.parent
                if jobs_root.is_symlink() or final_root.exists() or final_root.is_symlink():
                    raise ValueError("unsafe_job_artifact_path")
                jobs_root.mkdir(parents=True, exist_ok=True)
                staging_root.replace(final_root)
                try:
                    append_audit_event(
                        context.project,
                        {
                            "type": "analysis_completed",
                            "actor": "system",
                            "plan_version": plan.version,
                            "data_fingerprint": bundle.provenance.data_fingerprint,
                            "status": "completed",
                            "method_ids": [result.method for result in bundle.results.values()],
                        },
                    )
                except Exception:
                    shutil.rmtree(final_root, ignore_errors=True)
                    raise
                with context.state_lock:
                    context.job_outputs[job_id] = output
                    context.bundle = bundle
                    context.figures = list(published_figures)
                    try:
                        _persist_context(context)
                    except Exception:
                        context.job_outputs.pop(job_id, None)
                        context.bundle = None
                        context.figures = None
                        shutil.rmtree(final_root, ignore_errors=True)
                        raise

            return StagedJobResult(
                result={
                    **_job_result_payload(bundle),
                },
                publish=publish,
                cleanup=cleanup,
            )

        append_audit_event(
            context.project,
            {
                "type": "analysis_queued",
                "actor": "system",
                "plan_version": plan.version,
                "status": "queued",
            },
        )
        with context.state_lock:
            context.job_ids.add(job_id)
        def record_terminal(state: JobState) -> None:
            if state.status not in {"failed", "cancelled"}:
                return
            event_type = "analysis_failed" if state.status == "failed" else "analysis_cancelled"
            with context.state_lock:
                context.terminal_jobs[state.id] = state
                append_audit_event(
                    context.project,
                    {
                        "type": event_type,
                        "actor": "system",
                        "plan_version": plan.version,
                        "status": state.status,
                    },
                )
                _persist_context(context)
        try:
            job = manager.submit(
                run, language=brief.language, job_id=job_id, on_terminal=record_terminal
            )
        except Exception:
            with context.state_lock:
                context.job_ids.discard(job_id)
            raise HTTPException(status_code=503, detail="analysis_queue_unavailable")
        return _job_payload(job)

    @v1.get("/jobs/{job_id}")
    def get_job(job_id: UUID) -> dict[str, Any]:
        try:
            return _job_payload(manager.get(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job_not_found") from exc

    @v1.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: UUID) -> dict[str, Any]:
        try:
            return _job_payload(manager.cancel(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job_not_found") from exc

    @v1.post("/reports")
    def create_report(request: ReportRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        with context.state_lock:
            if request.job_id not in context.job_ids:
                raise HTTPException(status_code=409, detail="job_result_mismatch")
        try:
            job = manager.get(request.job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job_not_found") from exc
        with context.state_lock:
            output = context.job_outputs.get(request.job_id)
        if job.status != "completed" or output is None:
            raise HTTPException(status_code=409, detail="completed_analysis_required")
        destination = Path(request.destination)
        staging = (
            context.project.root
            / "artifacts"
            / f".report-staging-{request.job_id}-{uuid4()}"
        )
        try:
            if staging.exists() or staging.is_symlink():
                raise ValueError("unsafe_report_staging")
            staging.mkdir(parents=True)
            frame = _read_frame(context)
            figures = build_figures(
                frame,
                output.plan,
                output.bundle,
                staging / "figures",
                request.language,
            )
            staged_report = staging / "report.docx"
            build_results_docx(
                context.project,
                output.brief,
                output.plan,
                output.bundle,
                figures,
                request.language,
                staged_report,
            )
            report_relative = (
                Path("artifacts")
                / "reports"
                / f"{request.job_id}-{request.language}-{uuid4()}.docx"
            )
            atomic_file_copy(staged_report, context.project.root / report_relative)
            atomic_file_copy(staged_report, destination)
            with context.state_lock:
                context.report_refs.append(
                    {
                        "job_id": str(request.job_id),
                        "language": request.language,
                        "relative_path": report_relative.as_posix(),
                    }
                )
            append_audit_event(
                context.project,
                {"type": "report_exported", "actor": "user", "plan_version": output.plan.version},
            )
            with context.state_lock:
                _persist_context(context)
        except (OSError, ValueError):
            raise HTTPException(status_code=422, detail="report_export_failed")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return {"saved": True, "filename": destination.name}

    app.include_router(v1)
    return app


def main(argv: Optional[List[str]] = None) -> None:
    """Run the local service and print its versioned readiness record."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    config = Config(create_app(), host="127.0.0.1", port=args.port, access_log=False)
    ReadinessServer(config).run()


if __name__ == "__main__":
    main()
