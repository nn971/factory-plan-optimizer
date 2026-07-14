# Port-aware sparse clustering

Sparse clustering is an explanation-first, post-solve feature. The global recipe LP
remains authoritative for recipe rates, external supply, final demand, surplus,
unmet demand, feasibility, and objective values. Sparse clustering reads a
successful LP result and assigns active recipes to diagnostic clusters; it does not
change the solved plan.

The old strongest-edge union strategy is obsolete. Recipe-to-recipe sparse graph
edges are still built as dependency/affinity hints for clustering refinement, but
they are not exported as source-to-target item-flow allocations.

## Net ports and objective

For each cluster `C` and item `i`, sparse clustering computes recipe-only net
balance from solved rates:

```text
net(C, i) = sum(coefficient(r, i) * solved_rate(r) for r in C)
```

Net-port semantics are:

- `net(C, i) > port_epsilon`: one output net port;
- `net(C, i) < -port_epsilon`: one input net port;
- near zero: no net port.

Opposite recipe balances inside the same cluster cancel, so placing matching
producers and consumers together can reduce port count. Surplus/final products
appear naturally as positive cluster net and count as output net ports. Unmet demand
is diagnostic-only and does not enter sparse clustering's objective.

The reported sparse objective components are:

```text
total_score = port_cost + size_penalty + flow_cost
port_cost = port_cost_weight * total_net_port_count
size_penalty = size_penalty_weight * squared recipe-count size violations
flow_cost = flow_cost_weight * total absolute cluster item net
```

`flow_cost` is based on absolute cluster net balance, not exact routed crossing
flow. Source-target item allocation is not reported; cluster net ports are the
authoritative cluster interface.

`boundary_port_type_count` is retained for compatibility, but it now means total
net port count. The explicit `net_port_count` field is the preferred terminology.
External source/final-demand rows remain available as diagnostics, but they do not
add objective ports and are not included in `boundary_port_type_count`.

## Size penalty

The first port-aware implementation uses recipe-count size only:

```text
target_size = active_recipe_count / target_k
min_size = min_cluster_size_ratio * target_size
max_size = max_cluster_size_ratio * target_size

size_penalty(C) = max(0, min_size - size_C)^2
                + max(0, size_C - max_size)^2
```

This discourages one giant cluster plus tiny leftovers without forcing hard size
bounds.

## Assignment and refinement strategy

The engine is dependency-free and deterministic:

1. choose up to `target_k` non-empty seeds by item incidence, net magnitude, sparse
   graph degree, and recipe-id tie-breaks;
2. assign remaining recipes to the cluster with the best incremental net-objective
   delta, using sparse-edge affinity only as a secondary deterministic tie-break;
3. run local move refinement over bounded candidate clusters.

Candidate target clusters come from neighbor clusters in the sparse graph,
underfull clusters, and all clusters only when the target cluster count is small.
Moves are accepted only when they strictly improve `total_score`, with cooperative
runtime deadline checks.

Modes:

- `fast`: seeded assignment plus one refinement pass;
- `balanced`: seeded assignment plus more refinement passes, bounded by runtime.

Split/merge repair is not implemented yet.

## Request tuning fields

Approved sparse tuning fields and defaults are:

- `port_cost_weight = 1000.0`
- `size_penalty_weight = 10.0`
- `flow_cost_weight = 0.0`
- `min_cluster_size_ratio = 0.5`
- `max_cluster_size_ratio = 1.5`
- `max_refinement_passes = null` (`fast` uses 1, `balanced` defaults to 8)
- `port_epsilon = 1e-9`

Cluster-count controls, runtime, hub cap, result caps, and active-rate threshold are
unchanged from the sparse clustering request shape.

## Reported diagnostics

Results are summary-first and may include capped arrays for cluster summaries,
recipe assignments, net boundary port types, external diagnostic
rows, surplus/unmet rows, and hub summaries. Large arrays carry `total_count` and
`truncated` metadata.

Cluster summaries include recipe ids/counts and net input/output/total port counts.
`boundary_port_types.items` contains net-port rows with `net_amount`. External rows
use `source_or_demand_amount`; this is the source/demand amount associated with a
diagnostic outside interface, not exact routed flow and not an objective port.
Sparse overview visualization renders each net port through an item-pool node:
cluster output -> item pool -> cluster input.

## Limitations and known risks

- Recipe-to-recipe flow is proportional and aggregate; it is not exact routing.
- `flow_cost` is absolute cluster net flow, not exact routed crossing flow.
- External source/final-demand rows are diagnostics-only and do not affect net port
  count.
- Split/merge repair is deferred, so local refinement can still leave imperfect
  size or port trade-offs.
- Very high-degree hub items still cost CPU while candidate producer/consumer pairs
  are considered, even though retained memory is capped.
- Result details are intentionally capped; use `total_count`, graph statistics, and
  truncation warnings for complete-scale summaries.
- The feature is diagnostic-only and does not optimize layout, transport schedules,
  or production choices.

See also `docs/data_interface.md` for package/API contracts and
`docs/mathematical_model.md` for the global LP model notes.
