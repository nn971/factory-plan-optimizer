from __future__ import annotations

import json

import pytest
from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
    RecipeTerm,
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
                energy_required=3.2,
                ingredients=(RecipeTerm(type="unknown", name="iron-ore", amount=1.0),),
                results=(RecipeTerm(type="unknown", name="iron-plate", amount=1.0),),
                production_cost=0.5,
            ),
        ),
        final_demands={"iron-plate": 10.0} if final_demands is None else final_demands,
        external_supplies={"iron-ore": ExternalSupply(cost=1.0)}
        if external_supplies is None
        else external_supplies,
        unmet_demand_penalty_rate=1000.0,
    )


def _cluster_package() -> FactoryDataPackage:
    items = tuple(
        Item(item_id) for item_id in ("ore", "plate", "gear", "wire", "circuit")
    )
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=items,
        recipes=(
            Recipe(
                id="smelt-plate",
                coefficients={"ore": -1.0, "plate": 1.0},
                energy_required=1.0,
                ingredients=(RecipeTerm(type="unknown", name="ore", amount=1.0),),
                results=(RecipeTerm(type="unknown", name="plate", amount=1.0),),
                production_cost=0.0,
                category="smelting",
            ),
            Recipe(
                id="make-gear",
                coefficients={"plate": -1.0, "gear": 1.0},
                energy_required=1.0,
                ingredients=(RecipeTerm(type="unknown", name="plate", amount=1.0),),
                results=(RecipeTerm(type="unknown", name="gear", amount=1.0),),
                production_cost=0.0,
                category="crafting",
            ),
            Recipe(
                id="make-wire",
                coefficients={"plate": -1.0, "wire": 2.0},
                energy_required=1.0,
                ingredients=(RecipeTerm(type="unknown", name="plate", amount=1.0),),
                results=(RecipeTerm(type="unknown", name="wire", amount=2.0),),
                production_cost=0.0,
                category="crafting",
            ),
            Recipe(
                id="make-circuit",
                coefficients={"gear": -1.0, "wire": -2.0, "circuit": 1.0},
                energy_required=1.0,
                ingredients=(
                    RecipeTerm(type="unknown", name="gear", amount=1.0),
                    RecipeTerm(type="unknown", name="wire", amount=2.0),
                ),
                results=(RecipeTerm(type="unknown", name="circuit", amount=1.0),),
                production_cost=0.0,
                category="crafting",
            ),
            Recipe(
                id="inactive-output",
                coefficients={"ore": -1.0, "gear": 1.0},
                energy_required=1.0,
                ingredients=(RecipeTerm(type="unknown", name="ore", amount=1.0),),
                results=(RecipeTerm(type="unknown", name="gear", amount=1.0),),
                production_cost=10.0,
                category="crafting",
            ),
        ),
        final_demands={"circuit": 10.0},
        external_supplies={"ore": ExternalSupply(cost=0.0)},
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
                    energy_required=1.0,
                    ingredients=(),
                    results=(RecipeTerm(type="unknown", name="iron-ore", amount=1.0),),
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
    assert result.cluster_diagnostics["clusters"] == []
    assert "cost_defaults" in result.cluster_diagnostics


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


def test_cluster_diagnostics_are_active_only_and_do_not_change_objective() -> None:
    result = solve_global_recipe_lp(_cluster_package())

    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(
        sum(result.objective_components.values()),
    )
    assert result.objective_components["flow_cost"] == 0.0
    assert result.objective_components["port_cost"] == 0.0
    assert result.objective_components["cluster_cost"] == 0.0
    assert result.objective_components["duplication_cost"] == 0.0
    assert result.cluster_diagnostics["base_objective_value"] == pytest.approx(
        result.objective_value,
    )
    assert result.cluster_diagnostics[
        "combined_diagnostic_objective_value"
    ] == pytest.approx(
        result.objective_value + result.cluster_diagnostics["diagnostic_total"],
    )
    assert "inactive-output" not in {
        recipe_id
        for cluster in result.cluster_diagnostics["clusters"]  # type: ignore[index]
        for recipe_id in cluster["recipe_ids"]
    }
    json.dumps(result.cluster_diagnostics)


def test_category_first_direct_link_clusters_and_zero_net_rows() -> None:
    result = solve_global_recipe_lp(_cluster_package())
    clusters = result.cluster_diagnostics["clusters"]  # type: ignore[index]

    assert [cluster["recipe_ids"] for cluster in clusters] == [
        ["make-circuit", "make-gear", "make-wire"],
        ["smelt-plate"],
    ]
    crafting = clusters[0]
    assert crafting["label"] == "crafting: wire"
    zero_rows = [row for row in crafting["boundary_items"] if row["quantity"] == 0.0]
    assert {row["item_id"] for row in zero_rows} == {"gear", "wire"}
    assert all(row["is_zero_net"] for row in zero_rows)
    assert all(row["flow_cost"] == 0.0 and row["port_cost"] == 0.0 for row in zero_rows)


def test_cluster_diagnostic_components_reconcile_and_size_penalty_present() -> None:
    result = solve_global_recipe_lp(_cluster_package())
    diagnostics = result.cluster_diagnostics
    clusters = diagnostics["clusters"]  # type: ignore[index]
    global_components = diagnostics["diagnostic_components"]  # type: ignore[index]

    for key in ("flow_cost", "port_cost", "cluster_cost", "duplication_cost"):
        assert global_components[key] == pytest.approx(
            sum(cluster["diagnostic_components"][key] for cluster in clusters),
        )
    assert diagnostics["diagnostic_total"] == pytest.approx(
        sum(global_components.values()),
    )  # type: ignore[union-attr]
    assert global_components["cluster_cost"] > 0.0
    assert global_components["port_cost"] > global_components["flow_cost"]


def test_cross_cluster_flow_and_port_costs_are_split_without_double_counting() -> None:
    result = solve_global_recipe_lp(_cluster_package())
    clusters = result.cluster_diagnostics["clusters"]  # type: ignore[index]
    smelting = clusters[1]
    crafting = clusters[0]
    smelting_plate = next(
        row for row in smelting["boundary_items"] if row["item_id"] == "plate"
    )
    crafting_plate = next(
        row for row in crafting["boundary_items"] if row["item_id"] == "plate"
    )
    global_components = result.cluster_diagnostics["diagnostic_components"]  # type: ignore[index]

    assert smelting_plate["flow_cost"] == pytest.approx(10.0)
    assert crafting_plate["flow_cost"] == pytest.approx(10.0)
    assert smelting_plate["port_cost"] == pytest.approx(50.0)
    assert crafting_plate["port_cost"] == pytest.approx(50.0)
    assert global_components["flow_cost"] == pytest.approx(50.0)
    assert global_components["port_cost"] == pytest.approx(300.0)


def test_failure_results_have_empty_cluster_diagnostics() -> None:
    result = solve_global_recipe_lp(_package(recipes=(), external_supplies={}))

    assert result.status == "infeasible"
    assert result.cluster_diagnostics == {}
