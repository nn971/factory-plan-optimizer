from __future__ import annotations

import pytest
from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    FactoryDataPackage,
    Item,
    Recipe,
)

from factory_plan_optimizer.optimizer.sparse_partition import (
    ClusterState,
    ObjectiveComponents,
    ObjectiveWeights,
    PartitionConfig,
    RecipeNetVector,
    add_recipe_delta,
    build_recipe_net_vectors,
    cluster_from_recipes,
    move_recipe_delta,
    net_port_count,
    net_port_direction,
    remove_recipe_delta,
    score_cluster,
    score_partition,
    size_penalty,
)


def _recipe(recipe_id: str, coefficients: dict[str, float]) -> Recipe:
    return Recipe(
        id=recipe_id,
        coefficients=coefficients,
        energy_required=1,
        ingredients=(),
        results=(),
        production_cost=0,
    )


def _pkg(recipes: tuple[Recipe, ...]) -> FactoryDataPackage:
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=tuple(Item(item_id) for item_id in ("ore", "plate", "gear")),
        recipes=recipes,
        final_demands={},
        external_supplies={},
        unmet_demand_penalty_rate=1000,
    )


def _components_tuple(
    score: ObjectiveComponents,
) -> tuple[float, float, float, float, int]:
    return (
        score.port_cost,
        score.size_penalty,
        score.flow_cost,
        score.total_score,
        score.net_port_count,
    )


def test_recipe_net_vectors_are_coefficient_times_rate() -> None:
    vectors = build_recipe_net_vectors(
        _pkg(
            (
                _recipe("mine", {"ore": 2}),
                _recipe("smelt", {"ore": -1, "plate": 1}),
                _recipe("idle", {"gear": 1}),
            ),
        ),
        {"mine": 3, "smelt": 2, "idle": 0},
    )

    assert set(vectors) == {"mine", "smelt"}
    assert vectors["mine"].item_net == {"ore": 6}
    assert vectors["smelt"].item_net == {"ore": -2, "plate": 2}


def test_port_cancellation_reduces_net_port_count() -> None:
    cluster = cluster_from_recipes(
        (
            RecipeNetVector("producer", 1, {"plate": 5}),
            RecipeNetVector("consumer", 1, {"plate": -5}),
        ),
    )

    assert net_port_count({"plate": 5}, port_epsilon=1e-9) == 1
    assert (
        score_cluster(
            cluster, PartitionConfig(target_k=2, active_recipe_count=4)
        ).net_port_count
        == 0
    )


def test_surplus_net_output_counts_as_output_port() -> None:
    cluster = cluster_from_recipes((RecipeNetVector("producer", 1, {"gear": 2}),))

    assert net_port_direction(cluster.item_net["gear"], 1e-9) == "output"
    assert (
        score_cluster(
            cluster, PartitionConfig(target_k=2, active_recipe_count=4)
        ).net_port_count
        == 1
    )


def test_epsilon_behavior_around_zero_net() -> None:
    epsilon = 0.1

    assert net_port_direction(epsilon, epsilon) is None
    assert net_port_direction(-epsilon, epsilon) is None
    assert net_port_direction(epsilon + 0.001, epsilon) == "output"
    assert net_port_direction(-epsilon - 0.001, epsilon) == "input"


def test_size_penalty_formula() -> None:
    config = PartitionConfig(
        target_k=2,
        active_recipe_count=10,
        min_cluster_size_ratio=0.8,
        max_cluster_size_ratio=1.2,
    )

    assert config.target_size == pytest.approx(5)
    assert size_penalty(3, config) == pytest.approx(1)  # (4 - 3)^2
    assert size_penalty(5, config) == pytest.approx(0)
    assert size_penalty(8, config) == pytest.approx(4)  # (8 - 6)^2


def test_objective_components_sum_correctly() -> None:
    config = PartitionConfig(
        target_k=2,
        active_recipe_count=4,
        weights=ObjectiveWeights(
            port_cost_weight=100,
            size_penalty_weight=10,
            flow_cost_weight=0.5,
        ),
    )
    cluster = ClusterState({"r1"}, {"ore": -3, "plate": 2}, 1)

    score = score_cluster(cluster, config)

    expected_port_count = 2
    assert score.net_port_count == expected_port_count
    assert score.port_cost == pytest.approx(200)
    assert score.size_penalty == pytest.approx(0)
    assert score.flow_cost == pytest.approx(2.5)
    assert score.total_score == pytest.approx(202.5)


def test_add_remove_move_deltas_match_full_recomputation() -> None:
    config = PartitionConfig(
        target_k=2,
        active_recipe_count=4,
        weights=ObjectiveWeights(
            port_cost_weight=100,
            size_penalty_weight=3,
            flow_cost_weight=0.25,
        ),
        port_epsilon=0.01,
    )
    source = cluster_from_recipes(
        (
            RecipeNetVector("producer", 1, {"ore": 4, "plate": 0.005}),
            RecipeNetVector("consumer", 1, {"ore": -1}),
        ),
    )
    target = cluster_from_recipes((RecipeNetVector("gear", 1, {"gear": 2}),))
    moved = RecipeNetVector("consumer", 1, {"ore": -1})

    before_source = score_cluster(source, config)
    source_added = source.copy()
    extra = RecipeNetVector("extra", 1, {"ore": -3, "plate": 0.02})
    source_added.add_recipe(extra)
    assert _components_tuple(add_recipe_delta(source, extra, config)) == pytest.approx(
        _components_tuple(score_cluster(source_added, config) - before_source),
    )

    source_removed = source.copy()
    source_removed.remove_recipe(moved)
    remove_delta = remove_recipe_delta(source, moved, config)
    assert _components_tuple(remove_delta) == pytest.approx(
        _components_tuple(score_cluster(source_removed, config) - before_source),
    )

    before_partition = score_partition((source, target), config)
    moved_source = source.copy()
    moved_target = target.copy()
    moved_source.remove_recipe(moved)
    moved_target.add_recipe(moved)
    after_partition = score_partition((moved_source, moved_target), config)
    move_delta = move_recipe_delta(source, target, moved, config)
    assert _components_tuple(move_delta) == pytest.approx(
        _components_tuple(after_partition - before_partition),
    )
