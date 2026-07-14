from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from factory_plan_optimizer.optimizer.sparse_graph import SparseGraph
    from factory_plan_optimizer.optimizer.sparse_partition import RecipeNetVector

from factory_plan_optimizer.optimizer.sparse_partition import (
    cluster_from_recipes,
    net_port_direction,
)


def capped(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    """Return a capped result-array payload."""
    return {
        "items": items[:limit],
        "total_count": len(items),
        "truncated": len(items) > limit,
    }


def analyze_boundaries(  # noqa: C901,PLR0912,PLR0913
    graph: SparseGraph,
    assignments: dict[str, int],
    recipe_vectors: Mapping[str, RecipeNetVector],
    port_epsilon: float,
    external_supplies: Mapping[str, float],
    final_demands: Mapping[str, float],
    surplus: Mapping[str, float],
    unmet_demand: Mapping[str, float],
    caps: dict[str, int],
) -> dict[str, Any]:
    cluster_recipes: dict[int, list[str]] = defaultdict(list)
    for recipe_id, cluster_id in sorted(assignments.items()):
        cluster_recipes[cluster_id].append(recipe_id)

    external_amounts: dict[tuple[int, str, str], float] = {}
    for item_id, amount in sorted(external_supplies.items()):
        if amount <= 0.0:
            continue
        for endpoint in graph.consumers_by_item.get(item_id, ()):
            cluster_id = assignments[endpoint.recipe_id]
            key = (cluster_id, item_id, "input")
            external_amounts[key] = amount
    for item_id, amount in sorted(final_demands.items()):
        if amount <= 0.0:
            continue
        for endpoint in graph.producers_by_item.get(item_id, ()):
            cluster_id = assignments[endpoint.recipe_id]
            key = (cluster_id, item_id, "output")
            external_amounts[key] = amount

    cluster_states = {
        cluster_id: cluster_from_recipes(
            recipe_vectors[recipe_id] for recipe_id in recipes
        )
        for cluster_id, recipes in cluster_recipes.items()
    }
    net_port_rows = []
    cluster_net_counts: dict[int, dict[str, int]] = {}
    for cluster_id, cluster in sorted(cluster_states.items()):
        input_count = 0
        output_count = 0
        for item_id, net in sorted(cluster.item_net.items()):
            direction = net_port_direction(net, port_epsilon)
            if direction is None:
                continue
            if direction == "input":
                input_count += 1
            else:
                output_count += 1
            net_port_rows.append(
                {
                    "cluster_id": cluster_id,
                    "item_id": item_id,
                    "direction": direction,
                    "net_amount": net,
                },
            )
        cluster_net_counts[cluster_id] = {
            "net_input_port_count": input_count,
            "net_output_port_count": output_count,
            "net_port_count": input_count + output_count,
        }

    external_ports = _external_port_rows(external_amounts)
    port_rows = sorted(
        net_port_rows,
        key=lambda row: (row["cluster_id"], row["item_id"], row["direction"]),
    )
    surplus_unmet = [
        {
            "item_id": item_id,
            "surplus": surplus.get(item_id, 0.0),
            "unmet_demand": unmet_demand.get(item_id, 0.0),
        }
        for item_id in sorted(set(surplus) | set(unmet_demand))
        if surplus.get(item_id, 0.0) > 0.0 or unmet_demand.get(item_id, 0.0) > 0.0
    ]
    clusters = [
        {
            "cluster_id": cid,
            "recipe_count": len(recipes),
            "recipe_ids": recipes,
            **cluster_net_counts[cid],
        }
        for cid, recipes in sorted(cluster_recipes.items())
    ]
    net_port_count = len(port_rows)
    return {
        "cluster_summaries": capped(clusters, caps["cluster_summaries"]),
        "recipe_assignments": capped(
            [
                {"recipe_id": recipe_id, "cluster_id": cluster_id}
                for recipe_id, cluster_id in sorted(assignments.items())
            ],
            caps["recipe_assignments"],
        ),
        "boundary_port_types": capped(port_rows, caps["boundary_port_types"]),
        "external_boundary_port_types": capped(
            external_ports,
            caps["external_boundary_port_types"],
        ),
        "surplus_unmet_summary": capped(surplus_unmet, caps["surplus_unmet"]),
        "quality": {
            "boundary_port_type_count": net_port_count,
            "net_port_count": net_port_count,
            "size_imbalance": _imbalance(clusters),
        },
        "boundary_port_type_count": net_port_count,
        "net_port_count": net_port_count,
        "external_boundary_port_type_count": len(external_ports),
    }


def _external_port_rows(
    amounts: Mapping[tuple[int, str, str], float],
) -> list[dict[str, Any]]:
    return [
        {
            "cluster_id": cluster,
            "item_id": item_id,
            "direction": direction,
            "amount": amount,
        }
        for (cluster, item_id, direction), amount in sorted(
            amounts.items(),
            key=lambda row: (row[0][1], row[0][0], row[0][2]),
        )
    ]


def _imbalance(clusters: list[dict[str, Any]]) -> int:
    if not clusters:
        return 0
    sizes = [int(cluster["recipe_count"]) for cluster in clusters]
    return max(sizes) - min(sizes)
