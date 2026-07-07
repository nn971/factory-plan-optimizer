from __future__ import annotations

import time

import pytest

from factory_plan_api.dtos import SolveResultDto
from factory_plan_api.jobs import SolveJobStore, SolveJobStoreFullError


def test_solve_job_store_serializes_callable_error() -> None:
    store = SolveJobStore(max_workers=1)

    def fail() -> SolveResultDto:
        message = "boom"
        raise RuntimeError(message)

    queued = store.submit(fail)

    job = None
    for _ in range(50):
        job = store.get(queued.job_id)
        assert job is not None
        if job.status == "failed":
            break
        time.sleep(0.01)

    assert job is not None
    assert job.status == "failed"
    assert job.error is not None
    assert job.error.type == "RuntimeError"
    assert job.error.message == "boom"
    assert job.error.details


def test_solve_job_store_rejects_when_active_jobs_saturated() -> None:
    store = SolveJobStore(max_workers=1, max_active_jobs=1)

    def slow() -> SolveResultDto:
        time.sleep(0.2)
        return _result()

    store.submit(slow)

    with pytest.raises(SolveJobStoreFullError, match="too many"):
        store.submit(_result)


def _result() -> SolveResultDto:
    return SolveResultDto(
        solver_status="optimal",
        objective_value=0.0,
        objective_components={},
        recipe_rates={},
        external_supplies={},
        unmet_demand={},
        surplus={},
        balance_residuals={},
    )
