from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from pyomo.common.errors import ApplicationError
from pyomo.contrib.appsi.base import TerminationCondition
from pyomo.contrib.appsi.solvers import Highs
from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Var,
    minimize,
    value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game_data_extractor.data_contracts import FactoryDataPackage

OptimizedClusteringMode = Literal["continuous_split"]
OptimizedClusteringPreset = Literal["balanced", "fewer_ports", "even_size"]
MaxClusterSizeConstraint = Literal["soft", "hard"]
OptimizedClusteringStatus = Literal[
    "disabled",
    "no_active_recipes",
    "optimal",
    "feasible_non_optimal",
    "timeout_no_incumbent",
    "infeasible",
    "solver_unavailable",
    "model_too_large",
]

MODES: tuple[OptimizedClusteringMode, ...] = ("continuous_split",)
PRESETS: tuple[OptimizedClusteringPreset, ...] = (
    "balanced",
    "fewer_ports",
    "even_size",
)
MAX_CLUSTER_SIZE_CONSTRAINTS: tuple[MaxClusterSizeConstraint, ...] = ("soft", "hard")
STATUSES: tuple[OptimizedClusteringStatus, ...] = (
    "disabled",
    "no_active_recipes",
    "optimal",
    "feasible_non_optimal",
    "timeout_no_incumbent",
    "infeasible",
    "solver_unavailable",
    "model_too_large",
)

MIN_REPORTING_EPSILON = 1e-9
MAX_REPORTING_EPSILON = 1e-2
DEFAULT_REPORTING_EPSILON = 1e-6
MIN_TIME_LIMIT_SECONDS = 1.0
MAX_TIME_LIMIT_SECONDS = 600.0
DEFAULT_TIME_LIMIT_SECONDS = 60.0
RECONCILIATION_TOLERANCE = 1e-6
MAX_MODEL_SIZE_SCORE = 1_000_000
BINARY_ACTIVE_THRESHOLD = 0.5
_NONNEGATIVE_PARAMETER_FIELDS = (
    "flow_cost_per_quantity",
    "port_cost_per_item_type",
    "cluster_size_penalty_weight",
    "min_cluster_size",
)


class _Solver(Protocol):
    def available(self) -> bool: ...

    def solve(self, model: ConcreteModel) -> object: ...


@dataclass(frozen=True, slots=True)
class OptimizedClusteringParameters:
    """Requested optimized clustering parameters before preset resolution."""

    enabled: bool = False
    mode: str = "continuous_split"
    preset: str = "balanced"
    flow_cost_per_quantity: float | None = None
    port_cost_per_item_type: float | None = None
    cluster_size_penalty_weight: float | None = None
    min_cluster_size: float | None = None
    max_cluster_size: float | None = None
    reporting_epsilon: float | None = None
    time_limit_seconds: float | None = None
    max_cluster_size_constraint: str = "soft"
    allow_recipe_splitting: bool = False
    splittable_recipe_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectiveOptimizedClusteringParameters:
    """Resolved optimized clustering parameters safe to serialize and report."""

    enabled: bool
    mode: OptimizedClusteringMode
    preset: OptimizedClusteringPreset
    preset_is_provisional: bool
    flow_cost_per_quantity: float
    port_cost_per_item_type: float
    cluster_size_penalty_weight: float
    min_cluster_size: float
    max_cluster_size: float
    reporting_epsilon: float
    time_limit_seconds: float
    max_cluster_size_constraint: MaxClusterSizeConstraint
    allow_recipe_splitting: bool
    splittable_recipe_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, bool | float | str | list[str]]:
        """Return JSON-shaped parameters for result payloads."""
        data = asdict(self)
        data["splittable_recipe_ids"] = list(self.splittable_recipe_ids)
        return data


BALANCED_PARAMETERS = EffectiveOptimizedClusteringParameters(
    enabled=False,
    mode="continuous_split",
    preset="balanced",
    preset_is_provisional=False,
    flow_cost_per_quantity=1.0,
    port_cost_per_item_type=100.0,
    cluster_size_penalty_weight=10.0,
    min_cluster_size=5.0,
    max_cluster_size=15.0,
    reporting_epsilon=DEFAULT_REPORTING_EPSILON,
    time_limit_seconds=DEFAULT_TIME_LIMIT_SECONDS,
    max_cluster_size_constraint="soft",
    allow_recipe_splitting=False,
    splittable_recipe_ids=(),
)


def resolve_parameters(
    parameters: OptimizedClusteringParameters | None = None,
) -> EffectiveOptimizedClusteringParameters:
    requested = parameters or OptimizedClusteringParameters()
    validate_parameters(requested)

    preset = cast("OptimizedClusteringPreset", requested.preset)
    mode = cast("OptimizedClusteringMode", requested.mode)
    effective = replace(
        BALANCED_PARAMETERS,
        enabled=requested.enabled,
        mode=mode,
        preset=preset,
        preset_is_provisional=preset != "balanced",
    )
    if preset == "fewer_ports":
        effective = replace(effective, port_cost_per_item_type=200.0)
    elif preset == "even_size":
        effective = replace(effective, cluster_size_penalty_weight=25.0)

    return _apply_parameter_overrides(effective, requested)


def validate_parameters(parameters: OptimizedClusteringParameters) -> None:
    if type(parameters.enabled) is not bool:
        msg = "enabled must be a real bool"
        raise ValueError(msg)
    if parameters.mode not in MODES:
        msg = f"unknown optimized clustering mode: {parameters.mode}"
        raise ValueError(msg)
    if parameters.preset not in PRESETS:
        msg = f"unknown optimized clustering preset: {parameters.preset}"
        raise ValueError(msg)
    if parameters.max_cluster_size_constraint not in MAX_CLUSTER_SIZE_CONSTRAINTS:
        msg = (
            "unknown max cluster size constraint: "
            f"{parameters.max_cluster_size_constraint}"
        )
        raise ValueError(msg)
    if type(parameters.allow_recipe_splitting) is not bool:
        msg = "allow_recipe_splitting must be a real bool"
        raise ValueError(msg)
    if not isinstance(parameters.splittable_recipe_ids, tuple):
        msg = "splittable_recipe_ids must be a tuple"
        raise TypeError(msg)

    effective = _resolve_parameters_without_validation(parameters)
    _validate_numeric_parameters(effective)


def _validate_numeric_parameters(
    effective: EffectiveOptimizedClusteringParameters,
) -> None:
    nonnegative_fields = _NONNEGATIVE_PARAMETER_FIELDS
    numeric_fields = (
        *nonnegative_fields,
        "max_cluster_size",
        "reporting_epsilon",
        "time_limit_seconds",
    )
    for field in numeric_fields:
        if not isfinite(getattr(effective, field)):
            msg = f"{field} must be finite"
            raise ValueError(msg)
    for field in nonnegative_fields:
        if getattr(effective, field) < 0.0:
            msg = f"{field} must be nonnegative"
            raise ValueError(msg)
    if effective.max_cluster_size <= 0.0:
        msg = "max_cluster_size must be positive"
        raise ValueError(msg)
    if effective.min_cluster_size > effective.max_cluster_size:
        msg = "min_cluster_size must be less than or equal to max_cluster_size"
        raise ValueError(msg)
    reporting_epsilon_is_valid = (
        MIN_REPORTING_EPSILON <= effective.reporting_epsilon <= MAX_REPORTING_EPSILON
    )
    if not reporting_epsilon_is_valid:
        msg = "reporting_epsilon must be between 1e-9 and 1e-2 inclusive"
        raise ValueError(msg)
    time_limit_is_valid = (
        MIN_TIME_LIMIT_SECONDS <= effective.time_limit_seconds <= MAX_TIME_LIMIT_SECONDS
    )
    if not time_limit_is_valid:
        msg = "time_limit_seconds must be between 1 and 600 inclusive"
        raise ValueError(msg)


def _resolve_parameters_without_validation(
    parameters: OptimizedClusteringParameters,
) -> EffectiveOptimizedClusteringParameters:
    preset = parameters.preset
    effective = replace(
        BALANCED_PARAMETERS,
        enabled=parameters.enabled,
        mode="continuous_split",
        preset="balanced",
        preset_is_provisional=False,
    )
    if preset == "fewer_ports":
        effective = replace(
            effective,
            preset="fewer_ports",
            preset_is_provisional=True,
            port_cost_per_item_type=200.0,
        )
    elif preset == "even_size":
        effective = replace(
            effective,
            preset="even_size",
            preset_is_provisional=True,
            cluster_size_penalty_weight=25.0,
        )

    return _apply_parameter_overrides(effective, parameters)


def _apply_parameter_overrides(
    effective: EffectiveOptimizedClusteringParameters,
    parameters: OptimizedClusteringParameters,
) -> EffectiveOptimizedClusteringParameters:
    if parameters.flow_cost_per_quantity is not None:
        effective = replace(
            effective,
            flow_cost_per_quantity=parameters.flow_cost_per_quantity,
        )
    if parameters.port_cost_per_item_type is not None:
        effective = replace(
            effective,
            port_cost_per_item_type=parameters.port_cost_per_item_type,
        )
    if parameters.cluster_size_penalty_weight is not None:
        effective = replace(
            effective,
            cluster_size_penalty_weight=parameters.cluster_size_penalty_weight,
        )
    if parameters.min_cluster_size is not None:
        effective = replace(effective, min_cluster_size=parameters.min_cluster_size)
    if parameters.max_cluster_size is not None:
        effective = replace(effective, max_cluster_size=parameters.max_cluster_size)
    if parameters.reporting_epsilon is not None:
        effective = replace(effective, reporting_epsilon=parameters.reporting_epsilon)
    if parameters.time_limit_seconds is not None:
        effective = replace(effective, time_limit_seconds=parameters.time_limit_seconds)
    return replace(
        effective,
        max_cluster_size_constraint=cast(
            "MaxClusterSizeConstraint",
            parameters.max_cluster_size_constraint,
        ),
        allow_recipe_splitting=parameters.allow_recipe_splitting,
        splittable_recipe_ids=parameters.splittable_recipe_ids,
    )


def empty_result(
    *,
    status: OptimizedClusteringStatus = "no_active_recipes",
    parameters: EffectiveOptimizedClusteringParameters | None = None,
) -> dict[str, Any]:
    objective_components = {
        "flow_cost": 0.0,
        "port_cost": 0.0,
        "cluster_size_penalty": 0.0,
        "duplication_cost": 0.0,
    }
    cost_breakdown = {
        "inter_cluster_flow_cost": 0.0,
        "external_flow_cost": 0.0,
        "inter_cluster_port_cost": 0.0,
        "external_port_cost": 0.0,
        "cluster_size_penalty": 0.0,
        "duplication_cost": 0.0,
    }
    return {
        "status": status,
        "mode": (parameters or BALANCED_PARAMETERS).mode,
        "effective_parameters": (parameters or BALANCED_PARAMETERS).to_dict(),
        "objective_value": 0.0,
        "objective_components": objective_components,
        "cost_breakdown": cost_breakdown,
        "clusters": [],
        "allocations": [],
        "flows": [],
        "external_flows": [],
        "reconciliation": reconcile_objective_breakdown(
            objective_components,
            cost_breakdown,
        ),
    }


def optimize_clustering(  # noqa: C901, PLR0911, PLR0913
    package: FactoryDataPackage,
    recipe_rates: Mapping[str, float],
    *,
    external_supplies: Mapping[str, float] | None = None,
    unmet_demand: Mapping[str, float] | None = None,
    surplus: Mapping[str, float] | None = None,
    parameters: OptimizedClusteringParameters | None = None,
    max_model_size_score: int = MAX_MODEL_SIZE_SCORE,
) -> dict[str, Any]:
    """Solve the internal second-stage clustering MILP for fixed recipe totals."""
    effective = resolve_parameters(parameters)
    if not effective.enabled:
        return empty_result(status="disabled", parameters=effective)

    active_rates = {
        recipe_id: rate
        for recipe_id, rate in recipe_rates.items()
        if rate > effective.reporting_epsilon
    }
    if not active_rates:
        return empty_result(parameters=effective)

    recipe_by_id = {recipe.id: recipe for recipe in package.recipes}
    active_recipe_ids = sorted(rid for rid in recipe_by_id if rid in active_rates)
    item_ids = sorted(
        {
            item_id
            for recipe_id in active_recipe_ids
            for item_id in recipe_by_id[recipe_id].coefficients
        },
    )
    cluster_ids = [f"cluster_{index}" for index, _ in enumerate(active_recipe_ids)]
    size_score = _model_size_score(len(active_recipe_ids), len(item_ids))
    if size_score > max_model_size_score:
        result = empty_result(status="model_too_large", parameters=effective)
        result["message"] = "optimized clustering model exceeds guardrail"
        result["model_size"] = {
            "active_recipes": len(active_recipe_ids),
            "items": len(item_ids),
            "candidate_clusters": len(cluster_ids),
            "score": size_score,
            "max_score": max_model_size_score,
        }
        return result

    model = _build_optimized_model(
        package, active_rates, effective, active_recipe_ids, cluster_ids, item_ids
    )
    try:
        solver = _make_solver()
        if (config := getattr(solver, "config", None)) is not None:
            config.load_solution = False
            config.time_limit = effective.time_limit_seconds
        if not solver.available():
            return _solver_failure(
                "solver_unavailable", effective, "HiGHS solver is not available"
            )
        solve_result = solver.solve(model)
    except (ImportError, ModuleNotFoundError, ApplicationError) as error:
        return _solver_failure(
            "solver_unavailable", effective, "HiGHS solver is not available", str(error)
        )

    termination = getattr(solve_result, "termination_condition", None)
    status = _status_from_termination(termination)
    if status in {"infeasible", "timeout_no_incumbent"}:
        return _solver_failure(
            status,
            effective,
            "optimized clustering did not produce an incumbent",
            str(termination),
        )
    if (load_vars := getattr(solver, "load_vars", None)) is None:
        if status == "feasible_non_optimal":
            return _solver_failure(
                "timeout_no_incumbent",
                effective,
                "optimized clustering timed out without loadable incumbent",
                str(termination),
            )
    else:
        try:
            load_vars()
        except (RuntimeError, ValueError, ApplicationError) as error:
            if status == "feasible_non_optimal":
                return _solver_failure(
                    "timeout_no_incumbent",
                    effective,
                    "optimized clustering timed out without loadable incumbent",
                    repr(error),
                )
            raise
    return _report_result(
        model,
        package,
        active_rates,
        effective,
        active_recipe_ids,
        cluster_ids,
        item_ids,
        status,
        external_supplies or {},
        unmet_demand or {},
        surplus or {},
    )


def _make_solver() -> _Solver:
    return cast("_Solver", Highs())


def _model_size_score(recipe_count: int, item_count: int) -> int:
    return recipe_count * recipe_count * max(1, item_count) * 4


def _build_optimized_model(  # noqa: PLR0913
    package: FactoryDataPackage,
    active_rates: Mapping[str, float],
    effective: EffectiveOptimizedClusteringParameters,
    recipe_ids: list[str],
    cluster_ids: list[str],
    item_ids: list[str],
) -> ConcreteModel:
    recipe_by_id = {recipe.id: recipe for recipe in package.recipes}
    pairs = [(a, b) for a in cluster_ids for b in cluster_ids if a != b]
    model = ConcreteModel()
    model.y = Var(recipe_ids, cluster_ids, domain=NonNegativeReals)
    model.assigned = Var(recipe_ids, cluster_ids, domain=Binary)
    model.used = Var(cluster_ids, domain=Binary)
    model.under = Var(cluster_ids, domain=NonNegativeReals)
    model.over = Var(cluster_ids, domain=NonNegativeReals)
    model.flow = Var(pairs, item_ids, domain=NonNegativeReals)
    model.external_in = Var(cluster_ids, item_ids, domain=NonNegativeReals)
    model.external_out = Var(cluster_ids, item_ids, domain=NonNegativeReals)
    model.inter_port_in = Var(cluster_ids, item_ids, domain=Binary)
    model.inter_port_out = Var(cluster_ids, item_ids, domain=Binary)
    model.external_port_in = Var(cluster_ids, item_ids, domain=Binary)
    model.external_port_out = Var(cluster_ids, item_ids, domain=Binary)
    max_rate = sum(active_rates.values())
    big_m = max(
        1.0,
        sum(
            abs(coef) * active_rates.get(recipe.id, 0.0)
            for recipe in package.recipes
            for coef in recipe.coefficients.values()
        ),
    )

    model.recipe_total = Constraint(
        recipe_ids,
        rule=lambda _m, r: sum(model.y[r, k] for k in cluster_ids) == active_rates[r],
    )
    model.activation = Constraint(
        recipe_ids,
        cluster_ids,
        rule=lambda _m, r, k: model.y[r, k] <= active_rates[r] * model.used[k],
    )
    no_split_recipe_ids = [
        recipe_id
        for recipe_id in recipe_ids
        if not _recipe_may_split(recipe_id, effective)
    ]
    model.no_split_assignment_total = Constraint(
        no_split_recipe_ids,
        rule=lambda _m, r: sum(model.assigned[r, k] for k in cluster_ids) == 1,
    )
    model.no_split_assignment_bound = Constraint(
        no_split_recipe_ids,
        cluster_ids,
        rule=lambda _m, r, k: model.y[r, k] <= active_rates[r] * model.assigned[r, k],
    )
    model.size_upper = Constraint(
        cluster_ids,
        rule=lambda _m, k: (
            sum(model.y[r, k] for r in recipe_ids) <= max_rate * model.used[k]
        ),
    )
    model.size_min = Constraint(
        cluster_ids,
        rule=lambda _m, k: (
            model.under[k]
            >= effective.min_cluster_size * model.used[k]
            - sum(model.y[r, k] for r in recipe_ids)
        ),
    )
    model.size_max = Constraint(
        cluster_ids,
        rule=lambda _m, k: _max_size_constraint_rule(
            model,
            recipe_ids,
            k,
            effective,
        ),
    )

    def balance_rule(_m: ConcreteModel, k: str, i: str) -> object:
        net = sum(
            recipe_by_id[r].coefficients.get(i, 0.0) * model.y[r, k] for r in recipe_ids
        )
        incoming = sum(model.flow[a, b, i] for a, b in pairs if b == k)
        outgoing = sum(model.flow[a, b, i] for a, b in pairs if a == k)
        return (
            net
            + model.external_in[k, i]
            - model.external_out[k, i]
            + incoming
            - outgoing
            == 0
        )

    model.balance = Constraint(cluster_ids, item_ids, rule=balance_rule)
    model.inter_port_in_bound = Constraint(
        cluster_ids,
        item_ids,
        rule=lambda _m, k, i: (
            sum(model.flow[a, b, i] for a, b in pairs if b == k)
            <= big_m * model.inter_port_in[k, i]
        ),
    )
    model.inter_port_out_bound = Constraint(
        cluster_ids,
        item_ids,
        rule=lambda _m, k, i: (
            sum(model.flow[a, b, i] for a, b in pairs if a == k)
            <= big_m * model.inter_port_out[k, i]
        ),
    )
    model.external_port_in_bound = Constraint(
        cluster_ids,
        item_ids,
        rule=lambda _m, k, i: (
            model.external_in[k, i] <= big_m * model.external_port_in[k, i]
        ),
    )
    model.external_port_out_bound = Constraint(
        cluster_ids,
        item_ids,
        rule=lambda _m, k, i: (
            model.external_out[k, i] <= big_m * model.external_port_out[k, i]
        ),
    )
    inter_flow = sum(model.flow[a, b, i] for a, b in pairs for i in item_ids)
    external_flow = sum(
        model.external_in[k, i] + model.external_out[k, i]
        for k in cluster_ids
        for i in item_ids
    )
    ports = sum(
        model.inter_port_in[k, i]
        + model.inter_port_out[k, i]
        + model.external_port_in[k, i]
        + model.external_port_out[k, i]
        for k in cluster_ids
        for i in item_ids
    )
    size_penalty = sum(model.under[k] + model.over[k] for k in cluster_ids)
    model.objective = Objective(
        expr=effective.flow_cost_per_quantity * (inter_flow + external_flow)
        + effective.port_cost_per_item_type * ports
        + effective.cluster_size_penalty_weight * size_penalty,
        sense=minimize,
    )
    return model


def _recipe_may_split(
    recipe_id: str,
    effective: EffectiveOptimizedClusteringParameters,
) -> bool:
    return (
        effective.allow_recipe_splitting or recipe_id in effective.splittable_recipe_ids
    )


def _max_size_constraint_rule(
    model: ConcreteModel,
    recipe_ids: list[str],
    cluster_id: str,
    effective: EffectiveOptimizedClusteringParameters,
) -> object:
    size = sum(model.y[r, cluster_id] for r in recipe_ids)
    if effective.max_cluster_size_constraint == "hard":
        return size <= effective.max_cluster_size * model.used[cluster_id]
    return model.over[cluster_id] >= size - effective.max_cluster_size


def _status_from_termination(termination: object) -> OptimizedClusteringStatus:
    if termination == TerminationCondition.optimal:
        return "optimal"
    if termination in {
        TerminationCondition.maxTimeLimit,
        TerminationCondition.maxIterations,
    }:
        return "feasible_non_optimal"
    if termination in {
        TerminationCondition.infeasible,
        TerminationCondition.infeasibleOrUnbounded,
    }:
        return "infeasible"
    return "timeout_no_incumbent"


def _solver_failure(
    status: OptimizedClusteringStatus,
    parameters: EffectiveOptimizedClusteringParameters,
    message: str,
    details: str = "",
) -> dict[str, Any]:
    result = empty_result(status=status, parameters=parameters)
    result["message"] = message
    result["details"] = details
    return result


def _report_result(  # noqa: PLR0913
    model: ConcreteModel,
    package: FactoryDataPackage,
    active_rates: Mapping[str, float],
    effective: EffectiveOptimizedClusteringParameters,
    recipe_ids: list[str],
    cluster_ids: list[str],
    item_ids: list[str],
    status: OptimizedClusteringStatus,
    external_supplies: Mapping[str, float],
    unmet_demand: Mapping[str, float],
    surplus: Mapping[str, float],
) -> dict[str, Any]:
    pairs = [(a, b) for a in cluster_ids for b in cluster_ids if a != b]
    retained_cluster_ids = [
        k
        for k in cluster_ids
        if sum(_value(model.y[r, k]) for r in recipe_ids) > effective.reporting_epsilon
    ]
    retained_cluster_set = set(retained_cluster_ids)
    allocations = [
        {
            "recipe_id": r,
            "cluster_id": k,
            "rate": _value(model.y[r, k]),
            "fraction": _value(model.y[r, k]) / active_rates[r],
        }
        for r in recipe_ids
        for k in retained_cluster_ids
        if _value(model.y[r, k]) > effective.reporting_epsilon
    ]
    clusters = [
        {
            "cluster_id": k,
            "used": sum(_value(model.y[r, k]) for r in recipe_ids)
            > effective.reporting_epsilon,
            "size": sum(_value(model.y[r, k]) for r in recipe_ids),
            "under_min": _value(model.under[k]),
            "over_max": _value(model.over[k]),
        }
        for k in retained_cluster_ids
    ]
    flows = [
        {
            "from_cluster_id": a,
            "to_cluster_id": b,
            "item_id": i,
            "quantity": _value(model.flow[a, b, i]),
        }
        for a, b in pairs
        for i in item_ids
        if a in retained_cluster_set
        if b in retained_cluster_set
        if _value(model.flow[a, b, i]) > effective.reporting_epsilon
    ]
    external_flows = _external_rows(
        model,
        retained_cluster_ids,
        item_ids,
        effective,
        external_supplies,
        package.final_demands,
        unmet_demand,
        surplus,
    )
    inter_flow_qty = sum(_row_quantity(row) for row in flows)
    external_flow_qty = sum(_row_quantity(row) for row in external_flows)
    inter_ports = len(
        {(str(row["from_cluster_id"]), str(row["item_id"]), "out") for row in flows}
    ) + len({(str(row["to_cluster_id"]), str(row["item_id"]), "in") for row in flows})
    external_ports = len(
        {
            (str(row["cluster_id"]), str(row["item_id"]), str(row["direction"]))
            for row in external_flows
        },
    )
    size_penalty = effective.cluster_size_penalty_weight * sum(
        _value(model.under[k]) + _value(model.over[k]) for k in retained_cluster_ids
    )
    cost_breakdown = {
        "inter_cluster_flow_cost": effective.flow_cost_per_quantity * inter_flow_qty,
        "external_flow_cost": effective.flow_cost_per_quantity * external_flow_qty,
        "inter_cluster_port_cost": effective.port_cost_per_item_type * inter_ports,
        "external_port_cost": effective.port_cost_per_item_type * external_ports,
        "cluster_size_penalty": size_penalty,
        "duplication_cost": 0.0,
    }
    objective_components = {
        "flow_cost": cost_breakdown["inter_cluster_flow_cost"]
        + cost_breakdown["external_flow_cost"],
        "port_cost": cost_breakdown["inter_cluster_port_cost"]
        + cost_breakdown["external_port_cost"],
        "cluster_size_penalty": size_penalty,
        "duplication_cost": 0.0,
    }
    objective_value = _value(model.objective)
    return {
        "status": status,
        "mode": effective.mode,
        "effective_parameters": effective.to_dict(),
        "objective_value": objective_value,
        "objective_components": objective_components,
        "cost_breakdown": cost_breakdown,
        "clusters": clusters,
        "allocations": allocations,
        "flows": flows,
        "external_flows": external_flows,
        "reconciliation": reconcile_objective_breakdown(
            objective_components, cost_breakdown
        ),
        "objective_reconciliation": {
            "objective_value": objective_value,
            "reported_component_total": sum(objective_components.values()),
            "difference": objective_value - sum(objective_components.values()),
            "reconciled": abs(objective_value - sum(objective_components.values()))
            <= RECONCILIATION_TOLERANCE,
        },
    }


def _external_rows(
    model: ConcreteModel,
    cluster_ids: list[str],
    item_ids: list[str],
    effective: EffectiveOptimizedClusteringParameters,
    _external_supplies: Mapping[str, float],
    _final_demands: Mapping[str, float],
    _unmet_demand: Mapping[str, float],
    _surplus: Mapping[str, float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cluster_id in cluster_ids:
        for item_id in item_ids:
            incoming = _value(model.external_in[cluster_id, item_id])
            outgoing = _value(model.external_out[cluster_id, item_id])
            if incoming > effective.reporting_epsilon:
                rows.append(
                    {
                        "cluster_id": cluster_id,
                        "item_id": item_id,
                        "direction": "in",
                        "boundary_label": "aggregate_external_balance",
                        "quantity": incoming,
                    }
                )
            if outgoing > effective.reporting_epsilon:
                rows.append(
                    {
                        "cluster_id": cluster_id,
                        "item_id": item_id,
                        "direction": "out",
                        "boundary_label": "aggregate_external_balance",
                        "quantity": outgoing,
                    }
                )
    return rows


def _value(expression: object) -> float:
    return float(value(expression))


def _row_quantity(row: dict[str, object]) -> float:
    return cast("float", row["quantity"])


def reconcile_objective_breakdown(
    objective_components: dict[str, float],
    cost_breakdown: dict[str, float],
    *,
    tolerance: float = RECONCILIATION_TOLERANCE,
) -> dict[str, bool | float]:
    objective_total = sum(objective_components.values())
    breakdown_total = sum(cost_breakdown.values())
    difference = objective_total - breakdown_total
    return {
        "objective_total": objective_total,
        "breakdown_total": breakdown_total,
        "difference": difference,
        "reconciled": abs(difference) <= tolerance,
    }
