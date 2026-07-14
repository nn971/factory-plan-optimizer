from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from factory_plan_optimizer.optimizer.sparse_boundary import analyze_boundaries, capped
from factory_plan_optimizer.optimizer.sparse_engines import (
    PortAwareEngine,
    automatic_target,
)
from factory_plan_optimizer.optimizer.sparse_graph import (
    SparseGraph,
    build_sparse_graph,
)
from factory_plan_optimizer.optimizer.sparse_partition import (
    ObjectiveWeights,
    PartitionConfig,
    build_recipe_net_vectors,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game_data_extractor.data_contracts import FactoryDataPackage

SparseClusteringMode = Literal["fast", "balanced"]
SparseClusteringStatus = Literal[
    "success",
    "skipped",
    "model_too_large",
    "timeout",
    "failed",
]
SparseClusteringReasonCode = Literal[
    "disabled",
    "no_active_recipes",
    "model_too_large",
    "timeout",
    "failed",
]

DEFAULT_RESULT_CAPS = {
    "recipe_assignments": 2_000,
    "boundary_port_types": 2_000,
    "external_boundary_port_types": 200,
    "surplus_unmet": 100,
    "hub_summaries": 100,
    "cluster_summaries": 100,
}
LEGACY_RESULT_CAPS = {"boundary_flows"}
FAST_DEFAULT_REFINEMENT_PASSES = 1
BALANCED_DEFAULT_REFINEMENT_PASSES = 8
MIN_MAX_RUNTIME_SECONDS_EXCLUSIVE = 0.0
MIN_HUB_ITEM_TOP_K = 1


@dataclass(frozen=True, slots=True)
class SparseClusteringConfig:
    """Configuration for dependency-free sparse recipe graph clustering."""

    enabled: bool = False
    mode: SparseClusteringMode = "fast"
    graph_type: Literal["recipe-to-recipe"] = "recipe-to-recipe"
    target_cluster_count: int | None = None
    min_cluster_count: int | None = None
    max_cluster_count: int | None = None
    max_runtime_seconds: float = 5.0
    min_recipe_rate: float = 1e-9
    hub_item_top_k: int = 100
    max_refinement_passes: int | None = None
    port_cost_weight: float = 1000.0
    size_penalty_weight: float = 10.0
    flow_cost_weight: float = 0.0
    min_cluster_size_ratio: float = 0.5
    max_cluster_size_ratio: float = 1.5
    port_epsilon: float = 1e-9
    seed: int = 0
    result_caps: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_RESULT_CAPS),
    )

    def validate(self) -> None:  # noqa: C901,PLR0912
        """Raise ValueError when config settings are contradictory or invalid."""
        if self.mode not in {"fast", "balanced"}:
            message = f"invalid sparse clustering mode: {self.mode}"
            raise ValueError(message)
        for name in ("target_cluster_count", "min_cluster_count", "max_cluster_count"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                message = f"{name} must be positive"
                raise ValueError(message)
        if (
            self.min_cluster_count is not None
            and self.max_cluster_count is not None
            and self.min_cluster_count > self.max_cluster_count
        ):
            message = "min_cluster_count must not exceed max_cluster_count"
            raise ValueError(message)
        if self.target_cluster_count is not None:
            if (
                self.min_cluster_count is not None
                and self.target_cluster_count < self.min_cluster_count
            ):
                message = "target_cluster_count must be within min/max bounds"
                raise ValueError(message)
            if (
                self.max_cluster_count is not None
                and self.target_cluster_count > self.max_cluster_count
            ):
                message = "target_cluster_count must be within min/max bounds"
                raise ValueError(message)
        if self.max_runtime_seconds <= 0.0 or not isfinite(self.max_runtime_seconds):
            message = "max_runtime_seconds must be positive and finite"
            raise ValueError(message)
        if self.hub_item_top_k <= 0:
            message = "hub_item_top_k must be positive"
            raise ValueError(message)
        if self.min_recipe_rate < 0.0 or not isfinite(self.min_recipe_rate):
            message = "min_recipe_rate must be nonnegative and finite"
            raise ValueError(message)
        if self.max_refinement_passes is not None and self.max_refinement_passes < 0:
            message = "max_refinement_passes must be nonnegative"
            raise ValueError(message)
        for name in (
            "port_cost_weight",
            "size_penalty_weight",
            "flow_cost_weight",
            "min_cluster_size_ratio",
            "max_cluster_size_ratio",
            "port_epsilon",
        ):
            value = getattr(self, name)
            if value < 0.0 or not isfinite(value):
                message = f"{name} must be nonnegative and finite"
                raise ValueError(message)
        if self.min_cluster_size_ratio > self.max_cluster_size_ratio:
            message = "min_cluster_size_ratio must not exceed max_cluster_size_ratio"
            raise ValueError(message)
        for key, value in self.result_caps.items():
            if key not in DEFAULT_RESULT_CAPS and key not in LEGACY_RESULT_CAPS:
                message = f"unknown result cap: {key}"
                raise ValueError(message)
            if not isinstance(value, int) or value < 0:
                message = f"result cap {key} must be a nonnegative integer"
                raise ValueError(message)


def run_sparse_clustering(  # noqa: PLR0913
    package: FactoryDataPackage,
    *,
    recipe_rates: Mapping[str, float],
    external_supplies: Mapping[str, float],
    final_demands: Mapping[str, float] | None = None,
    surplus: Mapping[str, float] | None = None,
    unmet_demand: Mapping[str, float] | None = None,
    config: SparseClusteringConfig | None = None,
) -> dict[str, Any]:
    """Run sparse clustering as post-solve diagnostics without changing LP rates."""
    cfg = config or SparseClusteringConfig()
    cfg.validate()
    if not cfg.enabled:
        return _status(
            "skipped",
            cfg,
            "sparse clustering is disabled",
            reason_code="disabled",
        )
    deadline = monotonic() + cfg.max_runtime_seconds
    graph = build_sparse_graph(
        package,
        recipe_rates,
        min_recipe_rate=cfg.min_recipe_rate,
        hub_item_top_k=cfg.hub_item_top_k,
    )
    if not graph.active_recipes:
        return _status(
            "skipped",
            cfg,
            "no active recipes",
            reason_code="no_active_recipes",
        ) | {
            "graph_statistics": _graph_stats(graph, cfg),
        }
    target = automatic_target(
        len(graph.active_recipes),
        cfg.min_cluster_count,
        cfg.max_cluster_count,
        cfg.target_cluster_count,
    )
    if monotonic() > deadline:
        return _status(
            "timeout",
            cfg,
            "sparse clustering timed out before engine dispatch",
            reason_code="timeout",
        ) | {"graph_statistics": _graph_stats(graph, cfg)}
    warnings: list[str] = []
    partition_config = PartitionConfig(
        target_k=target,
        active_recipe_count=len(graph.active_recipes),
        weights=ObjectiveWeights(
            port_cost_weight=cfg.port_cost_weight,
            size_penalty_weight=cfg.size_penalty_weight,
            flow_cost_weight=cfg.flow_cost_weight,
        ),
        min_cluster_size_ratio=cfg.min_cluster_size_ratio,
        max_cluster_size_ratio=cfg.max_cluster_size_ratio,
        port_epsilon=cfg.port_epsilon,
    )
    active_ids = {recipe.id for recipe in graph.active_recipes}
    recipe_vectors = {
        recipe_id: vector
        for recipe_id, vector in build_recipe_net_vectors(package, recipe_rates).items()
        if recipe_id in active_ids
    }
    max_passes = cfg.max_refinement_passes
    if max_passes is None:
        max_passes = (
            FAST_DEFAULT_REFINEMENT_PASSES
            if cfg.mode == "fast"
            else BALANCED_DEFAULT_REFINEMENT_PASSES
        )
    try:
        engine_result = PortAwareEngine(max_refinement_passes=max_passes).cluster(
            recipe_vectors,
            graph.edges,
            target,
            partition_config,
            deadline,
        )
    except TimeoutError:
        return _status(
            "timeout",
            cfg,
            "sparse clustering timed out",
            reason_code="timeout",
        ) | {
            "graph_statistics": _graph_stats(graph, cfg),
        }
    assignments = engine_result.assignments
    boundary = analyze_boundaries(
        graph,
        assignments,
        recipe_vectors,
        cfg.port_epsilon,
        external_supplies,
        package.final_demands if final_demands is None else final_demands,
        {} if surplus is None else surplus,
        {} if unmet_demand is None else unmet_demand,
        _caps(cfg),
    )
    actual_count = len(set(assignments.values()))
    if actual_count != target:
        warnings.append(
            f"actual cluster count {actual_count} differs from target {target}",
        )
    hub_payload = capped(
        [asdict(hub) for hub in graph.hub_summaries],
        _caps(cfg)["hub_summaries"],
    )
    warnings.extend(_truncation_warnings(boundary | {"hub_summaries": hub_payload}))
    graph_stats = _graph_stats(graph, cfg)
    graph_stats["boundary_port_type_count"] = boundary["boundary_port_type_count"]
    graph_stats["net_port_count"] = boundary["net_port_count"]
    graph_stats["external_boundary_port_type_count"] = boundary[
        "external_boundary_port_type_count"
    ]
    return {
        "status": "success",
        "message": "sparse clustering completed",
        "mode": cfg.mode,
        "engine": "port-aware-seeded-refinement",
        "optimization_effect": "none",
        "graph_type": cfg.graph_type,
        "cluster_count": actual_count,
        "target_cluster_count": target,
        "effective_config": _effective_config(cfg),
        "warnings": warnings,
        "port_aware_objective": {
            "port_cost": engine_result.objective.port_cost,
            "size_penalty": engine_result.objective.size_penalty,
            "flow_cost": engine_result.objective.flow_cost,
            "total_score": engine_result.objective.total_score,
            "net_port_count": engine_result.objective.net_port_count,
            "refinement_passes": engine_result.refinement_passes,
        },
        **boundary,
        "hub_summaries": hub_payload,
        "graph_statistics": graph_stats,
    }


def _status(
    status: SparseClusteringStatus,
    cfg: SparseClusteringConfig,
    message: str,
    *,
    reason_code: SparseClusteringReasonCode,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason_code,
        "message": message,
        "mode": cfg.mode,
        "graph_type": cfg.graph_type,
        "optimization_effect": "none",
        "warnings": [],
        "effective_config": _effective_config(cfg),
    }


def _caps(cfg: SparseClusteringConfig) -> dict[str, int]:
    return dict(DEFAULT_RESULT_CAPS) | {
        key: value
        for key, value in cfg.result_caps.items()
        if key in DEFAULT_RESULT_CAPS
    }


def _graph_stats(graph: SparseGraph, cfg: SparseClusteringConfig) -> dict[str, Any]:
    active_items = set(graph.producers_by_item) | set(graph.consumers_by_item)
    return {
        "active_recipe_count": len(graph.active_recipes),
        "active_item_count": len(active_items),
        "edge_count": len(graph.edges),
        "candidate_edge_count": graph.total_candidate_edges,
        "candidate_estimated_flow": graph.total_candidate_flow,
        "skipped_hub_edge_count": sum(hub.skipped_count for hub in graph.hub_summaries),
        "hub_item_top_k": cfg.hub_item_top_k,
        "result_caps": _caps(cfg),
    }


def _effective_config(cfg: SparseClusteringConfig) -> dict[str, Any]:
    return {
        "mode": cfg.mode,
        "seed": cfg.seed,
        "max_runtime_seconds": cfg.max_runtime_seconds,
        "min_recipe_rate": cfg.min_recipe_rate,
        "hub_item_top_k": cfg.hub_item_top_k,
        "max_refinement_passes": cfg.max_refinement_passes,
        "port_cost_weight": cfg.port_cost_weight,
        "size_penalty_weight": cfg.size_penalty_weight,
        "flow_cost_weight": cfg.flow_cost_weight,
        "min_cluster_size_ratio": cfg.min_cluster_size_ratio,
        "max_cluster_size_ratio": cfg.max_cluster_size_ratio,
        "port_epsilon": cfg.port_epsilon,
        "result_caps": _caps(cfg),
    }


def sparse_clustering_defaults() -> dict[str, Any]:
    """Return public request defaults owned by optimizer-core."""
    cfg = SparseClusteringConfig()
    return {
        "enabled": cfg.enabled,
        "mode": cfg.mode,
        "target_cluster_count": cfg.target_cluster_count,
        "min_cluster_count": cfg.min_cluster_count,
        "max_cluster_count": cfg.max_cluster_count,
        "max_runtime_seconds": cfg.max_runtime_seconds,
        "min_recipe_rate": cfg.min_recipe_rate,
        "hub_item_top_k": cfg.hub_item_top_k,
        "port_cost_weight": cfg.port_cost_weight,
        "size_penalty_weight": cfg.size_penalty_weight,
        "flow_cost_weight": cfg.flow_cost_weight,
        "min_cluster_size_ratio": cfg.min_cluster_size_ratio,
        "max_cluster_size_ratio": cfg.max_cluster_size_ratio,
        "max_refinement_passes": cfg.max_refinement_passes,
        "effective_refinement_passes_by_mode": {
            "fast": FAST_DEFAULT_REFINEMENT_PASSES,
            "balanced": BALANCED_DEFAULT_REFINEMENT_PASSES,
        },
        "port_epsilon": cfg.port_epsilon,
        "seed": cfg.seed,
        "result_caps": _caps(cfg),
        "guardrails": sparse_clustering_guardrails(),
    }


def sparse_clustering_guardrails() -> dict[str, Any]:
    """Return sparse request guardrails for clients."""
    return {
        "max_runtime_seconds": {"exclusive_min": MIN_MAX_RUNTIME_SECONDS_EXCLUSIVE},
        "hub_item_top_k": {"min": MIN_HUB_ITEM_TOP_K, "integer": True},
        "cluster_counts": {"min": 1, "integer": True},
        "max_refinement_passes": {"min": 0, "integer": True, "nullable": True},
        "nonnegative_fields": [
            "min_recipe_rate",
            "port_cost_weight",
            "size_penalty_weight",
            "flow_cost_weight",
            "min_cluster_size_ratio",
            "max_cluster_size_ratio",
            "port_epsilon",
        ],
    }


def _truncation_warnings(payloads: Mapping[str, Any]) -> list[str]:
    warnings = []
    for name, payload in sorted(payloads.items()):
        if isinstance(payload, dict) and payload.get("truncated") is True:
            warnings.append(f"{name} truncated to configured result cap")
    return warnings
