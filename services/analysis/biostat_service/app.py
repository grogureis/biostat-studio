"""Authenticated local API assembly for the BioStat analysis service."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, List, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from uvicorn import Config, Server

from .analyses import AnalysisBundle, run_plan
from .contracts import AnalysisPlan, StudyBrief, VariableRole
from .data_intake import DataProfile, profile_excel
from .jobs import JobManager, JobState
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
    roles: list[VariableRole] = Field(default_factory=list)


class RunAnalysisRequest(BaseModel):
    project_id: UUID
    approved_plan_version: int = Field(ge=1)


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
    plan: AnalysisPlan | None = None
    bundle: AnalysisBundle | None = None
    figures: list[FigureArtifact] | None = None
    job_ids: set[UUID] = field(default_factory=set)


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
            root = Path(request.project_root) if request.project_root else profile.source_path.with_suffix(".biostat")
            project = create_project(root, request.brief, profile)
            append_audit_event(project, {"type": "data_imported", "actor": "user"})
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(status_code=422, detail="project_creation_failed")
        project_id = uuid4()
        projects[project_id] = ProjectContext(project=project, profile=profile, brief=request.brief)
        return {"id": str(project_id), "profile": _profile_payload(profile)}

    @v1.post("/plans")
    def create_plan(request: PlanRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        roles = {role.name: role for role in request.roles} or _default_roles(context)
        plan = build_plan(context.brief, context.profile, roles)
        context.plan = plan
        append_audit_event(context.project, {"type": "plan_generated", "actor": "system", "plan_version": plan.version})
        return plan.model_dump(mode="json")

    @v1.post("/jobs")
    def create_job(request: RunAnalysisRequest) -> dict[str, Any]:
        context = _get_context(projects, request.project_id)
        if context.plan is None or context.plan.version != request.approved_plan_version:
            raise HTTPException(status_code=409, detail="approved_plan_required")
        if context.plan.blocking_errors:
            raise HTTPException(status_code=422, detail="plan_has_blocking_errors")
        plan = context.plan
        append_audit_event(context.project, {"type": "plan_approved", "actor": "user", "plan_version": plan.version, "status": "approved"})

        def run(is_cancelled) -> dict[str, Any]:
            if is_cancelled():
                return {}
            frame = _read_frame(context)
            if is_cancelled():
                return {}
            bundle = run_plan(frame, plan)
            if is_cancelled():
                return {}
            figures = build_figures(frame, plan, bundle, context.project.root / "artifacts" / "figures", context.brief.language)
            if is_cancelled():
                return {}
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
            context.bundle = bundle
            context.figures = figures
            return {"results": [result.model_dump(mode="json") for result in bundle.results.values()], "warnings": bundle.warnings}

        job = manager.submit(run)
        context.job_ids.add(job.id)
        append_audit_event(context.project, {"type": "analysis_queued", "actor": "system", "plan_version": plan.version, "status": "queued"})
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
        if request.job_id not in context.job_ids:
            raise HTTPException(status_code=409, detail="job_result_mismatch")
        try:
            job = manager.get(request.job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job_not_found") from exc
        if job.status != "completed" or context.plan is None or context.bundle is None:
            raise HTTPException(status_code=409, detail="completed_analysis_required")
        destination = Path(request.destination)
        try:
            build_results_docx(context.project, context.brief, context.plan, context.bundle, context.figures or [], request.language, destination)
            append_audit_event(context.project, {"type": "report_exported", "actor": "user", "plan_version": context.plan.version})
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
