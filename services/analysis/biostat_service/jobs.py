"""Bounded, cooperative local jobs for analysis execution."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Event, Lock
from typing import Any, Callable, Literal, Union
from uuid import UUID, uuid4


JobLanguage = Literal["en", "tr"]
ProgressUpdate = Callable[[int, str], None]

JOB_MESSAGES = {
    "en": {
        "queued": "Analysis queued.",
        "reading_data": "Reading the approved dataset.",
        "analysis_running": "Running approved methods.",
        "figures_building": "Building publication figures.",
        "publishing": "Publishing verified results.",
        "failed": "Analysis could not be completed.",
    },
    "tr": {
        "queued": "Analiz kuyruğa alındı.",
        "reading_data": "Onaylanmış veri kümesi okunuyor.",
        "analysis_running": "Onaylanmış yöntemler çalıştırılıyor.",
        "figures_building": "Yayın şekilleri hazırlanıyor.",
        "publishing": "Doğrulanmış sonuçlar yayımlanıyor.",
        "failed": "Analiz tamamlanamadı.",
    },
}


@dataclass(frozen=True)
class JobState:
    """Public job state; result payloads are published only on completion."""

    id: UUID
    status: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None
    progress: int = 0


@dataclass(frozen=True)
class StagedJobResult:
    """Prepared output whose durable side effects are committed only if cancellation loses."""

    result: dict[str, Any]
    publish: Callable[[], None]
    cleanup: Callable[[], None]


JobOperation = Callable[
    [Callable[[], bool], ProgressUpdate], Union[dict[str, Any], StagedJobResult]
]


class JobManager:
    """Run local jobs with cancellation that always wins over late completion."""

    def __init__(self, *, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="biostat")
        self._jobs: dict[UUID, JobState] = {}
        self._cancelled: dict[UUID, Event] = {}
        self._futures: dict[UUID, Future[None]] = {}
        self._languages: dict[UUID, JobLanguage] = {}
        self._lock = Lock()

    def submit(
        self,
        operation: JobOperation,
        *,
        language: JobLanguage = "en",
        job_id: UUID | None = None,
    ) -> JobState:
        job_id = job_id or uuid4()
        state = JobState(id=job_id, status="queued", message=JOB_MESSAGES[language]["queued"])
        cancel_event = Event()
        with self._lock:
            if job_id in self._jobs:
                raise ValueError("duplicate_job_id")
            self._jobs[job_id] = state
            self._cancelled[job_id] = cancel_event
            self._languages[job_id] = language
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
            def update_progress(progress: int, stage: str) -> None:
                if stage not in JOB_MESSAGES[self._languages[job_id]]:
                    raise ValueError("invalid_job_stage")
                with self._lock:
                    state = self._jobs[job_id]
                    if state.status != "running" or progress <= state.progress or progress >= 100:
                        raise ValueError("invalid_job_progress")
                    self._jobs[job_id] = replace(
                        state,
                        progress=progress,
                        message=JOB_MESSAGES[self._languages[job_id]][stage],
                    )

            prepared = operation(cancelled.is_set, update_progress)
        except Exception:
            with self._lock:
                state = self._jobs[job_id]
                self._jobs[job_id] = replace(
                    state,
                    status="cancelled" if cancelled.is_set() else "failed",
                    error_code=None if cancelled.is_set() else "analysis_failed",
                    message=(
                        None
                        if cancelled.is_set()
                        else JOB_MESSAGES[self._languages[job_id]]["failed"]
                    ),
                    progress=100,
                )
            return
        staged = prepared if isinstance(prepared, StagedJobResult) else StagedJobResult(
            result=prepared, publish=lambda: None, cleanup=lambda: None
        )
        try:
            with self._lock:
                state = self._jobs[job_id]
                if cancelled.is_set():
                    self._jobs[job_id] = replace(
                        state, status="cancelled", result=None, message=None, progress=100
                    )
                else:
                    try:
                        staged.publish()
                    except Exception:
                        self._jobs[job_id] = replace(
                            state,
                            status="failed",
                            result=None,
                            error_code="analysis_failed",
                            message=JOB_MESSAGES[self._languages[job_id]]["failed"],
                            progress=100,
                        )
                    else:
                        self._jobs[job_id] = replace(
                            state, status="completed", result=staged.result, progress=100
                        )
        finally:
            try:
                staged.cleanup()
            except OSError:
                pass

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
