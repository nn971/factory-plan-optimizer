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

### Solver status and failures

The solver must not silently accept infeasible or non-optimal statuses. In Phase
3, the global recipe LP implementation should use a structured result object for
solver-unavailable, infeasible, unbounded, or non-optimal termination. Successful
results should include objective value, objective components, selected `x_r`,
external supplies, unmet demand, surplus, and balance residual diagnostics.
