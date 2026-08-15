"""Cancellable, value-free background analysis job behavior."""

from __future__ import annotations

from threading import Event
from time import sleep

from biostat_service.jobs import JobManager


def test_cancelled_job_never_becomes_completed() -> None:
    """A cancellation wins even when the worker finishes after it was requested."""
    manager = JobManager(max_workers=1)
    started = Event()
    release = Event()

    def slow_test_job(is_cancelled):
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

    def failing_job(_is_cancelled):
        raise ValueError("patient-001 must never leave the worker")

    job = manager.submit(failing_job)
    final = manager.wait(job.id, timeout=1)

    assert final.status == "failed"
    assert final.error_code == "analysis_failed"
    assert "patient-001" not in (final.message or "")
    manager.shutdown()
