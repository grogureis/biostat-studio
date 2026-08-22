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
from typing import Any, List, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from uvicorn import Config, Server

from .analyses import AnalysisBundle, run_plan
from .contracts import AnalysisPlan, StudyBrief, VariableRole
from .data_intake import DataProfile, profile_excel
from .jobs import JobManager, JobState, StagedJobResult
from .planner import build_plan
from .projects import LocalProject, append_audit_event, create_project
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


class PlanRequest(BaseModel):
    project_id: UUID


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
    state_lock: Any = field(default_factory=Lock, repr=False)


@dataclass(frozen=True)
class JobOutput:
    plan: AnalysisPlan
    brief: StudyBrief
    bundle: AnalysisBundle
    figures: tuple[FigureArtifact, ...]
    revision: UUID
    digest: str


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
    }


def _plan_digest(plan: AnalysisPlan) -> str:
    canonical = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _default_roles(context: ProjectContext) -> dict[str, VariableRole]:
    roles: dict[str, VariableRole] = {}
    requested = (
        *((name, "outcome") for name in context.brief.outcome_variables),
        *((name, "exposure") for name in context.brief.exposure_variables),
        *((name, "covariate") for name in context.brief.covariates),
    )
    if context.brief.pair_id_variable:
        requested = (*requested, (context.brief.pair_id_variable, "pair_id"))
    for name, role in requested:
        metadata = context.profile.variables.get(name)
        if metadata is not None:
            roles[name] = VariableRole(name=name, role=role, kind=metadata.kind, confirmed=True)
    return roles


def _read_frame(context: ProjectContext) -> pd.DataFrame:
    """Read fresh source bytes and reject modification after profiling."""
    source = context.profile.source_path
    before = sha256(source.read_bytes()).hexdigest()
    if before != context.profile.source_sha256:
        raise ValueError("source_file_changed")
    frame = pd.read_excel(source, sheet_name=context.profile.selected_sheet)
    if sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("source_file_changed")
    return frame


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
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(status_code=422, detail="project_creation_failed")
        project_id = uuid4()
        projects[project_id] = ProjectContext(
            project=project, profile=profile, brief=request.brief
        )
        return {"id": str(project_id), "profile": _profile_payload(profile)}

    @v1.post("/plans")
    def create_plan(request: PlanRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        with context.state_lock:
            if not context.data_structure_approved or context.approved_roles is None:
                raise HTTPException(
                    status_code=409, detail="data_structure_approval_required"
                )
            plan = build_plan(context.brief, context.profile, context.approved_roles)
            context.plan = plan
            context.plan_revision = uuid4()
            context.plan_digest = _plan_digest(plan)
            context.approved_plan_revision = None
            context.approved_plan_digest = None
            append_audit_event(
                context.project,
                {
                    "type": "plan_generated",
                    "actor": "system",
                    "plan_version": plan.version,
                },
            )
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
        return {"approved": True, "revision": str(request.revision), "digest": request.digest}

    @v1.post("/projects/{project_id}/data-approval")
    def approve_data_structure(
        project_id: UUID, request: DataApprovalRequest
    ) -> dict[str, bool]:
        context = _get_context(projects, project_id)
        with context.state_lock:
            if not context.data_structure_approved:
                roles = {role.name: role for role in request.roles} or _default_roles(context)
                if any(not role.confirmed for role in roles.values()):
                    raise HTTPException(
                        status_code=422, detail="unconfirmed_variable_roles"
                    )
                append_audit_event(
                    context.project,
                    {"type": "data_structure_approved", "actor": "user"},
                )
                context.approved_roles = roles
                context.data_structure_approved = True
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

            return StagedJobResult(
                result={
                    "results": [
                        result.model_dump(mode="json") for result in bundle.results.values()
                    ],
                    "warnings": bundle.warnings,
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
        try:
            job = manager.submit(run, language=brief.language, job_id=job_id)
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
        try:
            build_results_docx(
                context.project,
                output.brief,
                output.plan,
                output.bundle,
                output.figures,
                request.language,
                destination,
            )
            append_audit_event(
                context.project,
                {"type": "report_exported", "actor": "user", "plan_version": output.plan.version},
            )
        except (OSError, ValueError):
            raise HTTPException(status_code=422, detail="report_export_failed")
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
