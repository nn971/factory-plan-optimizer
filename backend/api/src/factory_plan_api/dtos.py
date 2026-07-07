from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ItemDto(BaseModel):
    id: str
    kind: Literal["item", "fluid", "unknown"]


class ExternalInputDto(BaseModel):
    item_id: str
    enabled: bool = False
    cost: float = Field(ge=0.0)
    capacity: float | None = Field(default=None, ge=0.0)


class ProblemDto(BaseModel):
    package_id: str | None = None
    items: list[ItemDto]
    demands: dict[str, float] = Field(default_factory=dict)
    external_inputs: list[ExternalInputDto]
    recipe_ids: list[str] = Field(default_factory=list)


class ProblemPackageDto(BaseModel):
    package_id: str
    problem: ProblemDto


class SolveRequestDto(BaseModel):
    package_id: str | None = None
    demands: dict[str, float] = Field(default_factory=dict)
    external_inputs: list[ExternalInputDto] = Field(default_factory=list)

    @field_validator("demands")
    @classmethod
    def demands_must_be_nonnegative(cls, demands: dict[str, float]) -> dict[str, float]:
        negative_ids = sorted(
            item_id for item_id, amount in demands.items() if amount < 0.0
        )
        if negative_ids:
            joined_ids = ", ".join(negative_ids)
            raise ValueError(f"demands must be nonnegative: {joined_ids}")
        return demands

    @model_validator(mode="after")
    def external_inputs_must_be_unique(self) -> SolveRequestDto:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for external_input in self.external_inputs:
            if external_input.item_id in seen:
                duplicates.add(external_input.item_id)
            seen.add(external_input.item_id)
        if duplicates:
            joined_ids = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate external_inputs entries: {joined_ids}")
        return self


class SolveQueuedDto(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]


class SolveResultDto(BaseModel):
    solver_status: str
    objective_value: float | None
    objective_components: dict[str, float]
    recipe_rates: dict[str, float]
    external_supplies: dict[str, float]
    unmet_demand: dict[str, float]
    surplus: dict[str, float]
    balance_residuals: dict[str, float]
    message: str = ""
    details: str = ""


class ErrorDto(BaseModel):
    type: str
    message: str
    details: str = ""


class SolveJobDto(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    result: SolveResultDto | None = None
    error: ErrorDto | None = None
