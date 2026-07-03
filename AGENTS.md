# AGENTS.md

## Project summary

This repository implements an experimental hierarchical factory-planning optimizer for Factorio-style recipe systems, especially large recursive modpacks such as Pyanodon.

The first goal is not blueprint generation. The first goal is an abstract optimizer that alternates between:

1. recipe and flow optimization;
2. construction of a process graph or hypergraph;
3. hierarchical clustering of factories;
4. logistics-aware reoptimization with port and inter-cluster flow costs.

Spoilage, exact tile placement, train scheduling, neural networks, and direct Factorio blueprint generation are out of scope until the core alternating optimizer is stable and tested.

## Core concept

The optimizer should produce a hierarchical abstract factory plan:

* Level 0: small production cells with complicated local multi-item logistics.
* Level 1: factory districts.
* Level 2: global logistics between districts.

The intended behavior is:

* keep complicated many-item flows inside low-level clusters;
* expose only a small number of high-throughput ports at high levels;
* allow slightly less raw-efficient recipes when they simplify logistics;
* allow small processes to be duplicated when this is cheaper than long-distance transport.

## Development priorities

Prioritize correctness, inspectability, and small tested models over performance.

Implement in this order:

1. data schema for items, recipes, demands, sources, and costs;
2. toy examples;
3. global recipe LP;
4. active process graph construction;
5. simple clustering;
6. cluster-aware flow optimization;
7. alternating optimization loop;
8. diagnostics and reports;
9. improved hypergraph partitioning;
10. MILP port variables;
11. larger Factorio/Pyanodon data import.

Do not implement neural networks, blueprint generation, GUI, or exact physical layout unless explicitly requested in a task.

## Mathematical model conventions

Use the following notation consistently in docs and comments:

* `i`: item or fluid.
* `r`: recipe or process variant.
* `C`: cluster.
* `ell`: hierarchy level.
* `x_r`: execution rate of recipe `r`.
* `a_ir`: net production coefficient of item `i` in recipe `r`.
* `f_iAB`: flow of item `i` from cluster `A` to cluster `B`.
* `p_C_i_ell`: binary or relaxed variable indicating that item `i` crosses cluster `C` at level `ell`.

A recipe coefficient is positive for output and negative for input.

Global balance convention:

```text
sum_r a_ir * x_r + external_supply_i = final_demand_i
```

Cluster-local balance convention:

```text
local_production + incoming_flow - outgoing_flow = local_demand
```

## Objective terms

Keep the objective decomposed into named components:

* `raw_cost`
* `production_cost`
* `flow_cost`
* `port_cost`
* `cluster_cost`
* `duplication_cost`
* `unmet_demand_penalty`

Do not hide all costs inside one opaque scalar. Every report should show the cost breakdown.

## Solver policy

Use Pyomo for symbolic optimization models unless a task explicitly requests another modeling library.

Use HiGHS as the default open-source solver.

Start with LP relaxations where possible. Introduce MILP variables only when the corresponding LP approximation has tests and diagnostics.

Every solver module must expose:

* a pure Python input object;
* a result object;
* objective value;
* named objective components;
* solver status;
* selected recipe rates;
* relevant flows.

Never silently accept infeasible or non-optimal solver statuses. Return a structured failure object or raise a clear exception.

## Clustering policy

Initial clustering may be simple and heuristic.

Acceptable first implementations:

* greedy agglomerative clustering;
* recursive bisection using NetworkX;
* manually supplied clusters for tests.

Hypergraph partitioners such as KaHyPar should be isolated behind an interface, not used directly throughout the codebase.

The clustering interface should accept weighted process/item-flow data and return a cluster tree.

## Alternating optimization policy

The alternating optimizer should be deterministic by default.

It should record all iterations:

* iteration number;
* recipe objective;
* logistics objective;
* port count;
* cluster count;
* changed recipes;
* moved processes;
* convergence reason.

Do not overwrite intermediate plans without preserving diagnostics.

The algorithm should stop when one of the following occurs:

* maximum iterations reached;
* objective improvement below tolerance;
* cluster assignment unchanged;
* recipe set unchanged and objective unchanged;
* infeasible subproblem encountered.

## Data and examples

All examples in `examples/` should be small enough to understand by hand.

Maintain at least these examples:

1. `toy_iron`: one raw source, one product, two recipe alternatives.
2. `toy_byproduct`: one recipe creates an awkward byproduct; another avoids it.
3. `toy_recursive`: a small recursive/cyclic recipe system.
4. `toy_ports`: a recipe that is raw-efficient but requires extra cluster ports.

Tests should verify expected qualitative behavior, for example:

* increasing port cost changes the chosen recipe;
* increasing flow cost encourages co-location;
* allowing duplication can reduce logistics cost;
* the global LP lower bound is no larger than the logistics-aware solution.

## Code style

Use Python 3.12 or newer.

Use type hints everywhere in library code.

Prefer dataclasses or Pydantic models for domain objects.

Keep solver-building code separate from domain data structures.

Avoid global mutable state.

Use clear names rather than abbreviations in public APIs.

Do not optimize performance prematurely.

## Testing commands

Use these commands before committing:

```bash
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
```

If a command is unavailable because dependencies are not installed, report that clearly and do not pretend it passed.

## Documentation requirements

Every new optimization model should have a matching explanation in `docs/mathematical_model.md`.

Every nontrivial heuristic should document:

* input;
* output;
* objective it approximates;
* known failure modes;
* test examples.

Every result object should be easy to serialize to JSON for later comparison.

## What not to do

Do not parse full Factorio prototype data in the first implementation unless the task explicitly asks for it.

Do not implement exact blueprint placement.

Do not add a GUI.

Do not introduce neural networks.

Do not hard-code Pyanodon-specific recipe names into the core optimizer.

Do not make hidden random choices without a seed.

Do not merge recipe optimization, clustering, and reporting into one large function.

## Review checklist

Before finishing a task, check:

1. Are there tests for the new behavior?
2. Does the code run on the toy examples?
3. Is the objective decomposed into named components?
4. Are infeasible solver results handled explicitly?
5. Are diagnostics sufficient to explain the chosen plan?
6. Did the task avoid out-of-scope features?
7. Is the result deterministic?

## Preferred task style for Codex

When modifying this repository, make small reviewable changes.

For each task:

1. inspect the existing architecture;
2. state the intended change briefly;
3. implement the smallest useful version;
4. add or update tests;
5. run available checks;
6. summarize changed files and remaining limitations.

Prefer a correct minimal solver over an impressive but untestable large implementation.
