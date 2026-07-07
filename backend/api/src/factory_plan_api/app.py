from __future__ import annotations

from typing import TYPE_CHECKING

from factory_plan_optimizer.optimizer.global_recipe_lp import solve_global_recipe_lp
from fastapi import FastAPI, HTTPException

from factory_plan_api.default_data import load_default_factory_data
from factory_plan_api.dtos import (
    ProblemDto,
    SolveJobDto,
    SolveQueuedDto,
    SolveRequestDto,
    SolveResultDto,
)
from factory_plan_api.jobs import SolveJobStore, SolveJobStoreFullError
from factory_plan_api.problem import (
    package_with_edits,
    problem_from_package,
    result_to_dto,
)

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.models import FactoryDataPackage

app = FastAPI(title="Factory Plan API")
job_store = SolveJobStore(max_workers=2)


@app.get("/api/problem/default", response_model=ProblemDto)
async def get_default_problem() -> ProblemDto:
    return problem_from_package(load_default_factory_data())


@app.post("/api/solve", response_model=SolveQueuedDto)
async def post_solve(request: SolveRequestDto) -> SolveQueuedDto:
    package = _package_from_request(request)

    def solve() -> SolveResultDto:
        return result_to_dto(solve_global_recipe_lp(package))

    try:
        return job_store.submit(solve)
    except SolveJobStoreFullError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


@app.get("/api/solve/{job_id}", response_model=SolveJobDto)
async def get_solve(job_id: str) -> SolveJobDto:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown solve job")
    return job


def _package_from_request(request: SolveRequestDto) -> FactoryDataPackage:
    try:
        base_package = load_default_factory_data()
        return package_with_edits(
            base_package,
            request.demands,
            request.external_inputs,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
