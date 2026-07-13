from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game_data_extractor.data_contracts import FactoryDataPackage


@dataclass(frozen=True, slots=True)
class ActiveRecipe:
    """Solved recipe rate active in the sparse graph."""

    id: str
    rate: float
    production_cost: float | None


@dataclass(frozen=True, slots=True)
class ItemEndpoint:
    """Recipe-side production or consumption amount for one item."""

    recipe_id: str
    amount: float


@dataclass(frozen=True, slots=True)
class RecipeEdge:
    """Capped recipe-to-recipe item flow estimate."""

    producer_recipe_id: str
    consumer_recipe_id: str
    item_id: str
    estimated_flow: float
    edge_weight: float


@dataclass(frozen=True, slots=True)
class HubSummary:
    """Per-item summary of candidate edges skipped by hub capping."""

    item_id: str
    kept_count: int
    skipped_count: int
    skipped_estimated_flow: float


@dataclass(frozen=True, slots=True)
class SparseGraph:
    """Sparse active recipe graph and construction diagnostics."""

    active_recipes: tuple[ActiveRecipe, ...]
    producers_by_item: dict[str, tuple[ItemEndpoint, ...]]
    consumers_by_item: dict[str, tuple[ItemEndpoint, ...]]
    edges: tuple[RecipeEdge, ...]
    hub_summaries: tuple[HubSummary, ...]
    total_candidate_edges: int
    total_candidate_flow: float


def build_sparse_graph(
    package: FactoryDataPackage,
    recipe_rates: Mapping[str, float],
    *,
    min_recipe_rate: float,
    hub_item_top_k: int,
) -> SparseGraph:
    rates = recipe_rates
    active = tuple(
        ActiveRecipe(recipe.id, rates.get(recipe.id, 0.0), recipe.production_cost)
        for recipe in sorted(package.recipes, key=lambda recipe: recipe.id)
        if rates.get(recipe.id, 0.0) > min_recipe_rate
    )
    active_ids = {recipe.id for recipe in active}
    producers: dict[str, list[ItemEndpoint]] = {}
    consumers: dict[str, list[ItemEndpoint]] = {}
    for recipe in sorted(package.recipes, key=lambda recipe: recipe.id):
        if recipe.id not in active_ids:
            continue
        rate = rates[recipe.id]
        for item_id, coefficient in sorted(recipe.coefficients.items()):
            amount = coefficient * rate
            if amount > 0.0:
                producers.setdefault(item_id, []).append(
                    ItemEndpoint(recipe.id, amount),
                )
            elif amount < 0.0:
                consumers.setdefault(item_id, []).append(
                    ItemEndpoint(recipe.id, -amount),
                )

    producers_by_item = {key: tuple(value) for key, value in sorted(producers.items())}
    consumers_by_item = {key: tuple(value) for key, value in sorted(consumers.items())}
    cost_signal = _cost_signal(active)
    edges: list[RecipeEdge] = []
    hubs: list[HubSummary] = []
    candidate_count = 0
    candidate_flow = 0.0
    for item_id in sorted(set(producers_by_item) | set(consumers_by_item)):
        item_edges, item_candidate_count, item_candidate_flow = _allocate_item_edges(
            item_id,
            producers_by_item.get(item_id, ()),
            consumers_by_item.get(item_id, ()),
            cost_signal,
            hub_item_top_k,
        )
        candidate_count += item_candidate_count
        candidate_flow += item_candidate_flow
        skipped_count = item_candidate_count - len(item_edges)
        if skipped_count:
            hubs.append(
                HubSummary(
                    item_id=item_id,
                    kept_count=len(item_edges),
                    skipped_count=skipped_count,
                    skipped_estimated_flow=item_candidate_flow
                    - sum(edge.estimated_flow for edge in item_edges),
                ),
            )
        edges.extend(item_edges)
    return SparseGraph(
        active_recipes=active,
        producers_by_item=producers_by_item,
        consumers_by_item=consumers_by_item,
        edges=tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge.item_id,
                    edge.producer_recipe_id,
                    edge.consumer_recipe_id,
                ),
            ),
        ),
        hub_summaries=tuple(hubs),
        total_candidate_edges=candidate_count,
        total_candidate_flow=candidate_flow,
    )


def _allocate_item_edges(
    item_id: str,
    producers: tuple[ItemEndpoint, ...],
    consumers: tuple[ItemEndpoint, ...],
    cost_signal: dict[str, float],
    limit: int,
) -> tuple[list[RecipeEdge], int, float]:
    if not producers or not consumers:
        return [], 0, 0.0
    total_production = sum(endpoint.amount for endpoint in producers)
    total_consumption = sum(endpoint.amount for endpoint in consumers)
    routed = min(total_production, total_consumption)
    if routed <= 0.0:
        return [], 0, 0.0
    kept: list[RecipeEdge] = []
    for producer in producers:
        for consumer in consumers:
            flow = (
                routed
                * (producer.amount / total_production)
                * (consumer.amount / total_consumption)
            )
            signal = (
                cost_signal.get(producer.recipe_id, 0.0)
                + cost_signal.get(consumer.recipe_id, 0.0)
            ) / 2.0
            edge = RecipeEdge(
                producer.recipe_id,
                consumer.recipe_id,
                item_id,
                flow,
                flow + 1e-6 * signal,
            )
            _insert_if_top_k(kept, edge, limit)
    candidate_count = len(producers) * len(consumers)
    return kept, candidate_count, routed


def _insert_if_top_k(edges: list[RecipeEdge], edge: RecipeEdge, limit: int) -> None:
    edges.append(edge)
    edges.sort(key=_edge_rank)
    if len(edges) > limit:
        edges.pop()


def _edge_rank(edge: RecipeEdge) -> tuple[float, float, str, str]:
    return (
        -edge.estimated_flow,
        -edge.edge_weight,
        edge.producer_recipe_id,
        edge.consumer_recipe_id,
    )


def _cost_signal(active: tuple[ActiveRecipe, ...]) -> dict[str, float]:
    costs = [
        recipe.production_cost
        for recipe in active
        if recipe.production_cost is not None
    ]
    if not costs or min(costs) == max(costs):
        return {recipe.id: 0.0 for recipe in active}
    low = min(costs)
    high = max(costs)
    return {
        recipe.id: 0.0
        if recipe.production_cost is None
        else (recipe.production_cost - low) / (high - low)
        for recipe in active
    }
