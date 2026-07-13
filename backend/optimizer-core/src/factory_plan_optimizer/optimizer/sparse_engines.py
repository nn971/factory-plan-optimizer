from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil, sqrt
from time import monotonic
from typing import TYPE_CHECKING

from factory_plan_optimizer.optimizer.sparse_partition import (
    ClusterState,
    ObjectiveComponents,
    PartitionConfig,
    RecipeNetVector,
    add_recipe_delta,
    cluster_from_recipes,
    move_recipe_delta,
    score_partition,
)

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.sparse_graph import RecipeEdge


SMALL_K_ALL_CANDIDATES = 8
IMPROVEMENT_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class PortAwareEngineResult:
    """Assignments and objective/refinement diagnostics from port-aware clustering."""

    assignments: dict[str, int]
    refinement_passes: int
    objective: ObjectiveComponents


@dataclass(frozen=True, slots=True)
class PortAwareEngine:
    """Dependency-free seeded assignment plus local refinement engine."""

    max_refinement_passes: int

    def cluster(
        self,
        recipe_vectors: dict[str, RecipeNetVector],
        edges: tuple[RecipeEdge, ...],
        target_count: int,
        config: PartitionConfig,
        deadline: float,
    ) -> PortAwareEngineResult:
        """Cluster recipes by directly minimizing the net-port objective."""
        if not recipe_vectors:
            return PortAwareEngineResult(
                {},
                0,
                ObjectiveComponents(0.0, 0.0, 0.0, 0.0, 0),
            )
        neighbor_ids, affinities = _graph_hints(edges)
        seed_ids = _choose_seeds(recipe_vectors, neighbor_ids, target_count)
        clusters = [
            cluster_from_recipes((recipe_vectors[seed_id],)) for seed_id in seed_ids
        ]
        assignments = {seed_id: index for index, seed_id in enumerate(seed_ids)}
        for recipe_id in sorted(set(recipe_vectors) - set(seed_ids)):
            _check_deadline(deadline)
            cluster_id = _best_assignment_cluster(
                recipe_vectors[recipe_id],
                clusters,
                assignments,
                affinities,
                config,
            )
            clusters[cluster_id].add_recipe(recipe_vectors[recipe_id])
            assignments[recipe_id] = cluster_id
        passes = _refine(
            recipe_vectors,
            clusters,
            assignments,
            neighbor_ids,
            config,
            self.max_refinement_passes,
            deadline,
        )
        score = score_partition(clusters, config)
        return PortAwareEngineResult(
            _renumber_assignments(assignments),
            passes,
            score,
        )


def automatic_target(
    active_recipe_count: int,
    minimum: int | None,
    maximum: int | None,
    target: int | None,
) -> int:
    """Choose the effective cluster target from bounds and active recipe count."""
    chosen = target if target is not None else max(1, ceil(sqrt(active_recipe_count)))
    if minimum is not None:
        chosen = max(minimum, chosen)
    if maximum is not None:
        chosen = min(maximum, chosen)
    return max(1, min(active_recipe_count, chosen))


def _choose_seeds(
    recipe_vectors: dict[str, RecipeNetVector],
    neighbor_ids: dict[str, set[str]],
    target_count: int,
) -> list[str]:
    seeds: list[str] = []
    candidates = sorted(
        (_seed_rank(recipe, neighbor_ids) for recipe in recipe_vectors.values()),
        key=lambda row: (-row[1], -row[2], row[0]),
    )
    deferred: list[str] = []
    for recipe_id, _score, _degree in candidates:
        if any(recipe_id in neighbor_ids.get(seed_id, set()) for seed_id in seeds):
            deferred.append(recipe_id)
            continue
        seeds.append(recipe_id)
        if len(seeds) >= target_count:
            return seeds
    for recipe_id in deferred:
        seeds.append(recipe_id)
        if len(seeds) >= target_count:
            return seeds
    return seeds


def _seed_rank(
    recipe: RecipeNetVector,
    neighbor_ids: dict[str, set[str]],
) -> tuple[str, float, int]:
    return (
        recipe.recipe_id,
        len(recipe.item_net) * 1000.0
        + sum(abs(value) for value in recipe.item_net.values()),
        len(neighbor_ids.get(recipe.recipe_id, set())),
    )


def _best_assignment_cluster(
    recipe: RecipeNetVector,
    clusters: list[ClusterState],
    assignments: dict[str, int],
    affinities: dict[tuple[str, str], float],
    config: PartitionConfig,
) -> int:
    best: tuple[float, float, float, int] | None = None
    best_cluster = 0
    for cluster_id, cluster in enumerate(clusters):
        delta = add_recipe_delta(cluster, recipe, config)
        affinity = sum(
            affinities.get(_pair_key(recipe.recipe_id, other), 0.0)
            for other, assigned_cluster in assignments.items()
            if assigned_cluster == cluster_id
        )
        rank = (delta.total_score, -affinity, cluster.size, cluster_id)
        if best is None or rank < best:
            best = rank
            best_cluster = cluster_id
    return best_cluster


def _refine(  # noqa: PLR0913
    recipe_vectors: dict[str, RecipeNetVector],
    clusters: list[ClusterState],
    assignments: dict[str, int],
    neighbor_ids: dict[str, set[str]],
    config: PartitionConfig,
    max_passes: int,
    deadline: float,
) -> int:
    completed = 0
    for _ in range(max_passes):
        _check_deadline(deadline)
        changed = False
        for recipe_id in sorted(recipe_vectors):
            _check_deadline(deadline)
            source_id = assignments[recipe_id]
            if len(clusters[source_id].recipe_ids) <= 1:
                continue
            target_id = _best_move_target(
                recipe_vectors[recipe_id],
                source_id,
                clusters,
                assignments,
                neighbor_ids,
                config,
            )
            if target_id is None:
                continue
            clusters[source_id].remove_recipe(recipe_vectors[recipe_id])
            clusters[target_id].add_recipe(recipe_vectors[recipe_id])
            assignments[recipe_id] = target_id
            changed = True
        completed += 1
        if not changed:
            break
    return completed


def _best_move_target(  # noqa: PLR0913
    recipe: RecipeNetVector,
    source_id: int,
    clusters: list[ClusterState],
    assignments: dict[str, int],
    neighbor_ids: dict[str, set[str]],
    config: PartitionConfig,
) -> int | None:
    best: tuple[float, int] | None = None
    for target_id in _candidate_targets(
        recipe,
        source_id,
        clusters,
        assignments,
        neighbor_ids,
        config,
    ):
        delta = move_recipe_delta(
            clusters[source_id],
            clusters[target_id],
            recipe,
            config,
        )
        if delta.total_score >= -IMPROVEMENT_EPSILON:
            continue
        rank = (delta.total_score, target_id)
        if best is None or rank < best:
            best = rank
    return None if best is None else best[1]


def _candidate_targets(  # noqa: PLR0913
    recipe: RecipeNetVector,
    source_id: int,
    clusters: list[ClusterState],
    assignments: dict[str, int],
    neighbor_ids: dict[str, set[str]],
    config: PartitionConfig,
) -> list[int]:
    targets = {
        assignments[neighbor]
        for neighbor in neighbor_ids.get(recipe.recipe_id, set())
        if neighbor in assignments and assignments[neighbor] != source_id
    }
    targets.update(
        cluster_id
        for cluster_id, cluster in enumerate(clusters)
        if cluster_id != source_id and cluster.size < config.min_size
    )
    if len(clusters) <= SMALL_K_ALL_CANDIDATES:
        targets.update(range(len(clusters)))
        targets.discard(source_id)
    return sorted(targets)


def _graph_hints(
    edges: tuple[RecipeEdge, ...],
) -> tuple[dict[str, set[str]], dict[tuple[str, str], float]]:
    neighbors: dict[str, set[str]] = defaultdict(set)
    affinities: dict[tuple[str, str], float] = defaultdict(float)
    for edge in edges:
        neighbors[edge.producer_recipe_id].add(edge.consumer_recipe_id)
        neighbors[edge.consumer_recipe_id].add(edge.producer_recipe_id)
        affinities[_pair_key(edge.producer_recipe_id, edge.consumer_recipe_id)] += (
            edge.edge_weight
        )
    return neighbors, affinities


def _pair_key(first: str, second: str) -> tuple[str, str]:
    return (first, second) if first <= second else (second, first)


def _renumber_assignments(assignments: dict[str, int]) -> dict[str, int]:
    seen: dict[int, int] = {}
    next_id = 0
    result = {}
    for recipe_id, old_id in sorted(assignments.items()):
        if old_id not in seen:
            seen[old_id] = next_id
            next_id += 1
        result[recipe_id] = seen[old_id]
    return result


def _check_deadline(deadline: float) -> None:
    if monotonic() > deadline:
        message = "sparse clustering timed out during port-aware clustering"
        raise TimeoutError(message)
