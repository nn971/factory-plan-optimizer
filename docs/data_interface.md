# Optimizer data interface

`FactoryDataPackage` is the canonical optimizer-facing data contract. It is
defined in `game_data_extractor.data_contracts`; optimizer-core and the API may
import that public contract package, but not extractor workflow modules.
Importers and generators may use richer internal models, but optimizer modules
consume only this package shape.

## Top-level package

```json
{
  "schema_version": "factory-data-v2",
  "items": [
    {
      "id": "iron-ore",
      "kind": "item",
      "category": "unknown",
      "unlock_condition": {"type": "unknown", "id": null}
    }
  ],
  "recipes": [
    {
      "id": "smelt-iron-plate",
      "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
      "energy_required": 3.2,
      "ingredients": [{"type": "item", "name": "iron-ore", "amount": 1.0}],
      "results": [{"type": "item", "name": "iron-plate", "amount": 1.0}],
      "production_cost": 0.0,
      "category": "smelting",
      "source_prototype_type": "recipe",
      "source_prototype_name": "smelt-iron-plate",
      "unlock_condition": {"type": "start-unlocked", "id": null}
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
- The canonical schema version is `factory-data-v2`; legacy v1 packages are
  rejected as unsupported. `category` is an
  optional non-empty string with no whitespace and defaults to `unknown`.
- `unlock_condition` is optional and defaults to `{"type": "unknown", "id": null}`.
  Allowed types are `technology`, `start-unlocked`, and `unknown`. Technology
  unlocks require a non-empty technology `id`; start-unlocked and unknown unlocks
  require `id` to be omitted or `null` and serialize with explicit `id: null`.
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

`energy_required` is required and must be a positive finite number. It is
craft/process time metadata in seconds, matching Factorio recipe prototype
language. The initial global LP does not yet use `energy_required`; future machine
count or throughput models are expected to use it.

`ingredients` and `results` are required arrays of object terms preserving the
source recipe shape; the loader never derives them from `coefficients`. Term
quantities use at least one of `amount`, `amount_min`, or `amount_max`, each
positive when present; `probability` is in `[0, 1]`; catalyst amounts,
temperatures, and `fluidbox_index` are nonnegative. Term `type` is `item`,
`fluid`, or `unknown`; item/fluid terms must match the referenced item kind,
while unknown terms may reference any known item ID.

`source_prototype_type` is `recipe` (default) or `boiler`. `source_prototype_name`
defaults to the recipe ID for recipe sources; boiler sources require an explicit
non-empty no-whitespace source name.

`production_cost` is the per-unit cost of `x_r` and contributes to the
`production_cost` objective component.

Importer-generated boiler transforms are intentionally narrow: only `boiler`
prototypes with input/output fluid-box filters are normalized into recipe-like
processes. IDs include the boiler and fluid names (for example,
`boiler-boiler-water-to-steam`) so multiple boilers producing the same fluid pair
do not collide. The transform uses a 1:1 fluid coefficient (`water: -1`,
`steam: 1`) and preserves boiler output `target_temperature` as result term
temperature metadata when present. Because current raw normalization does not yet
model heat capacity, fuel, or burner energy, boiler `energy_required` is a
positive `1.0` second approximation and adapter output sets
`production_cost: 0.0`; solver-visible fuel/energy cost is therefore omitted
until future energy constraints or explicit costs are added.

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

Optimized clustering is reported separately from the global LP result when an API
solve request opts into `optimized_clustering`. Its nested
`objective_components` use these names:

- `flow_cost`
- `port_cost`
- `cluster_size_penalty`
- `duplication_cost`

Optimized clustering intentionally uses `cluster_size_penalty` and does not emit
`cluster_cost`. Its response field is nullable: omitted/not requested optimized
clustering is represented as `optimized_clustering: null`; a successful global LP
can still contain a nested optimized-clustering status such as
`timeout_no_incumbent`, `solver_unavailable`, or `model_too_large` without making
the global LP solve fail.

Optimized clustering external rows currently use the conservative
`aggregate_external_balance` boundary label. These rows explain aggregate model
balance against the outside of the cluster system; they are not exact raw-supply,
final-demand, surplus, or unmet-demand routes.

Sparse graph clustering is a separate explanation-first post-solve feature, not a
new `FactoryDataPackage` field. It assigns active recipes from LP results and
reports capped diagnostic arrays through the solve API. Its compatibility field
`boundary_port_type_count` now means net port count from cluster item balances;
`net_port_count` is the explicit alias. Net-port objective components are reported
under `port_aware_objective` as `port_cost`, `size_penalty`, `flow_cost`, and
`total_score`. External boundary rows expose `source_or_demand_amount`; that value
is diagnostics-only and does not add objective ports. See
`docs/sparse_graph_clustering.md` for behavior, tuning fields, and limitations.

Optimized clustering keeps solved recipe totals fixed. Recipes are assigned whole
to one cluster by default; request parameters may allow all recipes to split with
`allow_recipe_splitting` or allow only specific recipes via
`splittable_recipe_ids`. Backend reporting trims sub-epsilon clusters and
recomputes reported rows/components from retained clusters while preserving the
raw solver objective for reconciliation. `max_cluster_size_constraint` defaults
to `soft`, which reports and penalizes over-max clusters; setting it to `hard`
enforces the maximum cluster size as a cap while keeping minimum size soft.

## Validation rules

The loader rejects packages when:

- `schema_version` is unsupported.
- item IDs or recipe IDs are duplicated.
- any recipe coefficient references an unknown item ID.
- any recipe term references an unknown item ID or an item/fluid kind mismatch.
- any recipe omits positive `energy_required` or required term arrays.
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
- `RecipePrototype.category` -> `recipes[].category`.
- `RecipePrototype.energy_required` -> `recipes[].energy_required`.
- signed `RecipeCoefficient.amount` -> `recipes[].coefficients[item_id]`.
- Recipe `ingredients` and `results` preserve raw term metadata where available,
  including fluid temperature constraints.
- Normal recipe sources use `source_prototype_type: "recipe"` and default
  `source_prototype_name` to the recipe ID.
- Boiler-derived synthetic recipes use `source_prototype_type: "boiler"`, carry
  the boiler prototype name, and currently omit fuel/energy cost via
  `production_cost: 0.0`.
- `RecipePrototype.enabled` -> `recipes[].unlock_condition` of `start-unlocked`.
- `TechnologyPrototype.unlocks` -> recipe `technology` unlock conditions; if
  multiple technologies unlock one recipe, the adapter chooses the sorted first
  technology ID deterministically. Recipes without either source use `unknown`.
- enabled or milestone-filtered recipe set -> included `recipes`.
- `ResourceSource.item_name` and source policy -> `external_supplies` entries
  with cost and optional capacity.
- user scenario targets -> `final_demands`.
- recipe policy or defaults -> `production_cost` and
  `unmet_demand_penalty_rate`.

## v2 limitations

- No process graph, cluster, port, or flow data is included yet.
- No integer variables, machine counts, modules, beacons, quality, spoilage, or
  exact physical layout are represented.
- Surplus disposal is allowed in the initial global LP with zero disposal cost.
  This means byproducts may be discarded unless a later schema/model version adds
  disposal limits or costs.
- External supply policies are item-level only; source locations and logistics
  are intentionally absent.
