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

## Internal second-stage optimized clustering MILP

Optimizer-core also contains a second-stage clustering model that can run after a
successful global LP solve. The API exposes it as an explicit opt-in solve
configuration, and the frontend presents it as an optional advanced second pass.
The base LP objective and deterministic `cluster_diagnostics` remain unchanged.
Optimized clustering results are returned in a separate nullable
`optimized_clustering` payload.

The model takes solved global LP recipe rates as fixed totals. A recipe is active
when `x_r > reporting_epsilon`. Candidate cluster slots are one slot per active
recipe, so the model may leave slots unused.

### Variables

For each active recipe `r` and candidate cluster `k`:

```text
y_rk >= 0              continuous allocation of recipe r to cluster k
assign_rk in {0, 1}    whole-recipe assignment indicator for non-splittable recipes
used_k in {0, 1}       whether cluster k is active
under_k, over_k >= 0   soft size violations
```

For every ordered pair of distinct clusters `(k,l)` and item `i`:

```text
flow_kli >= 0          item i sent from cluster k to cluster l
```

For each cluster and item, external boundary variables and directional port
binaries are modeled:

```text
external_in_ki, external_out_ki >= 0
inter_port_in_ki, inter_port_out_ki in {0, 1}
external_port_in_ki, external_port_out_ki in {0, 1}
```

### Constraints and activation semantics

Each active recipe allocation sums exactly to the solved global LP total:

```text
sum_k y_rk = x_r
```

Recipes do not split across clusters by default. For non-splittable recipes,
binary assignment indicators enforce that all of `x_r` appears in exactly one
cluster:

```text
sum_k assign_rk = 1
y_rk <= x_r * assign_rk
```

Recipes listed in `splittable_recipe_ids`, or all recipes when
`allow_recipe_splitting=true`, keep the continuous allocation behavior and may
appear in multiple clusters.

Allocations are tied to cluster activation:

```text
y_rk <= x_r * used_k
sum_r y_rk <= (sum_r x_r) * used_k
```

Unused clusters therefore have size `0`. The soft minimum-size penalty is
conditional on `used_k`, so unused slots do not pay a minimum-size penalty:

```text
under_k >= min_cluster_size * used_k - sum_r y_rk
over_k >= sum_r y_rk - max_cluster_size
```

By default, `max_cluster_size_constraint="soft"`, so `over_k` is penalized but
allowed. With `max_cluster_size_constraint="hard"`, the maximum size becomes a
hard cap instead:

```text
sum_r y_rk <= max_cluster_size * used_k
```

Minimum size remains soft in both modes.

For each cluster and item, item balance uses recipe net coefficients, explicit
pairwise inter-cluster flows, and external boundary flows:

```text
sum_r a_ir y_rk
  + external_in_ki - external_out_ki
  + sum_l flow_lki - sum_l flow_kli = 0
```

Separate inter-cluster and external directional port binaries are tied to
positive flow with a hand-checkable Big-M bound computed from total active
absolute item throughput:

```text
sum_l flow_lki  <= M * inter_port_in_ki
sum_l flow_kli  <= M * inter_port_out_ki
external_in_ki  <= M * external_port_in_ki
external_out_ki <= M * external_port_out_ki
```

### Objective and reported costs

The optimized clustering objective is separate from the global LP objective:

```text
flow_cost = flow_cost_per_quantity
          * (sum_kli flow_kli + sum_ki external_in_ki + external_out_ki)

inter_cluster_port_cost = port_cost_per_item_type
                        * sum_ki (inter_port_in_ki + inter_port_out_ki)

external_port_cost = port_cost_per_item_type
                   * sum_ki (external_port_in_ki + external_port_out_ki)

port_cost = inter_cluster_port_cost + external_port_cost

cluster_size_penalty = cluster_size_penalty_weight * sum_k (under_k + over_k)
duplication_cost = 0
```

The result reports `objective_components` with `flow_cost`, `port_cost`,
`cluster_size_penalty`, and `duplication_cost`, plus a detailed breakdown into
inter-cluster flow, external flow, inter-cluster port, external port, size
penalty, and duplication terms. The reconciliation helper requires those totals
to match within `1e-6`.

Reporting trims clusters with no allocation above `reporting_epsilon`. Reported
allocations, flows, external rows, cost breakdowns, and objective components are
recomputed from the retained clusters and retained rows, so trimming is part of
the backend result rather than a frontend display disguise. The raw solver
objective is still preserved as `objective_value`; `objective_reconciliation`
shows whether the retained reported component total matches that raw objective.

External boundary rows are conservative. Current variables are aggregate
balancing variables and are not constrained separately to actual solved raw
supply, final demand, surplus, or unmet-demand quantities, so reported external
rows use the label `aggregate_external_balance`. UI and API consumers should not
present these rows as exact raw-supply or final-demand routes.

### Guardrails, statuses, and known failure modes

Before constructing the MILP, the implementation computes a model-size score from
active recipes, candidate clusters, and items. If it exceeds the guardrail, the
call returns a structured `model_too_large` optimized-clustering result with no
clusters. This prevents accidentally building very large all-pairs item-flow
models.

Optimized clustering statuses are nested and do not imply global LP failure:
`disabled`, `no_active_recipes`, `optimal`, `feasible_non_optimal`,
`timeout_no_incumbent`, `infeasible`, `solver_unavailable`, and
`model_too_large`. A failed global LP omits optimized clustering. A successful
global LP may still return a non-success optimized-clustering status without
failing the solve response. Time-limit and iteration-limit terminations are
reported as `feasible_non_optimal` only when a feasible incumbent can actually be
loaded; otherwise the result is `timeout_no_incumbent` with no clusters. Known
limitations are the dense pairwise-flow formulation, aggregate external balance
labels, optional continuous splitting with no integer machine counts, and no
duplicated-recipe penalty yet (`duplication_cost` is reported as `0`).

API request parameters are opt-in under `optimized_clustering`. When omitted, no
optimized-clustering pass is requested and the response field is `null`. When
enabled, advanced parameters include preset, cost weights, min/max cluster size,
reporting epsilon, solver time limit, `allow_recipe_splitting`, and
`splittable_recipe_ids`. API validation applies the same effective defaults and
bounds as optimizer-core before queuing a solve job.

### Solver status and failures

The solver must not silently accept infeasible or non-optimal statuses. The
global recipe LP implementation uses a structured result object for
solver-unavailable, infeasible, unbounded, or non-optimal termination. Successful
results include objective value, objective components, selected `x_r`, external
supplies, unmet demand, surplus, balance residual diagnostics, and post-solve
cluster diagnostics when available.
