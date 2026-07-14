# Mathematical model notes

## Coefficient convention

Normalized importer datasets store each recipe coefficient as `a_ir`, the net
production coefficient for item or fluid `i` in recipe `r`.

- `a_ir > 0` means recipe `r` outputs item `i`.
- `a_ir < 0` means recipe `r` consumes item `i`.

This matches the project-wide balance convention:

```text
sum_r a_ir * x_r + external_supply_i = final_demand_i
```

## Initial global recipe LP

The first optimizer model consumes a canonical `FactoryDataPackage` and ignores
all logistics structure. It chooses continuous recipe rates and external supply
rates that satisfy final demand as cheaply as possible. The model supports a
default hard-demand solve mode plus an optional soft diagnostics mode with
explicit unmet-demand variables.

### Variables

For each recipe `r`:

```text
x_r >= 0
```

For each item or fluid `i`:

```text
external_supply_i >= 0
surplus_i >= 0
```

For each demanded final item `i` in soft diagnostics mode:

```text
unmet_demand_i >= 0
```

If an external supply has capacity `capacity_i`, then:

```text
external_supply_i <= capacity_i
```

Items without an external supply entry have `external_supply_i = 0`. In hard
demand mode, all `unmet_demand_i` variables are fixed to `0`, including demanded
items. In soft diagnostics mode, items not listed in `final_demands` have
`unmet_demand_i = 0` while demanded items may use unmet demand with a penalty.

### Balance

For every item or fluid `i` in the package:

```text
sum_r a_ir * x_r + external_supply_i + unmet_demand_i - surplus_i = final_demand_i
```

Missing final demand is treated as `0`, and `unmet_demand_i` is fixed to `0` for
those non-demand items. In hard demand mode, demanded items also have
`unmet_demand_i = 0`, so infeasible targets produce structured non-optimal or
infeasible results instead of an optimal result with shortage. Surplus disposal
is allowed in v1 by the nonnegative `surplus_i` variable with zero disposal cost.

### Objective

Minimize the sum of named objective components:

```text
raw_cost = sum_i supply_cost_i * external_supply_i
production_cost = sum_r production_cost_r * x_r
unmet_demand_penalty = sum_i unmet_demand_penalty_rate * unmet_demand_i
flow_cost = 0
port_cost = 0
cluster_cost = 0
duplication_cost = 0
```

The inactive logistics terms are reported as zero for this LP so result objects
have the same objective component names as later logistics-aware optimizers.

### Post-solve cluster diagnostics

Successful global LP solves also report diagnostic-only cluster/logistics data.
These diagnostics are computed after the LP solution is loaded. They are not
decision variables, constraints, or objective terms in the LP, and they do not
change selected recipe rates. For a diagnostic-only result:

```text
objective_value = raw_cost + production_cost + unmet_demand_penalty
flow_cost = 0
port_cost = 0
cluster_cost = 0
duplication_cost = 0
```

The diagnostic payload separately reports:

```text
base_objective_value = objective_value
diagnostic_total = diagnostic_flow_cost
                 + diagnostic_port_cost
                 + diagnostic_cluster_cost
                 + diagnostic_duplication_cost
combined_diagnostic_objective_value = base_objective_value + diagnostic_total
```

`combined_diagnostic_objective_value` is for comparison and explanation only; it
is not the objective optimized by the solver.

#### Active recipes and fixed diagnostic clusters

Let `eps = 1e-9`. A recipe is active for cluster diagnostics when:

```text
x_r > eps
```

Only active recipes are included in solver-provided cluster metadata. Diagnostic
clusters are deterministic and fixed after the solve:

1. Partition active recipes by recipe category.
2. Within each category, connect two recipes if one directly produces an item or
   fluid consumed by the other.
3. Each connected component is a diagnostic cluster.

Cross-category producer/consumer relationships remain boundary flows instead of
merging categories into one cluster. This keeps the first diagnostic heuristic
simple and avoids turning dense dependency graphs into one large cluster.

#### Cluster item nets and boundary rows

For each cluster `c` and item or fluid `i`, compute the solved net cluster flow:

```text
net_ci = sum_{r in c} a_ir * x_r
```

Boundary rows are reported for each item or fluid present in the active recipes'
coefficients:

- `net_ci > eps`: boundary output, quantity `net_ci`.
- `net_ci < -eps`: boundary input, quantity `net_ci`.
- `abs(net_ci) <= eps`: zero-net row, quantity `0`, visible in diagnostics but
  with zero flow and port cost.

Zero-net rows are retained so users can see when local production and
consumption cancel inside a cluster. Boundary rows classify each item as either
input or output in this first implementation; bidirectional ports for the same
cluster item are not modeled.

#### Diagnostic cost defaults

The first diagnostic defaults are intentionally simple:

```text
flow_cost_per_quantity = 1
port_cost_per_boundary_type = 100
recipe_size_penalty = 10
boundary_type_size_penalty = 25
target_active_recipes = [5, 15]
target_boundary_item_types = [3, 8]
```

Port/type cost is intentionally much larger than flow quantity cost because the
first heuristic should emphasize reducing distinct boundary item types before
small throughput changes.

For nonzero boundary rows, diagnostic flow cost is based on absolute net
quantity and diagnostic port cost is based on distinct nonzero-net boundary item
types. If one item has both output rows and input rows across clusters, the
matched quantity is treated as an approximate cross-cluster exchange: half of the
matched flow and port cost is attributed to output-side clusters and half to
input-side clusters. Unmatched boundary quantity remains attributed to the owning
cluster as external/final boundary diagnostic cost.

This attribution is a diagnostic approximation inferred from solved item nets,
not exact routing, transport, or layout. There are no transport variables in the
current LP.

Cluster size diagnostics are scalar penalties only. They do not reshape clusters
or make a solve infeasible:

```text
recipe_count_penalty_c = recipe_size_penalty
                       * max(0, target_min_recipes - active_recipe_count_c,
                                active_recipe_count_c - target_max_recipes)

boundary_type_penalty_c = boundary_type_size_penalty
                        * max(0, target_min_boundary_types - boundary_type_count_c,
                                 boundary_type_count_c - target_max_boundary_types)

diagnostic_cluster_cost_c = recipe_count_penalty_c + boundary_type_penalty_c
```

`diagnostic_duplication_cost` is currently reported as `0` because this phase has
no duplicated-recipe or duplicated-production model.

Failure, infeasible, unbounded, non-optimal, solver-unavailable, and unexpected
error results do not emit cluster diagnostics.

### Sparse graph clustering diagnostics

Sparse clustering is also a post-solve explanation layer. It assigns solved active
recipes to clusters using a net-balance port objective: positive cluster item net is
an output net port, negative net is an input net port, and near-zero net is no port.
The sparse objective is diagnostic-only and does not add LP variables, constraints,
or global objective terms. Recipe-to-recipe sparse graph flows remain proportional
diagnostics/affinity hints rather than exact routed crossing flow. Behavior, tuning
fields, caps, and limitations are documented in
`docs/sparse_graph_clustering.md`.

### Solver status and failures

The solver must not silently accept infeasible or non-optimal statuses. The
global recipe LP implementation uses a structured result object for
solver-unavailable, infeasible, unbounded, or non-optimal termination. Successful
results include objective value, objective components, selected `x_r`, external
supplies, unmet demand, surplus, balance residual diagnostics, and post-solve
cluster diagnostics when available.
