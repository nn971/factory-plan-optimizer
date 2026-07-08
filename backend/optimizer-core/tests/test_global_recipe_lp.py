from __future__ import annotations

import pytest
from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
)

from factory_plan_optimizer.optimizer import (
    global_recipe_lp,
    solve_global_recipe_lp,
)

RESIDUAL_TOLERANCE = 1e-7


def _package(
    *,
    recipes: tuple[Recipe, ...] | None = None,
    final_demands: dict[str, float] | None = None,
    external_supplies: dict[str, ExternalSupply] | None = None,
) -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=(Item("iron-ore"), Item("iron-plate")),
        recipes=recipes
        if recipes is not None
        else (
            Recipe(
                id="smelt-iron",
                coefficients={"iron-ore": -1.0, "iron-plate": 1.0},
                production_cost=0.5,
            ),
        ),
        final_demands={"iron-plate": 10.0} if final_demands is None else final_demands,
        external_supplies={"iron-ore": ExternalSupply(cost=1.0)}
        if external_supplies is None
        else external_supplies,
        unmet_demand_penalty_rate=1000.0,
    )


def test_successful_minimal_solve_result_shape_and_values() -> None:
    result = solve_global_recipe_lp(_package())

    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(15.0)
    assert result.recipe_rates["smelt-iron"] == pytest.approx(10.0)
    assert result.external_supplies["iron-ore"] == pytest.approx(10.0)
    assert result.unmet_demand["iron-plate"] == pytest.approx(0.0)
    assert result.surplus["iron-plate"] == pytest.approx(0.0)
    assert all(
        abs(residual) < RESIDUAL_TOLERANCE
        for residual in result.balance_residuals.values()
    )


def test_objective_component_keys_are_always_reported() -> None:
    result = solve_global_recipe_lp(_package())

    assert set(result.objective_components) == set(
        global_recipe_lp.OBJECTIVE_COMPONENT_KEYS,
    )
    assert result.objective_components["raw_cost"] == pytest.approx(10.0)
    assert result.objective_components["production_cost"] == pytest.approx(5.0)
    assert result.objective_components["flow_cost"] == 0.0


def test_hard_demand_is_default_and_reports_infeasible_without_supply() -> None:
    result = solve_global_recipe_lp(
        _package(
            recipes=(),
            external_supplies={},
        ),
    )

    assert result.status == "infeasible"
    assert result.objective_value is None
    assert set(result.objective_components) == set(
        global_recipe_lp.OBJECTIVE_COMPONENT_KEYS,
    )


def test_soft_diagnostics_reports_unmet_demand_without_supply() -> None:
    result = solve_global_recipe_lp(
        _package(
            recipes=(
                Recipe(
                    id="irrelevant",
                    coefficients={"iron-ore": 1.0},
                    production_cost=0.0,
                ),
            ),
            external_supplies={},
        ),
        solve_mode="soft_diagnostics",
    )

    assert result.status == "optimal"
    assert result.unmet_demand["iron-plate"] == pytest.approx(10.0)
    assert result.objective_components["unmet_demand_penalty"] == pytest.approx(10000.0)
    assert set(result.objective_components) == set(
        global_recipe_lp.OBJECTIVE_COMPONENT_KEYS,
    )


def test_solver_unavailable_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableSolver:
        def available(self) -> bool:
            return False

        def solve(self, _model: object) -> object:
            msg = "solve should not be called"
            raise AssertionError(msg)

    monkeypatch.setattr(global_recipe_lp, "_make_solver", UnavailableSolver)

    result = solve_global_recipe_lp(_package())

    assert result.status == "solver_unavailable"
    assert result.objective_value is None
    assert set(result.objective_components) == set(
        global_recipe_lp.OBJECTIVE_COMPONENT_KEYS,
    )


def test_non_optimal_solver_status_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SolverResult:
        termination_condition = global_recipe_lp.TerminationCondition.infeasible

    class InfeasibleSolver:
        def available(self) -> bool:
            return True

        def solve(self, _model: object) -> SolverResult:
            return SolverResult()

    monkeypatch.setattr(global_recipe_lp, "_make_solver", InfeasibleSolver)

    result = solve_global_recipe_lp(_package())

    assert result.status == "infeasible"
    assert result.objective_value is None
    assert "optimal" in result.message
