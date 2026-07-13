from __future__ import annotations

import json

import pytest
from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
)

from factory_plan_optimizer.optimizer.sparse_clustering import (
    SparseClusteringConfig,
    run_sparse_clustering,
)
from factory_plan_optimizer.optimizer.sparse_engines import _refine
from factory_plan_optimizer.optimizer.sparse_graph import build_sparse_graph
from factory_plan_optimizer.optimizer.sparse_partition import (
    PartitionConfig,
    RecipeNetVector,
    cluster_from_recipes,
    score_partition,
)

DEFAULT_BALANCED_REFINEMENT_PASSES = 8
EXTERNAL_INPUT_AND_FINAL_OUTPUT_COUNT = 2


def _pkg(recipes: tuple[Recipe, ...] | None = None) -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=tuple(Item(i) for i in ("ore", "plate", "gear", "science", "trash")),
        recipes=recipes
        or (
            _recipe("mine", {"ore": 1}, 0),
            _recipe("smelt", {"ore": -1, "plate": 1}, 5),
            _recipe("gear", {"plate": -2, "gear": 1}, 10),
            _recipe("science", {"gear": -1, "science": 1}, 20),
        ),
        final_demands={"science": 1},
        external_supplies={"ore": ExternalSupply(cost=1)},
        unmet_demand_penalty_rate=1000,
    )


def _recipe(recipe_id: str, coefficients: dict[str, float], cost: float = 0) -> Recipe:
    return Recipe(
        id=recipe_id,
        coefficients=coefficients,
        energy_required=1,
        ingredients=(),
        results=(),
        production_cost=cost,
    )


def test_producer_consumer_indexing_and_allocation_reconciles() -> None:
    graph = build_sparse_graph(
        _pkg(),
        {"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        min_recipe_rate=1e-9,
        hub_item_top_k=100,
    )
    assert [e.recipe_id for e in graph.producers_by_item["plate"]] == ["smelt"]
    assert [e.recipe_id for e in graph.consumers_by_item["plate"]] == ["gear"]
    plate_edges = [edge for edge in graph.edges if edge.item_id == "plate"]
    assert len(plate_edges) == 1
    assert plate_edges[0].estimated_flow == pytest.approx(2.0)
    assert {edge.item_id for edge in graph.edges} == {"ore", "plate", "gear"}


def test_hybrid_weight_uses_normalized_cost_signal() -> None:
    graph = build_sparse_graph(
        _pkg(),
        {"mine": 1, "smelt": 1},
        min_recipe_rate=0,
        hub_item_top_k=100,
    )
    edge = graph.edges[0]
    assert edge.estimated_flow == pytest.approx(1.0)
    assert edge.edge_weight > edge.estimated_flow
    assert edge.edge_weight <= edge.estimated_flow + 1e-6


def test_hub_cap_summarizes_skipped_edges_without_dense_unrelated_pairs() -> None:
    recipes = tuple(
        [_recipe("p", {"ore": 4})] + [_recipe(f"c{i}", {"ore": -1}) for i in range(4)]
    )
    rates = {"p": 1, **{f"c{i}": 1 for i in range(4)}}
    cap = 2
    candidate_count = 4
    graph = build_sparse_graph(
        _pkg(recipes),
        rates,
        min_recipe_rate=0,
        hub_item_top_k=cap,
    )
    assert len(graph.edges) == cap
    assert graph.total_candidate_edges == candidate_count
    assert graph.hub_summaries[0].skipped_count == candidate_count - cap
    assert graph.hub_summaries[0].skipped_estimated_flow == pytest.approx(2.0)


def test_high_degree_hub_keeps_only_capped_edges() -> None:
    producer_count = 30
    consumer_count = 40
    cap = 7
    recipes = tuple(
        [_recipe(f"p{i}", {"ore": 1}) for i in range(producer_count)]
        + [_recipe(f"c{i}", {"ore": -1}) for i in range(consumer_count)]
    )
    rates = {
        **{f"p{i}": 1.0 for i in range(producer_count)},
        **{f"c{i}": 1.0 for i in range(consumer_count)},
    }

    graph = build_sparse_graph(
        _pkg(recipes),
        rates,
        min_recipe_rate=0,
        hub_item_top_k=cap,
    )

    assert len(graph.edges) == cap
    assert graph.total_candidate_edges == producer_count * consumer_count
    assert graph.hub_summaries[0].skipped_count == producer_count * consumer_count - cap


def test_boundary_external_ports_and_surplus_unmet_are_separate() -> None:
    result = run_sparse_clustering(
        _pkg(),
        recipe_rates={"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        external_supplies={"ore": 1},
        surplus={"trash": 3},
        unmet_demand={"science": 0.5},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=2),
    )
    assert result["status"] == "success"
    ports = result["boundary_port_types"]["items"]
    assert any(
        port["direction"] == "output" and port["item_id"] == "science" for port in ports
    )
    external_ports = result["external_boundary_port_types"]["items"]
    assert any(
        port["direction"] == "input" and port["item_id"] == "ore"
        for port in external_ports
    )
    assert result["boundary_port_type_count"] == result["net_port_count"]
    assert result["port_aware_objective"]["net_port_count"] == result["net_port_count"]
    summary = result["surplus_unmet_summary"]["items"]
    assert {row["item_id"] for row in summary} == {"science", "trash"}


def _assignments(result: dict[str, object]) -> dict[str, int]:
    rows = result["recipe_assignments"]["items"]  # type: ignore[index]
    return {row["recipe_id"]: row["cluster_id"] for row in rows}  # type: ignore[index]


def test_deterministic_output_and_balanced_refinement() -> None:
    kwargs = {
        "recipe_rates": {"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        "external_supplies": {},
    }
    cfg = SparseClusteringConfig(enabled=True, mode="balanced", target_cluster_count=2)
    first = run_sparse_clustering(_pkg(), **kwargs, config=cfg)
    second = run_sparse_clustering(_pkg(), **kwargs, config=cfg)
    assert first == second
    assert first["engine"] == "port-aware-seeded-refinement"
    assert first["fallback"] is None
    assert first["fallback_attempted"] is False
    assert (
        first["port_aware_objective"]["refinement_passes"]
        <= DEFAULT_BALANCED_REFINEMENT_PASSES
    )


def test_fast_uses_one_refinement_pass_and_balanced_defaults_to_more() -> None:
    kwargs = {
        "recipe_rates": {"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        "external_supplies": {},
    }

    fast = run_sparse_clustering(
        _pkg(),
        **kwargs,
        config=SparseClusteringConfig(
            enabled=True,
            mode="fast",
            target_cluster_count=2,
        ),
    )
    balanced = run_sparse_clustering(
        _pkg(),
        **kwargs,
        config=SparseClusteringConfig(
            enabled=True,
            mode="balanced",
            target_cluster_count=2,
        ),
    )

    assert fast["port_aware_objective"]["refinement_passes"] <= 1
    assert balanced["effective_config"]["max_refinement_passes"] is None
    assert (
        balanced["port_aware_objective"]["refinement_passes"]
        <= DEFAULT_BALANCED_REFINEMENT_PASSES
    )


def test_port_canceling_recipes_prefer_same_cluster() -> None:
    recipes = (
        _recipe("consumer", {"ore": -5}),
        _recipe("producer", {"ore": 5}),
        _recipe("water", {"trash": 1}),
    )
    result = run_sparse_clustering(
        _pkg(recipes),
        recipe_rates={"producer": 1, "consumer": 1, "water": 1},
        external_supplies={},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=2),
    )

    assignments = _assignments(result)
    assert assignments["producer"] == assignments["consumer"]


def test_size_penalty_avoids_strongest_edge_giant_cluster_regression() -> None:
    recipes = (
        _recipe("p1", {"ore": 10}),
        _recipe("c1", {"ore": -10}),
        _recipe("p2", {"plate": 1}),
        _recipe("c2", {"plate": -1}),
    )
    result = run_sparse_clustering(
        _pkg(recipes),
        recipe_rates={"p1": 1, "c1": 1, "p2": 1, "c2": 1},
        external_supplies={},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=2),
    )

    sizes = sorted(row["recipe_count"] for row in result["cluster_summaries"]["items"])
    assert sizes == [2, 2]


def test_local_refinement_reduces_objective_on_crafted_case() -> None:
    vectors = {
        "consumer": RecipeNetVector("consumer", 1, {"ore": -5}),
        "other": RecipeNetVector("other", 1, {"plate": 2}),
        "producer": RecipeNetVector("producer", 1, {"ore": 5}),
    }
    clusters = [
        cluster_from_recipes((vectors["consumer"], vectors["other"])),
        cluster_from_recipes((vectors["producer"],)),
    ]
    assignments = {"consumer": 0, "other": 0, "producer": 1}
    config = PartitionConfig(target_k=2, active_recipe_count=3)

    before = score_partition(clusters, config)
    passes = _refine(
        vectors,
        clusters,
        assignments,
        {},
        config,
        max_passes=1,
        deadline=float("inf"),
    )
    after = score_partition(clusters, config)

    assert passes == 1
    assert after.total_score < before.total_score


def test_exact_small_unsupported_disabled_and_no_active_dispatch() -> None:
    assert (
        run_sparse_clustering(
            _pkg(),
            recipe_rates={},
            external_supplies={},
            config=SparseClusteringConfig(),
        )["status"]
        == "skipped"
    )
    assert (
        run_sparse_clustering(
            _pkg(),
            recipe_rates={},
            external_supplies={},
            config=SparseClusteringConfig(enabled=True),
        )["status"]
        == "skipped"
    )
    assert (
        run_sparse_clustering(
            _pkg(),
            recipe_rates={},
            external_supplies={},
            config=SparseClusteringConfig(enabled=True, mode="exact-small"),
        )["status"]
        == "unsupported"
    )


@pytest.mark.parametrize(
    "config",
    [
        SparseClusteringConfig(enabled=True, target_cluster_count=0),
        SparseClusteringConfig(enabled=True, min_cluster_count=3, max_cluster_count=2),
        SparseClusteringConfig(
            enabled=True,
            min_cluster_count=3,
            target_cluster_count=2,
        ),
        SparseClusteringConfig(
            enabled=True,
            max_cluster_count=1,
            target_cluster_count=2,
        ),
        SparseClusteringConfig(enabled=True, hub_item_top_k=0),
        SparseClusteringConfig(enabled=True, max_runtime_seconds=0),
        SparseClusteringConfig(enabled=True, max_runtime_seconds=float("inf")),
        SparseClusteringConfig(enabled=True, min_recipe_rate=float("nan")),
        SparseClusteringConfig(enabled=True, result_caps={"recipe_assignments": -1}),
        SparseClusteringConfig(
            enabled=True,
            result_caps={"recipe_assignments": 1.5},  # type: ignore[dict-item]
        ),
        SparseClusteringConfig(enabled=True, result_caps={"unknown": 1}),
    ],
)
def test_config_validation(config: SparseClusteringConfig) -> None:
    with pytest.raises(ValueError, match=r"."):
        config.validate()


def test_result_caps_truncate() -> None:
    result = run_sparse_clustering(
        _pkg(),
        recipe_rates={"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        external_supplies={},
        config=SparseClusteringConfig(
            enabled=True,
            result_caps={"recipe_assignments": 2, "cluster_summaries": 1},
        ),
    )
    assert result["recipe_assignments"]["truncated"] is True
    assert result["recipe_assignments"]["total_count"] == len(
        {"mine", "smelt", "gear", "science"},
    )
    assert result["cluster_summaries"]["truncated"] is True
    assert any("recipe_assignments truncated" in text for text in result["warnings"])


def test_api_ready_counts_and_external_port_deduplication() -> None:
    recipes = (
        _recipe("p", {"ore": 3}),
        _recipe("c1", {"ore": -1}),
        _recipe("c2", {"ore": -1}),
    )
    result = run_sparse_clustering(
        _pkg(recipes),
        recipe_rates={"p": 1, "c1": 1, "c2": 1},
        external_supplies={"ore": 5},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=1),
    )

    assert result["optimization_effect"] == "none"
    assert result["graph_statistics"]["active_item_count"] == 1
    assert result["graph_statistics"]["skipped_hub_edge_count"] == 0
    assert result["boundary_port_type_count"] == 1
    assert result["net_port_count"] == 1
    assert result["external_boundary_port_type_count"] == 1
    external_rows = result["external_boundary_port_types"]["items"]
    assert external_rows == [
        {"cluster_id": 0, "item_id": "ore", "direction": "input", "amount": 5},
    ]


def test_external_and_final_diagnostics_do_not_change_net_port_count() -> None:
    recipes = (_recipe("p", {"ore": 1}), _recipe("c", {"ore": -1}))
    base = run_sparse_clustering(
        _pkg(recipes),
        recipe_rates={"p": 1, "c": 1},
        external_supplies={},
        final_demands={},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=1),
    )
    with_external = run_sparse_clustering(
        _pkg(recipes),
        recipe_rates={"p": 1, "c": 1},
        external_supplies={"ore": 10},
        final_demands={"ore": 10},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=1),
    )

    assert base["net_port_count"] == 0
    assert with_external["net_port_count"] == 0
    assert with_external["boundary_port_type_count"] == 0
    assert (
        with_external["external_boundary_port_type_count"]
        == EXTERNAL_INPUT_AND_FINAL_OUTPUT_COUNT
    )


def test_objective_components_match_net_port_diagnostics_and_json() -> None:
    result = run_sparse_clustering(
        _pkg(),
        recipe_rates={"mine": 2, "smelt": 2, "gear": 1, "science": 1},
        external_supplies={},
        config=SparseClusteringConfig(enabled=True, target_cluster_count=2),
    )
    objective = result["port_aware_objective"]

    assert set(objective) >= {
        "port_cost",
        "size_penalty",
        "flow_cost",
        "total_score",
        "net_port_count",
    }
    assert result["boundary_port_type_count"] == objective["net_port_count"]
    assert result["net_port_count"] == objective["net_port_count"]
    assert (
        sum(row["net_port_count"] for row in result["cluster_summaries"]["items"])
        == result["net_port_count"]
    )
    json.dumps(result)
