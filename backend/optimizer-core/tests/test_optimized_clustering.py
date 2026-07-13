from __future__ import annotations

import pytest
from game_data_extractor.data_contracts import (
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
)
from pyomo.contrib.appsi.base import TerminationCondition

from factory_plan_optimizer.optimizer import optimized_clustering
from factory_plan_optimizer.optimizer.optimized_clustering import (
    BALANCED_PARAMETERS,
    DEFAULT_REPORTING_EPSILON,
    DEFAULT_TIME_LIMIT_SECONDS,
    MAX_MODEL_SIZE_SCORE,
    MODES,
    PRESETS,
    STATUSES,
    OptimizedClusteringParameters,
    empty_result,
    optimize_clustering,
    reconcile_objective_breakdown,
    resolve_parameters,
    validate_parameters,
)


def _recipe(recipe_id: str, coefficients: dict[str, float]) -> Recipe:
    return Recipe(
        id=recipe_id,
        coefficients=coefficients,
        energy_required=1.0,
        ingredients=(),
        results=(),
        production_cost=0.0,
    )


def _package() -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version="factory-data-v2",
        items=[Item("ore"), Item("plate"), Item("gear")],
        recipes=[
            _recipe("smelt", {"ore": -1.0, "plate": 1.0}),
            _recipe("gear", {"plate": -2.0, "gear": 1.0}),
        ],
        final_demands={"gear": 1.0},
        external_supplies={"ore": ExternalSupply(cost=1.0)},
        unmet_demand_penalty_rate=1000.0,
    )


def _tiny_external_package() -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version="factory-data-v2",
        items=[Item("main"), Item("dust")],
        recipes=[_recipe("make-main", {"main": 1.0, "dust": 0.001})],
        final_demands={"main": 1.0},
        external_supplies={},
        unmet_demand_penalty_rate=1000.0,
    )


def _package_with_irrelevant_items(count: int) -> FactoryDataPackage:
    base = _package()
    return FactoryDataPackage(
        schema_version=base.schema_version,
        items=[*base.items, *(Item(f"unused-{index}") for index in range(count))],
        recipes=base.recipes,
        final_demands=base.final_demands,
        external_supplies=base.external_supplies,
        unmet_demand_penalty_rate=base.unmet_demand_penalty_rate,
    )


def _split_pressure_package() -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version="factory-data-v2",
        items=[Item("big"), Item("tiny")],
        recipes=[
            _recipe("make-big", {"big": 1.0}),
            _recipe("make-tiny", {"tiny": 1.0}),
        ],
        final_demands={},
        external_supplies={},
        unmet_demand_penalty_rate=1000.0,
    )


class _FakeTimeoutResult:
    termination_condition = TerminationCondition.maxTimeLimit


class _FakeTimeoutSolver:
    config: object | None = None

    def available(self) -> bool:
        return True

    def solve(self, _model: object) -> _FakeTimeoutResult:
        return _FakeTimeoutResult()


def _make_fake_timeout_solver() -> _FakeTimeoutSolver:
    return _FakeTimeoutSolver()


def test_status_mode_and_preset_vocabularies() -> None:
    assert MODES == ("continuous_split",)
    assert PRESETS == ("balanced", "fewer_ports", "even_size")
    assert STATUSES == (
        "disabled",
        "no_active_recipes",
        "optimal",
        "feasible_non_optimal",
        "timeout_no_incumbent",
        "infeasible",
        "solver_unavailable",
        "model_too_large",
    )


def test_default_model_size_guardrail_allows_target_phase2_size() -> None:
    assert MAX_MODEL_SIZE_SCORE > 50 * 50 * 60 * 4


def test_resolve_balanced_parameters_uses_diagnostic_baseline() -> None:
    effective = resolve_parameters(OptimizedClusteringParameters(enabled=True))

    assert effective.enabled is True
    assert effective.mode == "continuous_split"
    assert effective.preset == "balanced"
    assert effective.preset_is_provisional is False
    assert (
        effective.flow_cost_per_quantity == BALANCED_PARAMETERS.flow_cost_per_quantity
    )
    assert (
        effective.port_cost_per_item_type == BALANCED_PARAMETERS.port_cost_per_item_type
    )
    assert (
        effective.cluster_size_penalty_weight
        == BALANCED_PARAMETERS.cluster_size_penalty_weight
    )
    assert effective.min_cluster_size == BALANCED_PARAMETERS.min_cluster_size
    assert effective.max_cluster_size == BALANCED_PARAMETERS.max_cluster_size
    assert effective.reporting_epsilon == DEFAULT_REPORTING_EPSILON
    assert effective.time_limit_seconds == DEFAULT_TIME_LIMIT_SECONDS
    assert effective.allow_recipe_splitting is False
    assert effective.splittable_recipe_ids == ()


def test_non_balanced_presets_are_provisional_and_report_effective_parameters() -> None:
    fewer_ports = resolve_parameters(
        OptimizedClusteringParameters(preset="fewer_ports"),
    )
    even_size = resolve_parameters(OptimizedClusteringParameters(preset="even_size"))

    assert fewer_ports.preset_is_provisional is True
    assert (
        fewer_ports.port_cost_per_item_type
        > BALANCED_PARAMETERS.port_cost_per_item_type
    )
    assert fewer_ports.to_dict()["preset"] == "fewer_ports"
    assert even_size.preset_is_provisional is True
    assert (
        even_size.cluster_size_penalty_weight
        > BALANCED_PARAMETERS.cluster_size_penalty_weight
    )
    assert even_size.to_dict()["preset"] == "even_size"


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (OptimizedClusteringParameters(enabled=1), "enabled"),  # type: ignore[arg-type]
        (OptimizedClusteringParameters(mode="bad"), "mode"),
        (OptimizedClusteringParameters(preset="bad"), "preset"),
        (
            OptimizedClusteringParameters(max_cluster_size_constraint="bad"),
            "max cluster size constraint",
        ),
        (OptimizedClusteringParameters(flow_cost_per_quantity=-1.0), "flow"),
        (OptimizedClusteringParameters(port_cost_per_item_type=-1.0), "port"),
        (OptimizedClusteringParameters(cluster_size_penalty_weight=-1.0), "size"),
        (OptimizedClusteringParameters(flow_cost_per_quantity=float("nan")), "finite"),
        (OptimizedClusteringParameters(min_cluster_size=-1.0), "min_cluster_size"),
        (OptimizedClusteringParameters(max_cluster_size=-1.0), "max_cluster_size"),
        (OptimizedClusteringParameters(max_cluster_size=0.0), "max_cluster_size"),
        (
            OptimizedClusteringParameters(min_cluster_size=2.0, max_cluster_size=1.0),
            "min_cluster_size",
        ),
        (OptimizedClusteringParameters(reporting_epsilon=1e-10), "reporting_epsilon"),
        (OptimizedClusteringParameters(reporting_epsilon=1e-1), "reporting_epsilon"),
        (OptimizedClusteringParameters(time_limit_seconds=0.0), "time_limit_seconds"),
        (OptimizedClusteringParameters(time_limit_seconds=601.0), "time_limit_seconds"),
        (OptimizedClusteringParameters(time_limit_seconds=float("inf")), "finite"),
    ],
)
def test_validate_parameters_rejects_invalid_values(
    parameters: OptimizedClusteringParameters,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_parameters(parameters)


def test_empty_result_uses_optimized_field_names_and_zero_costs() -> None:
    result = empty_result()

    assert result["status"] == "no_active_recipes"
    assert result["objective_value"] == 0.0
    assert result["clusters"] == []
    assert result["objective_components"] == {
        "flow_cost": 0.0,
        "port_cost": 0.0,
        "cluster_size_penalty": 0.0,
        "duplication_cost": 0.0,
    }
    assert result["cost_breakdown"] == {
        "inter_cluster_flow_cost": 0.0,
        "external_flow_cost": 0.0,
        "inter_cluster_port_cost": 0.0,
        "external_port_cost": 0.0,
        "cluster_size_penalty": 0.0,
        "duplication_cost": 0.0,
    }
    assert result["reconciliation"]["reconciled"] is True


def test_reconcile_objective_breakdown_reports_match_and_mismatch() -> None:
    matched = reconcile_objective_breakdown(
        {
            "flow_cost": 3.0,
            "port_cost": 5.0,
            "cluster_size_penalty": 7.0,
            "duplication_cost": 11.0,
        },
        {
            "inter_cluster_flow_cost": 1.0,
            "external_flow_cost": 2.0,
            "inter_cluster_port_cost": 3.0,
            "external_port_cost": 2.0,
            "cluster_size_penalty": 7.0,
            "duplication_cost": 11.0,
        },
    )
    mismatched = reconcile_objective_breakdown(
        {"flow_cost": 1.0},
        {"inter_cluster_flow_cost": 2.0},
    )

    assert matched["reconciled"] is True
    assert matched["difference"] == 0.0
    assert mismatched["reconciled"] is False
    assert mismatched["difference"] == -1.0


def test_optimize_clustering_conserves_allocations_and_reports_costs() -> None:
    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 1.0},
        external_supplies={"ore": 2.0},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=0.0,
            max_cluster_size=10.0,
        ),
    )

    assert result["status"] == "optimal"
    totals = {"smelt": 0.0, "gear": 0.0}
    for allocation in result["allocations"]:
        totals[allocation["recipe_id"]] += allocation["rate"]
    assert totals == pytest.approx({"smelt": 2.0, "gear": 1.0})
    assert {allocation["recipe_id"] for allocation in result["allocations"]} == {
        "smelt",
        "gear",
    }
    assert all(
        len(
            [
                allocation
                for allocation in result["allocations"]
                if allocation["recipe_id"] == recipe_id
            ],
        )
        == 1
        for recipe_id in ("smelt", "gear")
    )
    assert result["external_flows"]
    assert all(
        row["boundary_label"] == "aggregate_external_balance"
        for row in result["external_flows"]
    )
    assert result["objective_components"]["duplication_cost"] == 0.0
    assert result["reconciliation"]["reconciled"] is True
    assert result["objective_value"] == pytest.approx(
        sum(result["objective_components"].values()),
    )


def test_optimize_clustering_unused_clusters_are_trimmed_from_report() -> None:
    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 0.0},
        external_supplies={"ore": 2.0},
        surplus={"plate": 2.0},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=5.0,
            max_cluster_size=10.0,
        ),
    )

    assert result["status"] == "optimal"
    assert len(result["clusters"]) == 1
    assert all(cluster["used"] for cluster in result["clusters"])
    assert result["objective_components"]["cluster_size_penalty"] == pytest.approx(30.0)


def test_allowlisted_recipe_can_split() -> None:
    result = optimize_clustering(
        _split_pressure_package(),
        {"make-big": 10.0, "make-tiny": 0.01},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=0.0,
            max_cluster_size=6.0,
            flow_cost_per_quantity=0.0,
            port_cost_per_item_type=0.0,
            cluster_size_penalty_weight=1000.0,
            splittable_recipe_ids=("make-big",),
        ),
    )

    big_allocations = [
        allocation
        for allocation in result["allocations"]
        if allocation["recipe_id"] == "make-big"
    ]
    assert result["status"] == "optimal"
    assert len(big_allocations) > 1


def test_default_no_split_blocks_same_constructed_split() -> None:
    result = optimize_clustering(
        _split_pressure_package(),
        {"make-big": 10.0, "make-tiny": 0.01},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=0.0,
            max_cluster_size=6.0,
            flow_cost_per_quantity=0.0,
            port_cost_per_item_type=0.0,
            cluster_size_penalty_weight=1000.0,
        ),
    )

    big_allocations = [
        allocation
        for allocation in result["allocations"]
        if allocation["recipe_id"] == "make-big"
    ]
    assert result["status"] == "optimal"
    assert len(big_allocations) == 1


def test_hard_max_cluster_size_prevents_over_max_reported_cluster() -> None:
    max_cluster_size = 6.0
    result = optimize_clustering(
        _split_pressure_package(),
        {"make-big": 10.0, "make-tiny": 0.01},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            allow_recipe_splitting=True,
            min_cluster_size=0.0,
            max_cluster_size=max_cluster_size,
            max_cluster_size_constraint="hard",
            flow_cost_per_quantity=0.0,
            port_cost_per_item_type=0.0,
            cluster_size_penalty_weight=1000.0,
        ),
    )

    assert result["status"] == "optimal"
    assert all(cluster["size"] <= max_cluster_size for cluster in result["clusters"])
    assert all(
        cluster["over_max"] == pytest.approx(0.0) for cluster in result["clusters"]
    )


def test_optimize_clustering_model_too_large_guardrail() -> None:
    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 1.0},
        parameters=OptimizedClusteringParameters(enabled=True),
        max_model_size_score=1,
    )

    assert result["status"] == "model_too_large"
    assert result["clusters"] == []
    assert result["model_size"]["active_recipes"] == len({"smelt", "gear"})


def test_irrelevant_package_items_do_not_trigger_model_too_large() -> None:
    result = optimize_clustering(
        _package_with_irrelevant_items(1000),
        {"smelt": 2.0, "gear": 1.0},
        parameters=OptimizedClusteringParameters(enabled=True),
        max_model_size_score=2 * 2 * 3 * 4,
    )

    assert result["status"] == "optimal"


def test_reporting_epsilon_hides_rows_but_not_cost_components() -> None:
    result = optimize_clustering(
        _tiny_external_package(),
        {"make-main": 1.0},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=0.0,
            max_cluster_size=10.0,
            reporting_epsilon=1e-2,
        ),
    )

    assert result["status"] == "optimal"
    assert all(row["item_id"] != "dust" for row in result["external_flows"])
    assert result["cost_breakdown"]["external_flow_cost"] == pytest.approx(1.0)
    assert result["reconciliation"]["reconciled"] is True
    assert result["objective_reconciliation"]["objective_value"] == pytest.approx(
        result["objective_value"],
    )
    reported_component_total = result["objective_reconciliation"][
        "reported_component_total"
    ]
    assert reported_component_total == pytest.approx(
        sum(result["objective_components"].values()),
    )


def test_external_port_breakdown_reconciles_with_objective() -> None:
    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 1.0},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=1.5,
            max_cluster_size=2.0,
            flow_cost_per_quantity=0.0,
            port_cost_per_item_type=1.0,
            cluster_size_penalty_weight=1000.0,
        ),
    )

    assert result["status"] == "optimal"
    assert result["external_flows"]
    assert result["cost_breakdown"]["external_port_cost"] > 0.0
    assert result["objective_components"]["port_cost"] == pytest.approx(
        result["cost_breakdown"]["inter_cluster_port_cost"]
        + result["cost_breakdown"]["external_port_cost"],
    )
    assert result["objective_value"] == pytest.approx(
        sum(result["objective_components"].values()),
    )


def test_timeout_without_loadable_incumbent_reports_no_clusters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        optimized_clustering,
        "_make_solver",
        _make_fake_timeout_solver,
    )

    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 1.0},
        parameters=OptimizedClusteringParameters(enabled=True),
    )

    assert result["status"] == "timeout_no_incumbent"
    assert result["clusters"] == []


def test_zero_size_binary_slot_is_not_reported_used() -> None:
    result = optimize_clustering(
        _package(),
        {"smelt": 2.0, "gear": 0.0},
        parameters=OptimizedClusteringParameters(
            enabled=True,
            min_cluster_size=0.0,
            max_cluster_size=10.0,
            cluster_size_penalty_weight=0.0,
        ),
    )

    assert result["status"] == "optimal"
    assert all(
        cluster["used"] is False
        for cluster in result["clusters"]
        if cluster["size"] <= result["effective_parameters"]["reporting_epsilon"]
    )
