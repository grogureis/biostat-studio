import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
import pandas as pd

from biostat_service.app import _apply_approved_kinds, create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def _approved_roles(created: dict) -> list[dict]:
    return [
        {
            "name": name,
            "role": "exposure" if name == "group" else "outcome",
            "kind": metadata["kind"],
            "confirmed": True,
        }
        for name, metadata in created["profile"]["variables"].items()
    ]


def _wait_for_job(client, headers: dict, job_id: str, terminal_states: set[str], timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        if response.json()["status"] in terminal_states:
            return response
        if time.monotonic() >= deadline:
            return response
        time.sleep(0.01)


def test_health_is_available_on_loopback(client):
    response = client.get("/health")

    assert response.json() == {"status": "ok", "service": "biostat-analysis", "api": 1}


def test_create_app_rejects_missing_session_token(monkeypatch):
    monkeypatch.delenv("BIOSTAT_SESSION_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BIOSTAT_SESSION_TOKEN must be set"):
        create_app()


def test_create_app_rejects_empty_session_token(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "")

    with pytest.raises(RuntimeError, match="BIOSTAT_SESSION_TOKEN must be set"):
        create_app()


def test_v1_rejects_missing_token(client):
    response = client.get("/v1/session")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/data/profile"),
        ("post", "/v1/projects"),
        ("post", "/v1/projects/11111111-1111-4111-8111-111111111111/data-approval"),
        ("post", "/v1/plans"),
        ("post", "/v1/plans/approval"),
        ("post", "/v1/jobs"),
        ("get", "/v1/jobs/11111111-1111-4111-8111-111111111111"),
        ("post", "/v1/jobs/11111111-1111-4111-8111-111111111111/cancel"),
        ("post", "/v1/reports"),
    ],
)
def test_every_v1_capability_rejects_missing_token_before_body_validation(
    client, method: str, path: str
):
    response = client.post(path, json={}) if method == "post" else client.get(path)
    assert response.status_code == 401


def test_v1_rejects_raw_unprefixed_token(client):
    response = client.get("/v1/session", headers={"Authorization": "test-token"})

    assert response.status_code == 401


@pytest.mark.parametrize("authorization", ["Bearer", "Basic test-token", "BearerX test-token"])
def test_v1_rejects_malformed_authorization_scheme(client, authorization):
    response = client.get("/v1/session", headers={"Authorization": authorization})

    assert response.status_code == 401


def test_v1_rejects_wrong_bearer_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401


def test_v1_accepts_session_token(client):
    response = client.get("/v1/session", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200


def test_planning_requires_an_audited_data_structure_approval(client, tmp_path: Path):
    workbook_path = tmp_path / "approval.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    workbook.active.append(["control", 1])
    workbook.active.append(["treated", 2])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Approval boundary",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    created = client.post(
        "/v1/projects",
        headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(tmp_path / "approval.biostat"), "brief": brief},
    )
    project_id = created.json()["id"]
    context = next(iter(client.app.state.projects.values()))
    assert context.approved_roles is None

    blocked = client.post("/v1/plans", headers=headers, json={"project_id": project_id})
    assert blocked.status_code == 409
    assert blocked.json() == {"detail": "data_structure_approval_required"}

    implicit = client.post(
        f"/v1/projects/{project_id}/data-approval", headers=headers, json={}
    )
    assert implicit.status_code == 422
    assert implicit.json() == {"detail": "explicit_variable_snapshot_required"}
    approved = client.post(
        f"/v1/projects/{project_id}/data-approval", headers=headers,
        json={"roles": [
            {"name": name, "role": "exposure" if name == "group" else "outcome", "kind": metadata["kind"], "confirmed": True}
            for name, metadata in created.json()["profile"]["variables"].items()
        ]},
    )
    assert approved.json() == {"approved": True}
    assert set(context.approved_roles) == {"group", "outcome"}
    assert all(role.confirmed for role in context.approved_roles.values())
    assert client.post("/v1/plans", headers=headers, json={"project_id": project_id}).status_code == 200
    audit = (tmp_path / "approval.biostat" / "audit.jsonl").read_text(encoding="utf-8")
    assert audit.count('"type": "data_structure_approved"') == 1


def test_new_plan_revision_invalidates_approval_and_rejects_stale_execution(client, tmp_path: Path):
    workbook_path = tmp_path / "revision.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    workbook.active.append(["control", 1])
    workbook.active.append(["treated", 2])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Revision binding",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    created = client.post(
        "/v1/projects", headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(tmp_path / "revision.biostat"), "brief": brief},
    ).json()
    project_id = created["id"]
    client.post(f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": _approved_roles(created)})
    first = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
    assert first["revision"]
    assert len(first["digest"]) == 64
    assert client.post(
        "/v1/plans/approval", headers=headers,
        json={"project_id": project_id, "revision": first["revision"], "digest": first["digest"]},
    ).json() == {"approved": True, "revision": first["revision"], "digest": first["digest"]}

    second = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
    assert second["version"] == first["version"] == 1
    assert second["digest"] == first["digest"]
    assert second["revision"] != first["revision"]
    stale = client.post(
        "/v1/jobs", headers=headers,
        json={"project_id": project_id, "approved_plan_revision": first["revision"], "approved_plan_digest": first["digest"]},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "approved_plan_required"}


def test_validation_errors_never_echo_paths_uris_newlines_or_brief_text(client):
    headers = {"Authorization": "Bearer test-token"}
    hostile_path = "/Users/research/patient-001\nhttps://secret.example/study.xlsx"
    patient_text = "patient-001 has a rare diagnosis and must stay private"
    response = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "source_path": hostile_path,
            "brief": {
                "title": "",
                "question": patient_text,
                "hypothesis": "x",
                "design": "cohort",
                "outcome_variables": [],
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "fields": [
                {"field": "brief.title", "code": "string_too_short"},
                {"field": "brief.hypothesis", "code": "string_too_short"},
                {"field": "brief.outcome_variables", "code": "too_short"},
            ],
        }
    }
    assert hostile_path not in response.text
    assert patient_text not in response.text
    assert "patient-001" not in response.text
    assert "secret.example" not in response.text


def test_report_uses_the_immutable_output_of_the_requested_job(client, tmp_path: Path, monkeypatch):
    workbook_path = tmp_path / "two-jobs.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["control" if index < 6 else "treated", index + 1])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Two jobs",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    created = client.post(
        "/v1/projects", headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(tmp_path / "two-jobs.biostat"), "brief": brief},
    ).json()
    project_id = created["id"]
    client.post(f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": _approved_roles(created)})

    def run_latest_plan():
        plan = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
        client.post(
            "/v1/plans/approval", headers=headers,
            json={"project_id": project_id, "revision": plan["revision"], "digest": plan["digest"]},
        )
        queued = client.post(
            "/v1/jobs", headers=headers,
            json={"project_id": project_id, "approved_plan_revision": plan["revision"], "approved_plan_digest": plan["digest"]},
        ).json()
        state = _wait_for_job(
            client, headers, queued["id"], {"completed", "failed", "cancelled"}
        ).json()
        assert state["status"] == "completed"
        return queued["id"]

    first_job = run_latest_plan()
    context = next(iter(client.app.state.projects.values()))
    first_bundle = context.bundle
    second_job = run_latest_plan()
    assert second_job != first_job
    assert context.bundle is not first_bundle

    exported_bundles = []
    def capture_report(_project, _brief, _plan, bundle, _figures, _language, destination):
        exported_bundles.append(bundle)
        Path(destination).write_bytes(b"docx fixture")

    monkeypatch.setattr("biostat_service.app.build_results_docx", capture_report)
    response = client.post(
        "/v1/reports", headers=headers,
        json={"project_id": project_id, "job_id": first_job, "language": "en", "destination": str(tmp_path / "first.docx")},
    )
    assert response.status_code == 200
    assert len(exported_bundles) == 1
    assert exported_bundles[0] is first_bundle


def test_same_completed_job_builds_language_specific_figures_for_en_and_tr_exports(
    client, tmp_path: Path, monkeypatch
):
    workbook_path = tmp_path / "bilingual.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["control" if index < 6 else "treated", index + 1])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {"title": "Bilingual", "question": "Is the outcome different between groups?", "hypothesis": "Groups differ.", "design": "cohort", "outcome_variables": ["outcome"], "exposure_variables": ["group"]}
    created = client.post("/v1/projects", headers=headers, json={"source_path": str(workbook_path), "project_root": str(tmp_path / "bilingual.biostat"), "brief": brief}).json()
    project_id = created["id"]
    client.post(f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": _approved_roles(created)})
    plan = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
    client.post("/v1/plans/approval", headers=headers, json={"project_id": project_id, "revision": plan["revision"], "digest": plan["digest"]})
    job = client.post("/v1/jobs", headers=headers, json={"project_id": project_id, "approved_plan_revision": plan["revision"], "approved_plan_digest": plan["digest"]}).json()
    client.app.state.job_manager.wait(UUID(job["id"]), timeout=5)

    built_languages = []
    exported = []
    def language_figures(_frame, _plan, _bundle, output_dir, language):
        built_languages.append(language)
        Path(output_dir).mkdir(parents=True)
        png = Path(output_dir) / f"figure-{language}.png"
        png.write_bytes(b"png")
        return [SimpleNamespace(id="figure", png_path=png, svg_path=None, caption=f"caption-{language}", alt_text=f"axis-{language}", dpi=300, width_inches=6.5, height_inches=4.2)]
    def capture_report(_project, _brief, _plan, bundle, figures, language, destination):
        exported.append((bundle.model_dump(mode="json"), figures[0].caption, figures[0].alt_text, language))
        Path(destination).write_bytes(language.encode())
    monkeypatch.setattr("biostat_service.app.build_figures", language_figures)
    monkeypatch.setattr("biostat_service.app.build_results_docx", capture_report)

    for language in ("en", "tr"):
        response = client.post("/v1/reports", headers=headers, json={"project_id": project_id, "job_id": job["id"], "language": language, "destination": str(tmp_path / f"result-{language}.docx")})
        assert response.status_code == 200

    assert built_languages == ["en", "tr"]
    assert exported[0][0] == exported[1][0]
    assert exported[0][1:] == ("caption-en", "axis-en", "en")
    assert exported[1][1:] == ("caption-tr", "axis-tr", "tr")


def test_failed_analysis_persists_only_safe_diagnostics_and_terminal_audit(
    client, tmp_path: Path, monkeypatch
) -> None:
    workbook_path = tmp_path / "failure.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    workbook.active.append(["control", 1])
    workbook.active.append(["treated", 2])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {"title": "Failure", "question": "Do groups differ?", "hypothesis": "Groups differ.", "design": "cohort", "outcome_variables": ["outcome"], "exposure_variables": ["group"]}
    root = tmp_path / "failure.biostat"
    created = client.post("/v1/projects", headers=headers, json={"source_path": str(workbook_path), "project_root": str(root), "brief": brief}).json()
    project_id = created["id"]
    client.post(f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": _approved_roles(created)})
    plan = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
    client.post("/v1/plans/approval", headers=headers, json={"project_id": project_id, "revision": plan["revision"], "digest": plan["digest"]})

    def fail_without_leaking(_frame, _plan):
        raise RuntimeError("patient-001 /private/clinic/source.xlsx")

    monkeypatch.setattr("biostat_service.app.run_plan", fail_without_leaking)
    queued = client.post("/v1/jobs", headers=headers, json={"project_id": project_id, "approved_plan_revision": plan["revision"], "approved_plan_digest": plan["digest"]}).json()
    final = client.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)

    assert final.status == "failed"
    assert final.result is None
    assert final.diagnostics == ({"category": "library", "code": "library_failure"},)
    assert "patient-001" not in repr(final)
    manifest_text = (root / "project.json").read_text(encoding="utf-8")
    audit_text = (root / "audit.jsonl").read_text(encoding="utf-8")
    audit_events = [json.loads(line) for line in audit_text.splitlines()]
    assert audit_events[-1]["type"] == "analysis_failed"
    assert audit_events[-1]["status"] == "failed"
    assert "patient-001" not in manifest_text + audit_text
    assert "/private/clinic" not in manifest_text + audit_text
    report = client.post("/v1/reports", headers=headers, json={"project_id": project_id, "job_id": queued["id"], "language": "en", "destination": str(tmp_path / "must-not-exist.docx")})
    assert report.status_code == 409
    assert not (tmp_path / "must-not-exist.docx").exists()


def test_cancelled_pipeline_cleans_staging_and_never_becomes_reportable(client, tmp_path: Path, monkeypatch):
    workbook_path = tmp_path / "cancel.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["control" if index < 6 else "treated", index + 1])
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Cancellation",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    root = tmp_path / "cancel.biostat"
    created = client.post(
        "/v1/projects", headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(root), "brief": brief},
    ).json()
    project_id = created["id"]
    client.post(f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": _approved_roles(created)})
    plan = client.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
    client.post(
        "/v1/plans/approval", headers=headers,
        json={"project_id": project_id, "revision": plan["revision"], "digest": plan["digest"]},
    )

    figures_started = Event()
    release_figures = Event()
    def blocking_figures(_frame, _plan, _bundle, output_dir, _language):
        Path(output_dir).mkdir(parents=True)
        (Path(output_dir) / "partial.png").write_bytes(b"partial")
        figures_started.set()
        release_figures.wait(timeout=2)
        return []

    monkeypatch.setattr("biostat_service.app.build_figures", blocking_figures)
    queued = client.post(
        "/v1/jobs", headers=headers,
        json={"project_id": project_id, "approved_plan_revision": plan["revision"], "approved_plan_digest": plan["digest"]},
    ).json()
    assert figures_started.wait(timeout=2)
    cancelled = client.post(f"/v1/jobs/{queued['id']}/cancel", headers=headers, json={})
    assert cancelled.json()["status"] == "cancelling"
    release_figures.set()
    state = _wait_for_job(client, headers, queued["id"], {"cancelled"}).json()

    assert state["status"] == "cancelled"
    assert state["result"] is None
    assert '"type": "analysis_completed"' not in (root / "audit.jsonl").read_text(encoding="utf-8")
    assert '"type": "analysis_cancelled"' in (root / "audit.jsonl").read_text(encoding="utf-8")
    assert not list((root / "artifacts").glob(".staging-*"))
    assert next(iter(client.app.state.projects.values())).job_outputs == {}
    report = client.post(
        "/v1/reports", headers=headers,
        json={"project_id": project_id, "job_id": queued["id"], "language": "en", "destination": str(tmp_path / "cancelled.docx")},
    )
    assert report.status_code == 409
    assert not (tmp_path / "cancelled.docx").exists()


def test_authenticated_project_plan_job_and_report_routes_keep_values_out_of_responses(
    client, tmp_path: Path
):
    """The entire local workflow publishes metadata/results, never raw workbook values."""
    workbook_path = tmp_path / "study.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["group", "outcome"])
    for index in range(12):
        sheet.append(["control" if index < 6 else "treated", 100 + index])
    workbook.save(workbook_path)
    brief = {
        "title": "Treatment comparison",
        "question": "Does treatment change the measured outcome?",
        "hypothesis": "Treatment is associated with a different outcome.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
        "language": "en",
    }
    headers = {"Authorization": "Bearer test-token"}

    created = client.post(
        "/v1/projects",
        headers=headers,
        json={"source_path": str(workbook_path), "project_root": str(tmp_path / "study.biostat"), "brief": brief},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["profile"]["rows"] == 12
    assert "control" not in created.text
    assert str(workbook_path) not in created.text

    approved_data = client.post(
        f"/v1/projects/{payload['id']}/data-approval", headers=headers, json={"roles": _approved_roles(payload)}
    )
    assert approved_data.status_code == 200

    planned = client.post("/v1/plans", headers=headers, json={"project_id": payload["id"]})
    assert planned.status_code == 200
    assert planned.json()["blocking_errors"] == []
    approved_plan = client.post(
        "/v1/plans/approval",
        headers=headers,
        json={
            "project_id": payload["id"],
            "revision": planned.json()["revision"],
            "digest": planned.json()["digest"],
        },
    )
    assert approved_plan.status_code == 200

    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "project_id": payload["id"],
            "approved_plan_revision": planned.json()["revision"],
            "approved_plan_digest": planned.json()["digest"],
        },
    )
    assert queued.status_code == 200
    job_id = queued.json()["id"]
    status = _wait_for_job(client, headers, job_id, {"completed", "failed", "cancelled"})
    assert status.json()["status"] == "completed"
    assert status.json()["result"]["results"]
    assert "control" not in status.text

    audit_text = (tmp_path / "study.biostat" / "audit.jsonl").read_text(encoding="utf-8")
    assert '"type": "analysis_completed"' in audit_text
    assert '"data_fingerprint"' in audit_text
    assert "control" not in audit_text

    destination = tmp_path / "results.docx"
    exported = client.post(
        "/v1/reports",
        headers=headers,
        json={"project_id": payload["id"], "job_id": job_id, "language": "en", "destination": str(destination)},
    )
    assert exported.status_code == 200
    assert exported.json() == {"saved": True, "filename": "results.docx"}
    assert destination.exists()


def test_restart_open_reconstructs_completed_job_without_patient_rows_in_manifest(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    workbook_path = tmp_path / "restart.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["private-control" if index < 6 else "private-treated", index + 1])
    workbook.save(workbook_path)
    root = tmp_path / "restart.biostat"
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Restart-safe study",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }

    with TestClient(create_app()) as first:
        created = first.post(
            "/v1/projects", headers=headers,
            json={"source_path": str(workbook_path), "project_root": str(root), "brief": brief},
        ).json()
        project_id = created["id"]
        roles = [
            {"name": "group", "role": "exposure", "kind": created["profile"]["variables"]["group"]["kind"], "confirmed": True},
            {"name": "outcome", "role": "outcome", "kind": created["profile"]["variables"]["outcome"]["kind"], "confirmed": True},
        ]
        assert first.post(
            f"/v1/projects/{project_id}/data-approval", headers=headers, json={"roles": roles}
        ).status_code == 200
        plan = first.post("/v1/plans", headers=headers, json={"project_id": project_id}).json()
        approved_plan = first.post(
            "/v1/plans/approval", headers=headers,
            json={"project_id": project_id, "revision": plan["revision"], "digest": plan["digest"]},
        )
        assert approved_plan.status_code == 200, approved_plan.text
        queued = first.post(
            "/v1/jobs", headers=headers,
            json={"project_id": project_id, "approved_plan_revision": plan["revision"], "approved_plan_digest": plan["digest"]},
        )
        assert queued.status_code == 200, queued.text
        queued = queued.json()
        first.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)

    manifest_text = (root / "project.json").read_text(encoding="utf-8")
    assert str(workbook_path.resolve()) not in manifest_text
    assert "private-control" not in manifest_text
    assert "private-treated" not in manifest_text

    exported = []
    def capture_report(_project, _brief, _plan, bundle, figures, language, destination):
        exported.append((bundle, figures, language))
        Path(destination).write_bytes(b"reopened report")

    monkeypatch.setattr("biostat_service.app.build_results_docx", capture_report)
    with TestClient(create_app()) as restarted:
        opened = restarted.post(
            "/v1/projects/open", headers=headers, json={"project_root": str(root)}
        )
        assert opened.status_code == 200
        payload = opened.json()
        assert payload["id"] == project_id
        assert payload["approved_plan"] is True
        assert payload["completed_job_id"] == queued["id"]
        assert payload["results"]

        destination = tmp_path / "reopened.docx"
        report = restarted.post(
            "/v1/reports", headers=headers,
            json={"project_id": project_id, "job_id": queued["id"], "language": "en", "destination": str(destination)},
        )
        assert report.status_code == 200
        assert destination.read_bytes() == b"reopened report"
        assert exported[0][2] == "en"


def test_new_project_executes_from_immutable_snapshot_after_original_is_removed(
    client, tmp_path: Path
) -> None:
    workbook_path = tmp_path / "external.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["control" if index < 6 else "treated", index + 1])
    workbook.save(workbook_path)
    root = tmp_path / "snapshot.biostat"
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Immutable snapshot",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }

    created = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "source_path": str(workbook_path),
            "project_root": str(root),
            "brief": brief,
        },
    ).json()
    project_id = created["id"]
    workbook_path.unlink()

    assert client.post(
        f"/v1/projects/{project_id}/data-approval",
        headers=headers,
        json={"roles": _approved_roles(created)},
    ).status_code == 200
    plan = client.post(
        "/v1/plans", headers=headers, json={"project_id": project_id}
    ).json()
    assert client.post(
        "/v1/plans/approval",
        headers=headers,
        json={
            "project_id": project_id,
            "revision": plan["revision"],
            "digest": plan["digest"],
        },
    ).status_code == 200
    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "project_id": project_id,
            "approved_plan_revision": plan["revision"],
            "approved_plan_digest": plan["digest"],
        },
    ).json()
    terminal = client.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)

    assert terminal.status == "completed"
    context = client.app.state.projects[UUID(project_id)]
    assert context.profile.source_path == root / "source" / "source.xlsx"


@pytest.mark.parametrize(
    "tamper_case", ["plan_content", "job_digest", "bundle_provenance"]
)
def test_project_open_rejects_tampered_persisted_analysis_state(
    client, tmp_path: Path, tamper_case: str
) -> None:
    workbook_path = tmp_path / f"{tamper_case}.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        workbook.active.append(["control" if index < 6 else "treated", index + 1])
    workbook.save(workbook_path)
    root = tmp_path / f"{tamper_case}.biostat"
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Tamper boundary",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    created = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "source_path": str(workbook_path),
            "project_root": str(root),
            "brief": brief,
        },
    ).json()
    project_id = created["id"]
    assert client.post(
        f"/v1/projects/{project_id}/data-approval",
        headers=headers,
        json={"roles": _approved_roles(created)},
    ).status_code == 200
    plan = client.post(
        "/v1/plans", headers=headers, json={"project_id": project_id}
    ).json()
    assert client.post(
        "/v1/plans/approval",
        headers=headers,
        json={
            "project_id": project_id,
            "revision": plan["revision"],
            "digest": plan["digest"],
        },
    ).status_code == 200
    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "project_id": project_id,
            "approved_plan_revision": plan["revision"],
            "approved_plan_digest": plan["digest"],
        },
    ).json()
    terminal = client.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)
    assert terminal.status == "completed"

    manifest_path = root / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_job = manifest["state"]["terminal_jobs"][queued["id"]]["output"]
    if tamper_case == "plan_content":
        manifest["state"]["plan"]["content"]["version"] = 999
    elif tamper_case == "job_digest":
        stored_job["digest"] = "0" * 64
    else:
        stored_job["bundle"]["provenance"]["data_fingerprint"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with TestClient(create_app()) as restarted:
        opened = restarted.post(
            "/v1/projects/open",
            headers=headers,
            json={"project_root": str(root)},
        )

    assert opened.status_code == 422
    assert opened.json() == {"detail": "project_open_failed"}


def test_approved_continuous_kind_coerces_mixed_values_and_reports_missingness(
    client, tmp_path: Path
) -> None:
    workbook_path = tmp_path / "mixed-outcome.xlsx"
    workbook = Workbook()
    workbook.active.append(["group", "outcome"])
    for index in range(12):
        outcome = "not-recorded" if index == 2 else index + 1
        workbook.active.append(
            ["control" if index < 6 else "treated", outcome]
        )
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Approved coercion",
        "question": "Is the outcome different between groups?",
        "hypothesis": "The groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["outcome"],
        "exposure_variables": ["group"],
    }
    created = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "source_path": str(workbook_path),
            "project_root": str(tmp_path / "mixed-outcome.biostat"),
            "brief": brief,
        },
    ).json()
    roles = _approved_roles(created)
    next(role for role in roles if role["name"] == "outcome")["kind"] = "continuous"
    project_id = created["id"]

    assert client.post(
        f"/v1/projects/{project_id}/data-approval",
        headers=headers,
        json={"roles": roles},
    ).status_code == 200
    plan = client.post(
        "/v1/plans", headers=headers, json={"project_id": project_id}
    ).json()
    assert plan["blocking_errors"] == []
    assert "approved_kind_override:outcome:categorical:continuous" in plan["warnings"]
    assert client.post(
        "/v1/plans/approval",
        headers=headers,
        json={
            "project_id": project_id,
            "revision": plan["revision"],
            "digest": plan["digest"],
        },
    ).status_code == 200
    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "project_id": project_id,
            "approved_plan_revision": plan["revision"],
            "approved_plan_digest": plan["digest"],
        },
    ).json()
    terminal = client.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)

    assert terminal.status == "completed"
    primary = next(
        result for result in terminal.result["results"] if result["id"] == "primary_outcome"
    )
    assert primary["n"] == 11
    assert primary["diagnostics"]["counts"] == {"input": 12, "used": 11, "missing": 1}
    assert "approved_kind_override:outcome:categorical:continuous" in primary["warnings"]


def test_approved_categorical_kind_preserves_missingness_during_coercion() -> None:
    frame = pd.DataFrame({"mixed_group": [1, "A", None]})
    context = SimpleNamespace(
        approved_roles={
            "mixed_group": SimpleNamespace(role="exposure", kind="categorical")
        },
        profile=SimpleNamespace(
            variables={"mixed_group": SimpleNamespace(kind="binary")}
        ),
    )

    converted = _apply_approved_kinds(frame, context)

    assert converted["mixed_group"].dropna().tolist() == ["1", "A"]
    assert int(converted["mixed_group"].isna().sum()) == 1
    assert str(converted["mixed_group"].dtype) == "string"


def test_analysis_executes_with_collision_safe_numeric_header_identifiers(
    client, tmp_path: Path
) -> None:
    workbook_path = tmp_path / "header-collision.xlsx"
    workbook = Workbook()
    workbook.active.append([2026, "int:2026"])
    for index in range(12):
        workbook.active.append(
            [index + 1, "control" if index < 6 else "treated"]
        )
    workbook.save(workbook_path)
    headers = {"Authorization": "Bearer test-token"}
    brief = {
        "title": "Header identity",
        "question": "Is the numeric-header outcome different between groups?",
        "hypothesis": "The confirmed groups have different outcomes.",
        "design": "cohort",
        "outcome_variables": ["int:2026"],
        "exposure_variables": ["str:int:2026"],
    }
    created = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "source_path": str(workbook_path),
            "project_root": str(tmp_path / "header-collision.biostat"),
            "brief": brief,
        },
    ).json()
    assert set(created["profile"]["variables"]) == {"int:2026", "str:int:2026"}
    project_id = created["id"]
    roles = [
        {
            "name": "int:2026",
            "role": "outcome",
            "kind": "continuous",
            "confirmed": True,
        },
        {
            "name": "str:int:2026",
            "role": "exposure",
            "kind": "binary",
            "confirmed": True,
        },
    ]
    assert client.post(
        f"/v1/projects/{project_id}/data-approval",
        headers=headers,
        json={"roles": roles},
    ).status_code == 200
    plan = client.post(
        "/v1/plans", headers=headers, json={"project_id": project_id}
    ).json()
    assert plan["blocking_errors"] == []
    assert client.post(
        "/v1/plans/approval",
        headers=headers,
        json={
            "project_id": project_id,
            "revision": plan["revision"],
            "digest": plan["digest"],
        },
    ).status_code == 200
    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "project_id": project_id,
            "approved_plan_revision": plan["revision"],
            "approved_plan_digest": plan["digest"],
        },
    ).json()
    terminal = client.app.state.job_manager.wait(UUID(queued["id"]), timeout=5)

    assert terminal.status == "completed"
    primary = next(
        result for result in terminal.result["results"] if result["id"] == "primary_outcome"
    )
    assert primary["n"] == 12


def test_v1_rejects_non_loopback_client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app(), client=("192.0.2.1", 5000)) as remote_client:
        response = remote_client.get(
            "/v1/session", headers={"Authorization": "Bearer test-token"}
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "loopback_only"}


def test_launcher_emits_only_port_and_api_readiness():
    process = subprocess.Popen(
        [sys.executable, "-m", "biostat_service.app", "--port", "0"],
        env={**os.environ, "BIOSTAT_SESSION_TOKEN": "test-token"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=10):
            process.kill()
            process.wait(timeout=5)
            stderr = process.stderr.read() if process.stderr is not None else ""
            if "operation not permitted" in stderr.lower():
                pytest.skip("host sandbox does not permit a loopback listener")
            pytest.fail("launcher did not emit readiness within 10 seconds")
        line = process.stdout.readline()
        if not line:
            process.wait(timeout=5)
            stderr = process.stderr.read() if process.stderr is not None else ""
            if "operation not permitted" in stderr.lower():
                pytest.skip("host sandbox does not permit a loopback listener")
            pytest.fail("launcher exited before readiness")
        readiness = json.loads(line)
        assert readiness.keys() == {"port", "api"}
        assert isinstance(readiness["port"], int)
        assert readiness["port"] > 0
        assert readiness["api"] == 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
