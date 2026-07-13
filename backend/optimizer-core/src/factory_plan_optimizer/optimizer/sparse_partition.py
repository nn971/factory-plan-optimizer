from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from game_data_extractor.data_contracts import FactoryDataPackage


@dataclass(frozen=True, slots=True)
class RecipeNetVector:
    """Sparse solved recipe net production vector."""

    recipe_id: str
    rate: float
    item_net: dict[str, float]
    size: float = 1.0


@dataclass(slots=True)
class ClusterState:
    """Mutable sparse cluster state for local partition objective updates."""

    recipe_ids: set[str] = field(default_factory=set)
    item_net: dict[str, float] = field(default_factory=dict)
    size: float = 0.0

    def copy(self) -> ClusterState:
        """Return a mutable copy of this cluster."""
        return ClusterState(set(self.recipe_ids), dict(self.item_net), self.size)

    def add_recipe(self, recipe: RecipeNetVector) -> None:
        """Add one recipe vector to this cluster."""
        self.recipe_ids.add(recipe.recipe_id)
        self.size += recipe.size
        _apply_vector(self.item_net, recipe.item_net, 1.0)

    def remove_recipe(self, recipe: RecipeNetVector) -> None:
        """Remove one recipe vector from this cluster."""
        self.recipe_ids.remove(recipe.recipe_id)
        self.size -= recipe.size
        _apply_vector(self.item_net, recipe.item_net, -1.0)


@dataclass(frozen=True, slots=True)
class ObjectiveWeights:
    """Weights for the named partition objective components."""

    port_cost_weight: float = 1000.0
    size_penalty_weight: float = 10.0
    flow_cost_weight: float = 0.0


@dataclass(frozen=True, slots=True)
class PartitionConfig:
    """Configuration required to score a sparse recipe partition."""

    target_k: int
    active_recipe_count: int
    weights: ObjectiveWeights = ObjectiveWeights()
    min_cluster_size_ratio: float = 0.5
    max_cluster_size_ratio: float = 1.5
    port_epsilon: float = 1e-9

    @property
    def target_size(self) -> float:
        """Ideal recipe-count cluster size."""
        return self.active_recipe_count / self.target_k

    @property
    def min_size(self) -> float:
        """Soft minimum recipe-count cluster size."""
        return self.min_cluster_size_ratio * self.target_size

    @property
    def max_size(self) -> float:
        """Soft maximum recipe-count cluster size."""
        return self.max_cluster_size_ratio * self.target_size


@dataclass(frozen=True, slots=True)
class ObjectiveComponents:
    """Named objective components for partition scoring."""

    port_cost: float
    size_penalty: float
    flow_cost: float
    total_score: float
    net_port_count: int

    def __sub__(self, other: ObjectiveComponents) -> ObjectiveComponents:
        """Subtract matching objective components."""
        return ObjectiveComponents(
            port_cost=self.port_cost - other.port_cost,
            size_penalty=self.size_penalty - other.size_penalty,
            flow_cost=self.flow_cost - other.flow_cost,
            total_score=self.total_score - other.total_score,
            net_port_count=self.net_port_count - other.net_port_count,
        )


def build_recipe_net_vectors(
    package: FactoryDataPackage,
    recipe_rates: Mapping[str, float],
) -> dict[str, RecipeNetVector]:
    """Build `coefficient * solved_rate` sparse vectors for active recipes only."""
    vectors: dict[str, RecipeNetVector] = {}
    for recipe in package.recipes:
        rate = recipe_rates.get(recipe.id, 0.0)
        if rate == 0.0:
            continue
        item_net = {
            item_id: coefficient * rate
            for item_id, coefficient in recipe.coefficients.items()
            if coefficient * rate != 0.0
        }
        vectors[recipe.id] = RecipeNetVector(
            recipe_id=recipe.id,
            rate=rate,
            item_net=item_net,
        )
    return vectors


def cluster_from_recipes(recipes: Iterable[RecipeNetVector]) -> ClusterState:
    cluster = ClusterState()
    for recipe in recipes:
        cluster.add_recipe(recipe)
    return cluster


def net_port_direction(net: float, port_epsilon: float) -> str | None:
    if net > port_epsilon:
        return "output"
    if net < -port_epsilon:
        return "input"
    return None


def net_port_count(item_net: Mapping[str, float], port_epsilon: float) -> int:
    return sum(
        1
        for net in item_net.values()
        if net_port_direction(net, port_epsilon) is not None
    )


def size_penalty(size: float, config: PartitionConfig) -> float:
    under = max(0.0, config.min_size - size)
    over = max(0.0, size - config.max_size)
    return under * under + over * over


def score_cluster(
    cluster: ClusterState,
    config: PartitionConfig,
) -> ObjectiveComponents:
    ports = net_port_count(cluster.item_net, config.port_epsilon)
    abs_flow = sum(abs(net) for net in cluster.item_net.values())
    raw_size_penalty = size_penalty(cluster.size, config)
    port_cost = config.weights.port_cost_weight * ports
    weighted_size_penalty = config.weights.size_penalty_weight * raw_size_penalty
    flow_cost = config.weights.flow_cost_weight * abs_flow
    return ObjectiveComponents(
        port_cost=port_cost,
        size_penalty=weighted_size_penalty,
        flow_cost=flow_cost,
        total_score=port_cost + weighted_size_penalty + flow_cost,
        net_port_count=ports,
    )


def score_partition(
    clusters: Iterable[ClusterState],
    config: PartitionConfig,
) -> ObjectiveComponents:
    total = ObjectiveComponents(0.0, 0.0, 0.0, 0.0, 0)
    for cluster in clusters:
        score = score_cluster(cluster, config)
        total = ObjectiveComponents(
            port_cost=total.port_cost + score.port_cost,
            size_penalty=total.size_penalty + score.size_penalty,
            flow_cost=total.flow_cost + score.flow_cost,
            total_score=total.total_score + score.total_score,
            net_port_count=total.net_port_count + score.net_port_count,
        )
    return total


def add_recipe_delta(
    cluster: ClusterState,
    recipe: RecipeNetVector,
    config: PartitionConfig,
) -> ObjectiveComponents:
    return _local_delta(cluster, recipe, config, 1.0)


def remove_recipe_delta(
    cluster: ClusterState,
    recipe: RecipeNetVector,
    config: PartitionConfig,
) -> ObjectiveComponents:
    return _local_delta(cluster, recipe, config, -1.0)


def move_recipe_delta(
    source: ClusterState,
    target: ClusterState,
    recipe: RecipeNetVector,
    config: PartitionConfig,
) -> ObjectiveComponents:
    source_delta = remove_recipe_delta(source, recipe, config)
    target_delta = add_recipe_delta(target, recipe, config)
    return ObjectiveComponents(
        port_cost=source_delta.port_cost + target_delta.port_cost,
        size_penalty=source_delta.size_penalty + target_delta.size_penalty,
        flow_cost=source_delta.flow_cost + target_delta.flow_cost,
        total_score=source_delta.total_score + target_delta.total_score,
        net_port_count=source_delta.net_port_count + target_delta.net_port_count,
    )


def _local_delta(
    cluster: ClusterState,
    recipe: RecipeNetVector,
    config: PartitionConfig,
    sign: float,
) -> ObjectiveComponents:
    before_ports = 0
    after_ports = 0
    before_abs_flow = 0.0
    after_abs_flow = 0.0
    for item_id, recipe_net in recipe.item_net.items():
        before_net = cluster.item_net.get(item_id, 0.0)
        after_net = before_net + sign * recipe_net
        before_ports += int(
            net_port_direction(before_net, config.port_epsilon) is not None,
        )
        after_ports += int(
            net_port_direction(after_net, config.port_epsilon) is not None,
        )
        before_abs_flow += abs(before_net)
        after_abs_flow += abs(after_net)

    before_size_penalty = size_penalty(cluster.size, config)
    after_size_penalty = size_penalty(cluster.size + sign * recipe.size, config)
    port_cost = config.weights.port_cost_weight * (after_ports - before_ports)
    weighted_size_penalty = config.weights.size_penalty_weight * (
        after_size_penalty - before_size_penalty
    )
    flow_cost = config.weights.flow_cost_weight * (after_abs_flow - before_abs_flow)
    return ObjectiveComponents(
        port_cost=port_cost,
        size_penalty=weighted_size_penalty,
        flow_cost=flow_cost,
        total_score=port_cost + weighted_size_penalty + flow_cost,
        net_port_count=after_ports - before_ports,
    )


def _apply_vector(
    item_net: dict[str, float],
    vector: Mapping[str, float],
    sign: float,
) -> None:
    for item_id, value in vector.items():
        updated = item_net.get(item_id, 0.0) + sign * value
        if updated == 0.0:
            item_net.pop(item_id, None)
        else:
            item_net[item_id] = updated
