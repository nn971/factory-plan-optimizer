from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Literal

from factory_plan_api.config import DEFAULT_API_LIMITS
from factory_plan_api.dtos import ErrorDto, SolveJobDto, SolveQueuedDto, SolveResultDto

if TYPE_CHECKING:
    from collections.abc import Callable

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(slots=True)
class _JobRecord:
    job_id: str
    status: JobStatus
    result: SolveResultDto | None = None
    error: ErrorDto | None = None


class SolveJobStore:
    def __init__(
        self,
        max_workers: int = DEFAULT_API_LIMITS.max_solve_workers,
        max_active_jobs: int = DEFAULT_API_LIMITS.max_active_jobs,
        max_retained_jobs: int = DEFAULT_API_LIMITS.max_retained_jobs,
    ) -> None:
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, _JobRecord] = {}
        self._job_order: list[str] = []
        self._max_active_jobs = max_active_jobs
        self._max_retained_jobs = max_retained_jobs

    def submit(self, solve: Callable[[], SolveResultDto]) -> SolveQueuedDto:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._prune_completed_locked()
            if self._active_count_locked() >= self._max_active_jobs:
                raise SolveJobStoreFullError("too many queued or running solve jobs")
            self._jobs[job_id] = _JobRecord(job_id=job_id, status="queued")
            self._job_order.append(job_id)
        self._executor.submit(self._run, job_id, solve)
        return SolveQueuedDto(job_id=job_id, status="queued")

    def get(self, job_id: str) -> SolveJobDto | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return SolveJobDto(
                job_id=record.job_id,
                status=record.status,
                result=record.result,
                error=record.error,
            )

    def _run(self, job_id: str, solve: Callable[[], SolveResultDto]) -> None:
        with self._lock:
            self._jobs[job_id].status = "running"
        try:
            result = solve()
        except Exception as error:  # noqa: BLE001
            serialized = ErrorDto(
                type=type(error).__name__,
                message=str(error),
                details=traceback.format_exc(),
            )
            with self._lock:
                record = self._jobs[job_id]
                record.status = "failed"
                record.error = serialized
                self._prune_completed_locked()
            return
        with self._lock:
            record = self._jobs[job_id]
            record.status = "succeeded"
            record.result = result
            self._prune_completed_locked()

    def _active_count_locked(self) -> int:
        return sum(
            1
            for record in self._jobs.values()
            if record.status in {"queued", "running"}
        )

    def _prune_completed_locked(self) -> None:
        completed_count = sum(
            1
            for record in self._jobs.values()
            if record.status in {"succeeded", "failed"}
        )
        while (
            len(self._jobs) > self._max_retained_jobs
            or completed_count > self._max_retained_jobs
        ):
            if not self._job_order:
                return
            oldest_job_id = self._job_order.pop(0)
            record = self._jobs.get(oldest_job_id)
            if record is None:
                continue
            if record.status in {"queued", "running"}:
                self._job_order.append(oldest_job_id)
                return
            del self._jobs[oldest_job_id]
            completed_count -= 1


class SolveJobStoreFullError(RuntimeError):
    pass
