from __future__ import annotations

from typing import TYPE_CHECKING

from game_data_extractor.data_contracts.factory_data import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_data_extractor.data_contracts.dataset import OptimizerRecipeDataset
    from game_data_extractor.data_contracts.recipe_models import RecipePrototype

TOLERANCE = 1e-7
UNMET_DEMAND_PENALTY_RATE = 1e9
EXACT_ACCEPTED_INPUTS = frozenset({"water", "stone", "native-flora", "kerogen"})


def accepted_early_pyanodon_inputs(dataset: OptimizerRecipeDataset) -> tuple[str, ...]:
    """Return deterministic raw-ish external inputs for early Pyanodon planning."""
    item_names = {item.name for item in dataset.items}
    item_names.update(source.item_name for source in dataset.resource_sources)
    accepted = {
        name
        for name in item_names
        if name in EXACT_ACCEPTED_INPUTS
        or name.endswith("-ore")
        or name.startswith("ore-")
    }
    return tuple(sorted(accepted))


def dataset_to_factory_data_package(
    dataset: OptimizerRecipeDataset,
    demands_per_second: Mapping[str, float],
    accepted_inputs: Sequence[str] | None = None,
) -> FactoryDataPackage:
    accepted = tuple(accepted_inputs or accepted_early_pyanodon_inputs(dataset))
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=tuple(
            Item(id=item.name, kind=item.prototype_type) for item in dataset.items
        ),
        recipes=tuple(_convert_recipe(recipe) for recipe in dataset.recipes),
        final_demands=dict(demands_per_second),
        external_supplies={name: ExternalSupply(cost=1.0) for name in accepted},
        unmet_demand_penalty_rate=UNMET_DEMAND_PENALTY_RATE,
    )


def _convert_recipe(recipe: RecipePrototype) -> Recipe:
    coefficients: dict[str, float] = {}
    for coefficient in recipe.coefficients:
        coefficients[coefficient.item_name] = (
            coefficients.get(coefficient.item_name, 0.0) + coefficient.amount
        )
    return Recipe(
        id=recipe.name,
        coefficients={
            name: value
            for name, value in coefficients.items()
            if abs(value) > TOLERANCE
        },
        production_cost=0.0,
    )
