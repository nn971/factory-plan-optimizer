from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, cast

from pyomo.common.errors import ApplicationError
from pyomo.contrib.appsi.base import (
    TerminationCondition,
)
from pyomo.contrib.appsi.solvers import Highs
from pyomo.environ import (
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Var,
    minimize,
    value,
)

from factory_plan_optimizer.optimizer.cluster_diagnostics import (
    build_cluster_diagnostics,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_data_extractor.data_contracts import FactoryDataPackage
    from pyomo.core.base.var import VarData

type GlobalRecipeLpStatus = Literal[
    "optimal",
    "solver_unavailable",
    "infeasible",
    "unbounded",
    "non_optimal",
    "error",
]
type GlobalRecipeLpSolveMode = Literal["hard_demand", "soft_diagnostics"]

OBJECTIVE_COMPONENT_KEYS = (
    "raw_cost",
    "production_cost",
    "flow_cost",
    "port_cost",
    "cluster_cost",
    "duplication_cost",
    "unmet_demand_penalty",
)


@dataclass(frozen=True, slots=True)
class GlobalRecipeLpResult:
    """Structured result or failure for the initial global recipe LP."""

    status: GlobalRecipeLpStatus
    objective_value: float | None
    objective_components: Mapping[str, float]
    recipe_rates: Mapping[str, float] = field(default_factory=dict)
    external_supplies: Mapping[str, float] = field(default_factory=dict)
    unmet_demand: Mapping[str, float] = field(default_factory=dict)
    surplus: Mapping[str, float] = field(default_factory=dict)
    balance_residuals: Mapping[str, float] = field(default_factory=dict)
    cluster_diagnostics: Mapping[str, object] = field(default_factory=dict)
    sparse_clustering: Mapping[str, object] | None = None
    message: str = ""
    details: str = ""

    @property
    def is_success(self) -> bool:
        """Return whether the LP solved to optimality."""
        return self.status == "optimal"


class _Solver(Protocol):
    def available(self) -> bool: ...
    def solve(self, model: ConcreteModel) -> object: ...


def solve_global_recipe_lp(
    package: FactoryDataPackage,
    *,
    solve_mode: GlobalRecipeLpSolveMode = "hard_demand",
) -> GlobalRecipeLpResult:
    """Solve the minimal global recipe LP for a factory data package."""
    model = _build_model(package, solve_mode=solve_mode)
    try:
        solver = _make_solver()
        if (config := getattr(solver, "config", None)) is not None:
            config.load_solution = False
        if not solver.available():
            return _failure("solver_unavailable", "HiGHS solver is not available")
        result = solver.solve(model)
    except (ImportError, ModuleNotFoundError, ApplicationError) as error:
        return _failure(
            "solver_unavailable",
            "HiGHS solver is not available",
            str(error),
        )
    except Exception as error:  # noqa: BLE001
        return _failure("error", "unexpected solver error", repr(error))

    termination = getattr(result, "termination_condition", None)
    if termination != TerminationCondition.optimal:
        return _failure(
            _status_from_termination(termination),
            "solver did not find an optimal solution",
            str(termination),
        )
    if (load_vars := getattr(solver, "load_vars", None)) is not None:
        load_vars()

    return _success(package, model)


def _make_solver() -> _Solver:
    return cast("_Solver", Highs())


def _build_model(
    package: FactoryDataPackage,
    *,
    solve_mode: GlobalRecipeLpSolveMode,
) -> ConcreteModel:
    item_ids = [item.id for item in package.items]
    recipe_ids = [recipe.id for recipe in package.recipes]
    recipe_by_id = {recipe.id: recipe for recipe in package.recipes}

    model = ConcreteModel()
    model.recipe_ids = recipe_ids
    model.item_ids = item_ids
    model.x = Var(recipe_ids, domain=NonNegativeReals)
    model.external_supply = Var(item_ids, domain=NonNegativeReals)
    model.unmet_demand = Var(item_ids, domain=NonNegativeReals)
    model.surplus = Var(item_ids, domain=NonNegativeReals)

    for item_id in item_ids:
        supply = package.external_supplies.get(item_id)
        supply_var = _var(model.external_supply[item_id])
        if supply is None:
            supply_var.fix(0.0)
        elif supply.capacity is not None:
            supply_var.setub(supply.capacity)
        if item_id not in package.final_demands or solve_mode == "hard_demand":
            _var(model.unmet_demand[item_id]).fix(0.0)

    def balance_rule(_model: ConcreteModel, item_id: str) -> object:
        production = sum(
            recipe_by_id[recipe_id].coefficients.get(item_id, 0.0) * model.x[recipe_id]
            for recipe_id in recipe_ids
        )
        return production + model.external_supply[item_id] + model.unmet_demand[
            item_id
        ] - model.surplus[item_id] == package.final_demands.get(item_id, 0.0)

    model.balance = Constraint(item_ids, rule=balance_rule)
    model.objective = Objective(
        expr=(
            _raw_cost(package, model, item_ids)
            + _production_cost(package, model, recipe_ids)  # type: ignore[operator]
            + _unmet_demand_penalty(package, model, item_ids)
        ),
        sense=minimize,
    )
    return model


def _success(package: FactoryDataPackage, model: ConcreteModel) -> GlobalRecipeLpResult:
    item_ids = [item.id for item in package.items]
    recipe_ids = [recipe.id for recipe in package.recipes]
    components = _objective_components(package, model, item_ids, recipe_ids)
    recipe_rates = {recipe_id: _value(model.x[recipe_id]) for recipe_id in recipe_ids}
    external_supplies = {
        item_id: _value(model.external_supply[item_id]) for item_id in item_ids
    }
    unmet_demand = {
        item_id: _value(model.unmet_demand[item_id]) for item_id in item_ids
    }
    surplus = {item_id: _value(model.surplus[item_id]) for item_id in item_ids}
    residuals = _balance_residuals(
        package,
        recipe_rates,
        external_supplies,
        unmet_demand,
        surplus,
    )
    return GlobalRecipeLpResult(
        status="optimal",
        objective_value=sum(components.values()),
        objective_components=components,
        recipe_rates=recipe_rates,
        external_supplies=external_supplies,
        unmet_demand=unmet_demand,
        surplus=surplus,
        balance_residuals=residuals,
        cluster_diagnostics=build_cluster_diagnostics(
            package,
            recipe_rates,
            base_objective_value=sum(components.values()),
        ),
    )


def _objective_components(
    package: FactoryDataPackage,
    model: ConcreteModel,
    item_ids: Sequence[str],
    recipe_ids: Sequence[str],
) -> dict[str, float]:
    return {
        "raw_cost": _value(_raw_cost(package, model, item_ids)),
        "production_cost": _value(_production_cost(package, model, recipe_ids)),
        "flow_cost": 0.0,
        "port_cost": 0.0,
        "cluster_cost": 0.0,
        "duplication_cost": 0.0,
        "unmet_demand_penalty": _value(
            _unmet_demand_penalty(package, model, item_ids),
        ),
    }


def _raw_cost(
    package: FactoryDataPackage,
    model: ConcreteModel,
    item_ids: Sequence[str],
) -> object:
    return sum(
        package.external_supplies[item_id].cost * model.external_supply[item_id]
        for item_id in item_ids
        if item_id in package.external_supplies
    )


def _production_cost(
    package: FactoryDataPackage,
    model: ConcreteModel,
    recipe_ids: Sequence[str],
) -> object:
    recipe_by_id = {recipe.id: recipe for recipe in package.recipes}
    return sum(
        recipe_by_id[recipe_id].production_cost * model.x[recipe_id]
        for recipe_id in recipe_ids
    )


def _unmet_demand_penalty(
    package: FactoryDataPackage,
    model: ConcreteModel,
    item_ids: Sequence[str],
) -> object:
    return sum(
        package.unmet_demand_penalty_rate * model.unmet_demand[item_id]
        for item_id in item_ids
        if item_id in package.final_demands
    )


def _balance_residuals(
    package: FactoryDataPackage,
    recipe_rates: Mapping[str, float],
    external_supplies: Mapping[str, float],
    unmet_demand: Mapping[str, float],
    surplus: Mapping[str, float],
) -> dict[str, float]:
    residuals: dict[str, float] = {}
    for item in package.items:
        produced = sum(
            recipe.coefficients.get(item.id, 0.0) * recipe_rates[recipe.id]
            for recipe in package.recipes
        )
        residuals[item.id] = (
            produced
            + external_supplies[item.id]
            + unmet_demand[item.id]
            - surplus[item.id]
            - package.final_demands.get(item.id, 0.0)
        )
    return residuals


def _status_from_termination(termination: object) -> GlobalRecipeLpStatus:
    if termination == TerminationCondition.infeasible:
        return "infeasible"
    if termination == TerminationCondition.unbounded:
        return "unbounded"
    return "non_optimal"


def _failure(
    status: GlobalRecipeLpStatus,
    message: str,
    details: str = "",
) -> GlobalRecipeLpResult:
    return GlobalRecipeLpResult(
        status=status,
        objective_value=None,
        objective_components=dict.fromkeys(OBJECTIVE_COMPONENT_KEYS, 0.0),
        message=message,
        details=details,
    )


def _value(expression: object) -> float:
    return float(value(expression))


def _var(var_data: object) -> VarData:
    return cast("VarData", var_data)
