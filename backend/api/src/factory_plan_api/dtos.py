from __future__ import annotations

from math import isfinite
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    field_validator,
    model_serializer,
    model_validator,
)


class ItemDto(BaseModel):
    id: str
    kind: Literal["item", "fluid", "unknown"]


class ExternalInputDto(BaseModel):
    item_id: str
    kind: Literal["item", "fluid", "unknown"] = "unknown"
    enabled: bool = False
    cost: float = Field(ge=0.0)
    capacity: float | None = Field(default=None, ge=0.0)
    source: (
        Literal[
            "default_input",
            "inferred_unproduced",
            "inferred_fluid",
        ]
        | None
    ) = None
    default_approved: bool = False


class MilestoneDto(BaseModel):
    item_id: str
    recipe_ids: list[str]


class ProblemDto(BaseModel):
    package_id: str | None = None
    scenario_id: str | None = None
    scenario_label: str = "Factory planning scenario"
    items: list[ItemDto]
    demands: dict[str, float] = Field(default_factory=dict)
    target_demands: list[str] = Field(default_factory=list)
    rate_units: str = "items/s"
    default_solve_mode: Literal["hard_demand", "soft_diagnostics"] = "hard_demand"
    external_inputs: list[ExternalInputDto]
    raw_input_candidates: list[ExternalInputDto] = Field(default_factory=list)
    recipe_ids: list[str] = Field(default_factory=list)
    milestones: list[MilestoneDto] = Field(default_factory=list)
    item_metadata: dict[str, dict[str, str]] = Field(default_factory=dict)
    recipe_metadata: dict[str, dict[str, str]] = Field(default_factory=dict)
    sparse_clustering_defaults: dict[str, object] = Field(default_factory=dict)


class ProblemPackageDto(BaseModel):
    package_id: str
    problem: ProblemDto


class UnlockConditionDto(BaseModel):
    type: Literal["technology", "start-unlocked", "unknown"]
    id: str | None = None


class ExplorerOverviewDto(BaseModel):
    item_count: int
    fluid_count: int
    recipe_count: int
    item_categories: list[str]
    recipe_categories: list[str]


class ExplorerRecipeLinkDto(BaseModel):
    id: str
    category: str


class ExplorerItemDto(BaseModel):
    id: str
    kind: Literal["item", "fluid", "unknown"]
    category: str
    unlock_condition: UnlockConditionDto
    produced_by: list[ExplorerRecipeLinkDto]
    consumed_by: list[ExplorerRecipeLinkDto]


class RecipeTermDto(BaseModel):
    type: Literal["item", "fluid", "unknown"]
    name: str
    amount: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    probability: float | None = None
    catalyst_amount: float | None = None
    temperature: float | None = None
    minimum_temperature: float | None = None
    maximum_temperature: float | None = None
    fluidbox_index: int | None = None


class ExplorerRecipeIODto(BaseModel):
    item_id: str
    kind: Literal["item", "fluid", "unknown"]
    category: str
    amount: float
    terms: list[RecipeTermDto]


class ExplorerRecipeDto(BaseModel):
    id: str
    category: str
    unlock_condition: UnlockConditionDto
    energy_required: float
    production_cost: float
    source_prototype_type: Literal["recipe", "boiler"]
    source_prototype_name: str | None
    inputs: list[ExplorerRecipeIODto]
    outputs: list[ExplorerRecipeIODto]


class ExplorerResponseDto(BaseModel):
    package_id: str
    overview: ExplorerOverviewDto
    milestones: list[MilestoneDto] = Field(default_factory=list)
    items: list[ExplorerItemDto]
    recipes: list[ExplorerRecipeDto]


class SparseClusteringConfigDto(BaseModel):
    enabled: StrictBool = False
    mode: Literal["fast", "balanced"] | None = None
    target_cluster_count: int | None = Field(default=None, gt=0)
    min_cluster_count: int | None = Field(default=None, gt=0)
    max_cluster_count: int | None = Field(default=None, gt=0)
    max_runtime_seconds: float | None = Field(default=None, gt=0.0)
    min_recipe_rate: float | None = Field(default=None, ge=0.0)
    hub_item_top_k: int | None = Field(default=None, gt=0)
    port_cost_weight: float | None = Field(default=None, ge=0.0)
    size_penalty_weight: float | None = Field(default=None, ge=0.0)
    flow_cost_weight: float | None = Field(default=None, ge=0.0)
    min_cluster_size_ratio: float | None = Field(default=None, ge=0.0)
    max_cluster_size_ratio: float | None = Field(default=None, ge=0.0)
    max_refinement_passes: int | None = Field(default=None, ge=0)
    port_epsilon: float | None = Field(default=None, ge=0.0)
    seed: int | None = None
    result_caps: dict[str, int] = Field(default_factory=dict)

    @field_validator(
        "max_runtime_seconds",
        "min_recipe_rate",
        "port_cost_weight",
        "size_penalty_weight",
        "flow_cost_weight",
        "min_cluster_size_ratio",
        "max_cluster_size_ratio",
        "port_epsilon",
    )
    @classmethod
    def numeric_values_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("sparse clustering numeric values must be finite")
        return value

    @field_validator("result_caps")
    @classmethod
    def result_caps_must_be_nonnegative(cls, value: dict[str, int]) -> dict[str, int]:
        invalid = sorted(key for key, cap in value.items() if cap < 0)
        if invalid:
            raise ValueError(f"result caps must be nonnegative: {', '.join(invalid)}")
        return value

    @model_validator(mode="after")
    def cluster_counts_must_be_consistent(self) -> SparseClusteringConfigDto:
        if (
            self.min_cluster_count is not None
            and self.max_cluster_count is not None
            and self.min_cluster_count > self.max_cluster_count
        ):
            raise ValueError("min_cluster_count must not exceed max_cluster_count")
        if self.target_cluster_count is not None and (
            (
                self.min_cluster_count is not None
                and self.target_cluster_count < self.min_cluster_count
            )
            or (
                self.max_cluster_count is not None
                and self.target_cluster_count > self.max_cluster_count
            )
        ):
            raise ValueError("target_cluster_count must be within min/max bounds")
        if (
            self.min_cluster_size_ratio is not None
            and self.max_cluster_size_ratio is not None
            and self.min_cluster_size_ratio > self.max_cluster_size_ratio
        ):
            raise ValueError(
                "min_cluster_size_ratio must not exceed max_cluster_size_ratio",
            )
        return self


class SolveRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_id: str | None = None
    selected_milestone: str | None = None
    solve_mode: Literal["hard_demand", "soft_diagnostics"] = "hard_demand"
    demands: dict[str, float] = Field(default_factory=dict)
    external_inputs: list[ExternalInputDto] = Field(default_factory=list)
    sparse_clustering: SparseClusteringConfigDto | None = None

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


class ClusterBoundaryItemDto(BaseModel):
    item_id: str
    direction: Literal["input", "output"]
    is_zero_net: bool
    quantity: float
    flow_cost: float
    port_cost: float


class ClusterDto(BaseModel):
    id: str
    label: str
    category: str
    recipe_ids: list[str]
    active_recipe_count: int
    boundary_item_type_count: int
    boundary_items: list[ClusterBoundaryItemDto]
    diagnostic_components: dict[str, float]


class ClusterCostDefaultsDto(BaseModel):
    flow_cost_per_quantity: float
    port_cost_per_boundary_type: float
    recipe_size_penalty: float
    boundary_type_size_penalty: float
    target_active_recipes: list[int]
    target_boundary_item_types: list[int]


class ClusterDiagnosticsDto(BaseModel):
    mode: Literal["diagnostic_only"]
    active_epsilon: float
    cost_defaults: ClusterCostDefaultsDto
    diagnostic_components: dict[str, float]
    base_objective_value: float
    diagnostic_total: float
    combined_diagnostic_objective_value: float
    clusters: list[ClusterDto]


class SparseCappedArrayDto(BaseModel):
    items: list[dict[str, object]]
    total_count: int
    truncated: bool


class SparsePortAwareObjectiveDto(BaseModel):
    port_cost: float
    size_penalty: float
    flow_cost: float
    total_score: float
    net_port_count: int
    refinement_passes: int


class SparseClusteringResultDto(BaseModel):
    status: Literal[
        "success",
        "skipped",
        "model_too_large",
        "timeout",
        "failed",
    ]
    message: str
    reason_code: (
        Literal[
            "disabled",
            "no_active_recipes",
            "model_too_large",
            "timeout",
            "failed",
        ]
        | None
    ) = None
    mode: Literal["fast", "balanced"]
    graph_type: Literal["recipe-to-recipe"]
    optimization_effect: Literal["none"]
    engine: str | None = None
    cluster_count: int | None = None
    target_cluster_count: int | None = None
    effective_config: dict[str, object]
    warnings: list[str]
    quality: dict[str, float] | None = None
    boundary_port_type_count: int | None = None
    net_port_count: int | None = None
    external_boundary_port_type_count: int | None = None
    port_aware_objective: SparsePortAwareObjectiveDto | None = None
    graph_statistics: dict[str, object] | None = None
    cluster_summaries: SparseCappedArrayDto | None = None
    recipe_assignments: SparseCappedArrayDto | None = None
    boundary_flows: SparseCappedArrayDto | None = None
    boundary_port_types: SparseCappedArrayDto | None = None
    external_boundary_port_types: SparseCappedArrayDto | None = None
    surplus_unmet_summary: SparseCappedArrayDto | None = None
    hub_summaries: SparseCappedArrayDto | None = None

    @model_validator(mode="after")
    def non_success_requires_reason_code(self) -> SparseClusteringResultDto:
        _require_reason_code(
            self.status,
            self.reason_code,
            success_statuses={"success"},
        )
        return self

    @model_serializer(mode="wrap")
    def omit_success_reason_code(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        data = cast("dict[str, object]", handler(self))
        if data.get("reason_code") is None:
            data.pop("reason_code", None)
        return data


class SolveResultDto(BaseModel):
    solver_status: str
    objective_value: float | None
    objective_components: dict[str, float]
    recipe_rates: dict[str, float]
    external_supplies: dict[str, float]
    unmet_demand: dict[str, float]
    surplus: dict[str, float]
    balance_residuals: dict[str, float]
    cluster_diagnostics: ClusterDiagnosticsDto | None = None
    sparse_clustering: SparseClusteringResultDto | None = None
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


def _require_reason_code(
    status: str,
    reason_code: str | None,
    *,
    success_statuses: set[str],
) -> None:
    if status not in success_statuses and reason_code is None:
        raise ValueError("non-success clustering results require reason_code")
