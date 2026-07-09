from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game_data_extractor.data_contracts import FactoryDataPackage, Recipe


# Optimizer-side tolerance for treating solved recipe rates and item flows as active.
ACTIVE_EPSILON = 1e-9

FLOW_COST_PER_QUANTITY = 1.0
PORT_COST_PER_BOUNDARY_TYPE = 100.0
RECIPE_SIZE_PENALTY = 10.0
BOUNDARY_TYPE_SIZE_PENALTY = 25.0
TARGET_RECIPE_COUNT = (5, 15)
TARGET_BOUNDARY_TYPE_COUNT = (3, 8)


def build_cluster_diagnostics(
    package: FactoryDataPackage,
    recipe_rates: Mapping[str, float],
    *,
    base_objective_value: float = 0.0,
) -> dict[str, Any]:
    """Build deterministic post-solve cluster/logistics diagnostics.

    Diagnostics are solution-derived and intentionally do not affect LP objective terms.
    """
    recipes_by_id = {recipe.id: recipe for recipe in package.recipes}
    active_ids = sorted(
        recipe_id
        for recipe_id, rate in recipe_rates.items()
        if rate > ACTIVE_EPSILON and recipe_id in recipes_by_id
    )
    if not active_ids:
        return _empty_diagnostics(base_objective_value)

    clusters = _clusters(active_ids, recipes_by_id)
    cluster_rows: list[dict[str, Any]] = []
    global_components = {
        "flow_cost": 0.0,
        "port_cost": 0.0,
        "cluster_cost": 0.0,
        "duplication_cost": 0.0,
    }

    for index, recipe_ids in enumerate(clusters):
        recipes = [recipes_by_id[recipe_id] for recipe_id in recipe_ids]
        category = recipes[0].category
        boundary_rows = _boundary_rows(recipes, recipe_rates)
        cluster_rows.append(
            {
                "id": f"cluster-{index + 1}",
                "category": category,
                "recipe_ids": list(recipe_ids),
                "boundary_items": boundary_rows,
            },
        )

    _attribute_boundary_costs(cluster_rows)

    for cluster_row in cluster_rows:
        recipe_ids = cluster_row["recipe_ids"]
        recipes = [recipes_by_id[recipe_id] for recipe_id in recipe_ids]
        category = recipes[0].category
        boundary_rows = cluster_row["boundary_items"]
        nonzero_rows = [
            row for row in boundary_rows if abs(row["quantity"]) > ACTIVE_EPSILON
        ]
        flow_cost = sum(row["flow_cost"] for row in nonzero_rows)
        port_cost = sum(row["port_cost"] for row in nonzero_rows)
        cluster_cost = _size_penalty(
            len(recipe_ids),
            TARGET_RECIPE_COUNT,
            RECIPE_SIZE_PENALTY,
        )
        cluster_cost += _size_penalty(
            len(nonzero_rows),
            TARGET_BOUNDARY_TYPE_COUNT,
            BOUNDARY_TYPE_SIZE_PENALTY,
        )
        components = {
            "flow_cost": flow_cost,
            "port_cost": port_cost,
            "cluster_cost": cluster_cost,
            "duplication_cost": 0.0,
        }
        for key, value in components.items():
            global_components[key] += value
        label_item = _dominant_output(recipes, recipe_rates, boundary_rows)
        cluster_row.update(
            {
                "label": f"{category}: {label_item}",
                "active_recipe_count": len(recipe_ids),
                "boundary_item_type_count": len(nonzero_rows),
                "diagnostic_components": components,
            },
        )

    diagnostic_total = sum(global_components.values())
    return {
        "mode": "diagnostic_only",
        "active_epsilon": ACTIVE_EPSILON,
        "cost_defaults": _cost_defaults(),
        "diagnostic_components": global_components,
        "base_objective_value": base_objective_value,
        "diagnostic_total": diagnostic_total,
        "combined_diagnostic_objective_value": base_objective_value + diagnostic_total,
        "clusters": cluster_rows,
    }


def _clusters(  # noqa: C901
    active_ids: list[str],
    recipes_by_id: Mapping[str, Recipe],
) -> list[list[str]]:
    by_category: dict[str, list[str]] = defaultdict(list)
    for recipe_id in active_ids:
        by_category[recipes_by_id[recipe_id].category].append(recipe_id)

    clusters: list[list[str]] = []
    for category in sorted(by_category):
        ids = sorted(by_category[category])
        neighbors = {recipe_id: set[str]() for recipe_id in ids}
        for left in ids:
            for right in ids:
                if left >= right:
                    continue
                if _directly_linked(recipes_by_id[left], recipes_by_id[right]):
                    neighbors[left].add(right)
                    neighbors[right].add(left)
        unseen = set(ids)
        while unseen:
            start = min(unseen)
            component: list[str] = []
            queue = deque([start])
            unseen.remove(start)
            while queue:
                current = queue.popleft()
                component.append(current)
                for nxt in sorted(neighbors[current]):
                    if nxt in unseen:
                        unseen.remove(nxt)
                        queue.append(nxt)
            clusters.append(sorted(component))
    return clusters


def _directly_linked(left: Recipe, right: Recipe) -> bool:
    for item_id, left_coeff in left.coefficients.items():
        right_coeff = right.coefficients.get(item_id, 0.0)
        if left_coeff * right_coeff < -(ACTIVE_EPSILON**2):
            return True
    return False


def _boundary_rows(
    recipes: list[Recipe],
    recipe_rates: Mapping[str, float],
) -> list[dict[str, Any]]:
    nets: dict[str, float] = defaultdict(float)
    positive_gross: dict[str, float] = defaultdict(float)
    negative_gross: dict[str, float] = defaultdict(float)
    for recipe in recipes:
        rate = recipe_rates[recipe.id]
        for item_id, coefficient in recipe.coefficients.items():
            quantity = coefficient * rate
            nets[item_id] += quantity
            if quantity > ACTIVE_EPSILON:
                positive_gross[item_id] += quantity
            elif quantity < -ACTIVE_EPSILON:
                negative_gross[item_id] += abs(quantity)
    rows = []
    for item_id in sorted(nets):
        quantity = nets[item_id]
        is_zero_net = False
        if abs(quantity) <= ACTIVE_EPSILON:
            quantity = 0.0
            is_zero_net = True
            direction = (
                "input" if negative_gross[item_id] > ACTIVE_EPSILON else "output"
            )
        elif quantity > 0.0:
            direction = "output"
        else:
            direction = "input"
        rows.append(
            {
                "item_id": item_id,
                "direction": direction,
                "is_zero_net": is_zero_net,
                "quantity": quantity,
                "flow_cost": (
                    abs(quantity) * FLOW_COST_PER_QUANTITY if quantity else 0.0
                ),
                "port_cost": PORT_COST_PER_BOUNDARY_TYPE if quantity else 0.0,
            },
        )
    return rows


def _attribute_boundary_costs(cluster_rows: list[dict[str, Any]]) -> None:
    rows_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in cluster_rows:
        for row in cluster["boundary_items"]:
            row["flow_cost"] = 0.0
            row["port_cost"] = 0.0
            if abs(row["quantity"]) > ACTIVE_EPSILON:
                rows_by_item[row["item_id"]].append(row)

    for rows in rows_by_item.values():
        output_rows = [row for row in rows if row["direction"] == "output"]
        input_rows = [row for row in rows if row["direction"] == "input"]
        output_total = sum(row["quantity"] for row in output_rows)
        input_total = sum(abs(row["quantity"]) for row in input_rows)
        if output_total > ACTIVE_EPSILON and input_total > ACTIVE_EPSILON:
            matched = min(output_total, input_total)
            for row in output_rows:
                share = row["quantity"] / output_total
                row["flow_cost"] += matched * FLOW_COST_PER_QUANTITY * 0.5 * share
                row["port_cost"] += PORT_COST_PER_BOUNDARY_TYPE * 0.5 / len(output_rows)
                row["flow_cost"] += max(row["quantity"] - matched * share, 0.0)
            for row in input_rows:
                quantity = abs(row["quantity"])
                share = quantity / input_total
                row["flow_cost"] += matched * FLOW_COST_PER_QUANTITY * 0.5 * share
                row["port_cost"] += PORT_COST_PER_BOUNDARY_TYPE * 0.5 / len(input_rows)
                row["flow_cost"] += max(quantity - matched * share, 0.0)
        else:
            for row in rows:
                row["flow_cost"] = abs(row["quantity"]) * FLOW_COST_PER_QUANTITY
                row["port_cost"] = PORT_COST_PER_BOUNDARY_TYPE


def _dominant_output(
    recipes: list[Recipe],
    recipe_rates: Mapping[str, float],
    boundary_rows: list[dict[str, Any]],
) -> str:
    outputs: dict[str, float] = defaultdict(float)
    for recipe in recipes:
        rate = recipe_rates[recipe.id]
        for item_id, coefficient in recipe.coefficients.items():
            if coefficient > ACTIVE_EPSILON:
                outputs[item_id] += coefficient * rate
    if not outputs:
        outputs = {
            row["item_id"]: abs(row["quantity"])
            for row in boundary_rows
            if row["direction"] == "output"
        }
    if not outputs:
        return "unknown"
    return min(outputs, key=lambda item_id: (-outputs[item_id], item_id))


def _size_penalty(count: int, target: tuple[int, int], rate: float) -> float:
    low, high = target
    if count < low:
        return (low - count) * rate
    if count > high:
        return (count - high) * rate
    return 0.0


def _empty_diagnostics(base_objective_value: float = 0.0) -> dict[str, Any]:
    return {
        "mode": "diagnostic_only",
        "active_epsilon": ACTIVE_EPSILON,
        "cost_defaults": _cost_defaults(),
        "diagnostic_components": {
            "flow_cost": 0.0,
            "port_cost": 0.0,
            "cluster_cost": 0.0,
            "duplication_cost": 0.0,
        },
        "base_objective_value": base_objective_value,
        "diagnostic_total": 0.0,
        "combined_diagnostic_objective_value": base_objective_value,
        "clusters": [],
    }


def _cost_defaults() -> dict[str, float | list[int]]:
    return {
        "flow_cost_per_quantity": FLOW_COST_PER_QUANTITY,
        "port_cost_per_boundary_type": PORT_COST_PER_BOUNDARY_TYPE,
        "recipe_size_penalty": RECIPE_SIZE_PENALTY,
        "boundary_type_size_penalty": BOUNDARY_TYPE_SIZE_PENALTY,
        "target_active_recipes": list(TARGET_RECIPE_COUNT),
        "target_boundary_item_types": list(TARGET_BOUNDARY_TYPE_COUNT),
    }
