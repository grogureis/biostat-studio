"""Cancellable, value-free background analysis job behavior."""

from __future__ import annotations

from threading import Event, Thread
from time import sleep

import pytest
import pandas as pd

from biostat_service.jobs import JobManager, StagedJobResult
from biostat_service.analyses import AnalysisExecutionError, run_plan
from biostat_service.contracts import AnalysisPlan, PlanItem


def test_cancelled_job_never_becomes_completed() -> None:
    """A cancellation wins even when the worker finishes after it was requested."""
    manager = JobManager(max_workers=1)
    started = Event()
    release = Event()

    def slow_test_job(is_cancelled, _update_progress):
        started.set()
        while not release.wait(0.01):
            if is_cancelled():
                return {"partial": "must_not_be_published"}
        return {"completed": True}

    job = manager.submit(slow_test_job)
    assert started.wait(timeout=1)
    assert manager.cancel(job.id).status == "cancelling"
    release.set()

    final = manager.wait(job.id, timeout=1)
    assert final.status == "cancelled"
    assert final.result is None
    assert final.error_code is None
    manager.shutdown()


def test_job_failure_exposes_a_safe_code_not_exception_text() -> None:
    manager = JobManager(max_workers=1)

    def failing_job(_is_cancelled, _update_progress):
        raise ValueError("patient-001 must never leave the worker")

    job = manager.submit(failing_job)
    final = manager.wait(job.id, timeout=1)

    assert final.status == "failed"
    assert final.error_code == "analysis_failed"
    assert "patient-001" not in (final.message or "")
    manager.shutdown()


def test_job_failure_message_is_safe_and_localized_for_turkish() -> None:
    manager = JobManager(max_workers=1)

    def failing_job(_is_cancelled, _update_progress):
        raise ValueError("/private/patient-001.xlsx")

    final = manager.wait(manager.submit(failing_job, language="tr").id, timeout=1)
    assert final.error_code == "analysis_failed"
    assert final.message == "Analiz tamamlanamadı."
    assert "patient-001" not in final.message
    manager.shutdown()


def test_analysis_execution_failure_exposes_only_allowlisted_diagnostic_categories() -> None:
    manager = JobManager(max_workers=1)

    def failing_job(_is_cancelled, _update_progress):
        raise AnalysisExecutionError(
            "/private/patient-001.xlsx",
            warnings=[{"code": "perfect_separation", "message": "patient-001"}],
        )

    final = manager.wait(manager.submit(failing_job).id, timeout=1)

    assert final.status == "failed"
    assert final.error_code == "analysis_execution_error"
    assert final.diagnostics == ({"category": "separation", "code": "perfect_separation"},)
    assert "patient-001" not in repr(final)
    manager.shutdown()


@pytest.mark.parametrize(
    ("producer_code", "expected_category"),
    [
        ("model_fit_failure", "separation"),
        ("model_convergence_failure", "convergence"),
        ("library_warning", "library"),
    ],
)
def test_real_analysis_warning_codes_map_to_safe_diagnostic_categories(
    producer_code: str, expected_category: str
) -> None:
    manager = JobManager(max_workers=1)

    def failing_job(_is_cancelled, _update_progress):
        raise AnalysisExecutionError(
            "private model detail",
            warnings=[
                {
                    "code": producer_code,
                    "method": "logistic_regression",
                    "category": "private-library-detail",
                }
            ],
        )

    final = manager.wait(manager.submit(failing_job).id, timeout=1)

    assert final.error_code == "analysis_execution_error"
    assert final.diagnostics == (
        {"category": expected_category, "code": producer_code},
    )
    assert "private" not in repr(final)
    manager.shutdown()


def test_real_logistic_failure_reaches_job_boundary_with_actionable_safe_codes() -> None:
    frame = pd.DataFrame(
        {
            "event": [0, 0, 0, 0, 1, 1, 1, 1],
            "x": [-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0],
        }
    )
    plan = AnalysisPlan(
        items=[
            PlanItem(
                id="primary_outcome",
                estimand="Odds ratio for the confirmed predictor.",
                method="logistic_regression",
                rationale="The confirmed binary outcome requires logistic regression.",
                required_variables=["event", "x"],
            )
        ]
    )
    manager = JobManager(max_workers=1)

    def failing_job(_is_cancelled, _update_progress):
        return {"bundle": run_plan(frame, plan)}

    final = manager.wait(manager.submit(failing_job).id, timeout=2)

    assert final.status == "failed"
    assert final.error_code == "analysis_execution_error"
    assert {tuple(sorted(item.items())) for item in final.diagnostics} == {
        (("category", "convergence"), ("code", "model_convergence_failure")),
        (("category", "library"), ("code", "library_warning")),
    }
    assert "PerfectSeparationWarning" not in repr(final)
    manager.shutdown()


def test_job_operation_publishes_real_monotonic_stage_progress() -> None:
    manager = JobManager(max_workers=1)
    stage_reached = Event()
    release = Event()

    def staged_job(_is_cancelled, update_progress):
        update_progress(35, "analysis_running")
        stage_reached.set()
        release.wait(timeout=1)
        return {"completed": True}

    job = manager.submit(staged_job)
    assert stage_reached.wait(timeout=1)
    running = manager.get(job.id)
    assert running.status == "running"
    assert running.progress == 35
    assert running.message == "Running approved methods."
    release.set()
    assert manager.wait(job.id, timeout=1).progress == 100
    manager.shutdown()


def test_late_cancellation_cleans_staging_without_publishing_side_effects() -> None:
    manager = JobManager(max_workers=1)
    prepared = Event()
    release = Event()
    published: list[str] = []
    cleaned: list[str] = []

    def staged_job(_is_cancelled, _update_progress):
        prepared.set()
        release.wait(timeout=1)
        return StagedJobResult(
            result={"completed": True},
            publish=lambda: published.append("audit-and-artifacts"),
            cleanup=lambda: cleaned.append("staging"),
        )

    job = manager.submit(staged_job)
    assert prepared.wait(timeout=1)
    assert manager.cancel(job.id).status == "cancelling"
    release.set()
    final = manager.wait(job.id, timeout=1)

    assert final.status == "cancelled"
    assert final.result is None
    assert published == []
    assert cleaned == ["staging"]
    manager.shutdown()


def test_terminal_state_is_not_public_until_terminal_callback_finishes() -> None:
    """A public terminal state means its durable callback side effects are done."""
    manager = JobManager(max_workers=1)
    callback_started = Event()
    release_callback = Event()
    read_finished = Event()
    observed = []

    def record_terminal(_state):
        callback_started.set()
        release_callback.wait(timeout=1)

    job = manager.submit(
        lambda _is_cancelled, _update_progress: {"completed": True},
        on_terminal=record_terminal,
    )
    assert callback_started.wait(timeout=1)

    def read_public_state() -> None:
        observed.append(manager.get(job.id))
        read_finished.set()

    reader = Thread(target=read_public_state)
    reader.start()
    assert not read_finished.wait(timeout=0.05)
    release_callback.set()
    assert read_finished.wait(timeout=1)
    reader.join(timeout=1)

    assert observed[0].status == "completed"
    manager.shutdown()
