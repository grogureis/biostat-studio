"""Bounded, cooperative local jobs for analysis execution."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Event, Lock
from typing import Any, Callable
from uuid import UUID, uuid4


JobOperation = Callable[[Callable[[], bool]], dict[str, Any]]


@dataclass(frozen=True)
class JobState:
    """Public job state; result payloads are published only on completion."""

    id: UUID
    status: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None
    progress: int = 0


class JobManager:
    """Run local jobs with cancellation that always wins over late completion."""

    def __init__(self, *, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="biostat")
        self._jobs: dict[UUID, JobState] = {}
        self._cancelled: dict[UUID, Event] = {}
        self._futures: dict[UUID, Future[None]] = {}
        self._lock = Lock()

    def submit(self, operation: JobOperation) -> JobState:
        job_id = uuid4()
        state = JobState(id=job_id, status="queued")
        cancel_event = Event()
        with self._lock:
            self._jobs[job_id] = state
            self._cancelled[job_id] = cancel_event
            self._futures[job_id] = self._executor.submit(self._run, job_id, operation)
        return state

    def _run(self, job_id: UUID, operation: JobOperation) -> None:
        with self._lock:
            cancelled = self._cancelled[job_id]
            if cancelled.is_set():
                self._jobs[job_id] = replace(self._jobs[job_id], status="cancelled", progress=100)
                return
            self._jobs[job_id] = replace(self._jobs[job_id], status="running", progress=10)
        try:
            result = operation(cancelled.is_set)
        except Exception:
            with self._lock:
                state = self._jobs[job_id]
                self._jobs[job_id] = replace(
                    state,
                    status="cancelled" if cancelled.is_set() else "failed",
                    error_code=None if cancelled.is_set() else "analysis_failed",
                    message=None if cancelled.is_set() else "Analysis could not be completed.",
                    progress=100,
                )
            return
        with self._lock:
            state = self._jobs[job_id]
            self._jobs[job_id] = replace(
                state,
                status="cancelled" if cancelled.is_set() else "completed",
                result=None if cancelled.is_set() else result,
                progress=100,
            )

    def get(self, job_id: UUID) -> JobState:
        with self._lock:
            return self._jobs[job_id]

    def cancel(self, job_id: UUID) -> JobState:
        with self._lock:
            state = self._jobs[job_id]
            if state.status in {"completed", "failed", "cancelled"}:
                return state
            self._cancelled[job_id].set()
            next_state = replace(state, status="cancelling", result=None)
            self._jobs[job_id] = next_state
            return next_state

    def wait(self, job_id: UUID, *, timeout: float | None = None) -> JobState:
        self._futures[job_id].result(timeout=timeout)
        return self.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
