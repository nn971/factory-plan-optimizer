from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from factory_plan_optimizer.optimizer.global_recipe_lp import solve_global_recipe_lp
from fastapi import FastAPI, HTTPException, Request
from game_data_extractor.data_contracts import (
    FactoryDataPackageParseError,
    load_factory_data_package,
)

from factory_plan_api.default_data import load_default_factory_data
from factory_plan_api.dtos import (
    ExplorerResponseDto,
    ProblemDto,
    ProblemPackageDto,
    SolveJobDto,
    SolveQueuedDto,
    SolveRequestDto,
    SolveResultDto,
)
from factory_plan_api.explorer import explorer_from_package
from factory_plan_api.jobs import SolveJobStore, SolveJobStoreFullError
from factory_plan_api.problem import (
    DEFAULT_PACKAGE_ID,
    DEFAULT_SCENARIO_ID,
    package_with_edits,
    problem_from_package,
    result_to_dto,
)

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import FactoryDataPackage

app = FastAPI(title="Factory Plan API")
job_store = SolveJobStore(max_workers=2)
MAX_PACKAGE_UPLOAD_BYTES = 1_000_000
MAX_STORED_PACKAGES = 8
uploaded_packages: dict[str, FactoryDataPackage] = {}


@dataclass
class CurrentPackageState:
    package_id: str | None = None
    package: FactoryDataPackage | None = None


current_package_state = CurrentPackageState()


@app.get("/api/problem/default", response_model=ProblemDto)
async def get_default_problem() -> ProblemDto:
    package = load_default_factory_data()
    set_current_package(DEFAULT_PACKAGE_ID, package)
    return problem_from_package(
        package,
        package_id=DEFAULT_PACKAGE_ID,
        scenario_id=DEFAULT_SCENARIO_ID,
    )


@app.post("/api/problem/package", response_model=ProblemPackageDto)
async def post_problem_package(request: Request) -> ProblemPackageDto:
    content_length = request.headers.get("content-length")
    if (
        content_length is not None
        and _parse_content_length(content_length) > MAX_PACKAGE_UPLOAD_BYTES
    ):
        raise HTTPException(
            status_code=413,
            detail="factory data package upload too large",
        )
    body = await request.body()
    if len(body) > MAX_PACKAGE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="factory data package upload too large",
        )
    try:
        package = load_factory_data_package(body.decode("utf-8"))
    except (FactoryDataPackageParseError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if len(uploaded_packages) >= MAX_STORED_PACKAGES:
        raise HTTPException(
            status_code=429,
            detail="too many uploaded factory data packages",
        )
    package_id = str(uuid.uuid4())
    uploaded_packages[package_id] = package
    set_current_package(package_id, package)
    return ProblemPackageDto(
        package_id=package_id,
        problem=problem_from_package(package, package_id=package_id),
    )


@app.get("/api/explorer", response_model=ExplorerResponseDto)
async def get_explorer() -> ExplorerResponseDto:
    package_id, package = current_package_or_default()
    return explorer_from_package(package, package_id)


@app.post("/api/solve", response_model=SolveQueuedDto)
async def post_solve(request: SolveRequestDto) -> SolveQueuedDto:
    package = _package_from_request(request)

    def solve() -> SolveResultDto:
        return result_to_dto(
            solve_global_recipe_lp(package, solve_mode=request.solve_mode),
        )

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
        base_package = _base_package_from_request(request)
        return package_with_edits(
            base_package,
            request.demands,
            request.external_inputs,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _base_package_from_request(request: SolveRequestDto) -> FactoryDataPackage:
    if request.package_id is None or request.package_id == DEFAULT_PACKAGE_ID:
        return load_default_factory_data()
    package = uploaded_packages.get(request.package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="unknown factory data package")
    return package


def set_current_package(package_id: str, package: FactoryDataPackage) -> None:
    current_package_state.package_id = package_id
    current_package_state.package = package


def clear_current_package() -> None:
    current_package_state.package_id = None
    current_package_state.package = None


def current_package_or_default() -> tuple[str, FactoryDataPackage]:
    package_id = current_package_state.package_id
    package = current_package_state.package
    if package_id is None or package is None:
        package = load_default_factory_data()
        set_current_package(DEFAULT_PACKAGE_ID, package)
        package_id = DEFAULT_PACKAGE_ID
    return package_id, package


def _parse_content_length(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="invalid content-length header",
        ) from error
