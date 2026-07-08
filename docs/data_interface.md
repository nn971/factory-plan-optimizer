# Optimizer data interface

`FactoryDataPackage` is the canonical optimizer-facing data contract. It is
defined in `game_data_extractor.data_contracts`; optimizer-core and the API may
import that public contract package, but not extractor workflow modules.
Importers and generators may use richer internal models, but optimizer modules
consume only this package shape.

## Top-level package

```json
{
  "schema_version": "factory-data-v1",
  "items": [{"id": "iron-ore", "kind": "item"}],
  "recipes": [
    {
      "id": "smelt-iron-plate",
      "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
      "production_cost": 0.0
    }
  ],
  "final_demands": {"iron-plate": 60.0},
  "external_supplies": {
    "iron-ore": {"cost": 1.0, "capacity": null}
  },
  "unmet_demand_penalty_rate": 1000000.0
}
```

Required top-level fields are `schema_version`, `items`, `recipes`,
`final_demands`, `external_supplies`, and `unmet_demand_penalty_rate`.

The first canonical example package is
`examples/data/toy_iron.factory-data.json`.

## IDs, units, and rates

- All IDs are stable non-empty strings with no whitespace and are unique within
  their collection.
- Items represent both solid items and fluids. `kind` is one of `item`, `fluid`,
  or `unknown`. It is optional; the loader defaults omitted `kind` to `unknown`.
- Rates are continuous amounts per second. Adapters must convert coefficients,
  demands, supplies, and costs to this common rate basis before writing the
  package.
- `x_r` is the execution rate of recipe `r`; if `x_r = 1`, the recipe contributes
  exactly its signed coefficients per second.

## Recipe coefficients and costs

Each recipe has a `coefficients` object mapping `item_id` to signed `a_ir`:

- `a_ir > 0`: recipe `r` produces item `i`.
- `a_ir < 0`: recipe `r` consumes item `i`.
- zero coefficients are rejected by the loader and should be omitted.

`production_cost` is the per-unit cost of `x_r` and contributes to the
`production_cost` objective component. It is required in v1.

## Demands, external supplies, and penalties

- `final_demands[item_id]` is requested final demand for item `i`.
- `external_supplies[item_id].cost` is the per-unit raw/external supply cost and
  contributes to `raw_cost`.
- `external_supplies[item_id].capacity` is optional. `null` or omitted means no
  finite upper bound. A numeric value is an upper bound on supply rate.
- `unmet_demand_penalty_rate` is the per-unit penalty for unmet final demand in
  the initial global LP's `soft_diagnostics` solve mode. In default
  `hard_demand` mode, unmet demand is fixed to `0` so infeasible targets are
  reported as structured non-optimal/infeasible results. In soft diagnostics,
  `unmet_demand_i` may be positive only for items listed in `final_demands`; it
  is fixed to `0` for all other items.

## Objective component names

All optimizer results should report these named components, even when inactive:

- `raw_cost`
- `production_cost`
- `flow_cost`
- `port_cost`
- `cluster_cost`
- `duplication_cost`
- `unmet_demand_penalty`

For the initial global recipe LP, logistics terms (`flow_cost`, `port_cost`,
`cluster_cost`, and `duplication_cost`) are inactive and reported as `0.0`.

## Validation rules

The loader rejects packages when:

- `schema_version` is unsupported.
- item IDs or recipe IDs are duplicated.
- any recipe coefficient references an unknown item ID.
- any final demand or external supply references an unknown item ID.
- numeric rates, costs, capacities, or penalties are negative where nonnegative
  values are required.
- a recipe has no nonzero coefficients or includes an individual zero
  coefficient.

The JSON Schema in `schemas/factory_data.schema.json` documents the wire shape;
semantic validation by the loader remains authoritative.

## Generator/importer versus optimizer responsibilities

The `backend/game-data-extractor` package and `game-data-extractor` CLI are
responsible for reading Factorio/mod data, applying
startup settings and milestone filters, normalizing recipe coefficients, choosing
which recipes and sources are exposed, converting units, and writing a
`FactoryDataPackage`.

The optimizer is responsible for validating the canonical package, building LP or
later logistics-aware models, solving them, and returning structured results.
Solver failures should be represented by a structured result object. The
optimizer must not import or depend on importer-internal models.

## Adapter mapping from importer datasets

The current importer milestone export is still importer/generator output. An
adapter should map it into `FactoryDataPackage` as follows:

- `ItemPrototype.name` -> `items[].id`.
- item/fluid prototype type -> `items[].kind` when available, otherwise
  `unknown`.
- `RecipePrototype.name` -> `recipes[].id`.
- signed `RecipeCoefficient.amount` -> `recipes[].coefficients[item_id]`.
- enabled or milestone-filtered recipe set -> included `recipes`.
- `ResourceSource.item_name` and source policy -> `external_supplies` entries
  with cost and optional capacity.
- user scenario targets -> `final_demands`.
- recipe policy or defaults -> `production_cost` and
  `unmet_demand_penalty_rate`.

## v1 limitations

- No process graph, cluster, port, or flow data is included yet.
- No integer variables, machine counts, modules, beacons, quality, spoilage, or
  exact physical layout are represented.
- Surplus disposal is allowed in the initial global LP with zero disposal cost.
  This means byproducts may be discarded unless a later schema/model version adds
  disposal limits or costs.
- External supply policies are item-level only; source locations and logistics
  are intentionally absent.
