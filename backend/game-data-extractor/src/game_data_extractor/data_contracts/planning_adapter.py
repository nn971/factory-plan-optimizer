from __future__ import annotations

from typing import TYPE_CHECKING, cast

from game_data_extractor.data_contracts.factory_data import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
    RecipeTerm,
    UnlockCondition,
)
from game_data_extractor.data_contracts.milestones import calculate_milestone_recipe_set
from game_data_extractor.data_contracts.provenance_models import (
    MilestoneDefinition,
    MilestoneRecipeSet,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_data_extractor.data_contracts.dataset import OptimizerRecipeDataset
    from game_data_extractor.data_contracts.factory_data import RecipeTermType
    from game_data_extractor.data_contracts.recipe_models import (
        ItemPrototype,
        RawRecipeTerm,
        RecipePrototype,
    )

TOLERANCE = 1e-7
UNMET_DEMAND_PENALTY_RATE = 1e9
EXACT_ACCEPTED_INPUTS = frozenset(
    {
        "kerogen",
        "native-flora",
        "phosphate-rock",
        "raw-coal",
        "stone",
        "sulfur",
        "water",
    },
)
SCIENCE_MILESTONE_ORDER = (
    "automation-science-pack",
    "py-science-pack-1",
    "logistic-science-pack",
    "py-science-pack-2",
    "military-science-pack",
    "chemical-science-pack",
)
SCIENCE_MILESTONE_INDEX = {
    item_id: index for index, item_id in enumerate(SCIENCE_MILESTONE_ORDER)
}


def accepted_early_pyanodon_inputs(dataset: OptimizerRecipeDataset) -> tuple[str, ...]:
    """Return deterministic raw-ish external inputs for early Pyanodon planning."""
    item_names = {item.name for item in dataset.items}
    item_names.update(source.item_name for source in dataset.resource_sources)
    return accepted_early_pyanodon_item_ids(tuple(item_names))


def accepted_early_pyanodon_item_ids(item_ids: Sequence[str]) -> tuple[str, ...]:
    """Return item ids allowed as early Pyanodon external inputs.

    This is the single source of truth for both importer-generated external
    supplies and API raw-input review candidates.
    """
    accepted = {
        item_id
        for item_id in item_ids
        if item_id in EXACT_ACCEPTED_INPUTS
        or item_id.endswith("-ore")
        or item_id.startswith("ore-")
    }
    return tuple(sorted(accepted))


def dataset_to_factory_data_package(
    dataset: OptimizerRecipeDataset,
    demands_per_second: Mapping[str, float],
    accepted_inputs: Sequence[str] | None = None,
) -> FactoryDataPackage:
    accepted = _dedupe_preserving_order(
        accepted_early_pyanodon_inputs(dataset)
        if accepted_inputs is None
        else accepted_inputs,
    )
    technology_by_recipe = _recipe_unlocks_by_technology(dataset)
    items = _canonical_items(dataset)
    item_kinds: dict[str, RecipeTermType] = {
        item.name: cast("RecipeTermType", item.prototype_type) for item in items
    }
    recipes = tuple(
        _convert_recipe(recipe, technology_by_recipe, item_kinds)
        for recipe in dataset.recipes
        if _has_nonzero_coefficients(recipe)
    )
    return FactoryDataPackage(
        schema_version=SCHEMA_VERSION,
        items=tuple(Item(id=item.name, kind=item.prototype_type) for item in items),
        recipes=recipes,
        final_demands=dict(demands_per_second),
        external_supplies={name: ExternalSupply(cost=1.0) for name in accepted},
        raw_input_suggestions=accepted,
        unmet_demand_penalty_rate=UNMET_DEMAND_PENALTY_RATE,
        milestones=_science_milestones(dataset, recipes),
    )


def _dedupe_preserving_order(item_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item_ids))


def _canonical_items(dataset: OptimizerRecipeDataset) -> tuple[ItemPrototype, ...]:
    """Return items with duplicate generated parameter pseudo-items removed."""
    items: list[ItemPrototype] = []
    seen: set[str] = set()
    for item in dataset.items:
        if item.name in seen and item.name.startswith("parameter-"):
            continue
        seen.add(item.name)
        items.append(item)
    return tuple(items)


def _has_nonzero_coefficients(recipe: RecipePrototype) -> bool:
    coefficients: dict[str, float] = {}
    for coefficient in recipe.coefficients:
        coefficients[coefficient.item_name] = (
            coefficients.get(coefficient.item_name, 0.0) + coefficient.amount
        )
    return any(abs(value) > TOLERANCE for value in coefficients.values())


def _recipe_unlocks_by_technology(dataset: OptimizerRecipeDataset) -> dict[str, str]:
    unlocks: dict[str, list[str]] = {}
    for technology in dataset.technologies:
        for unlock in technology.unlocks:
            unlocks.setdefault(unlock.recipe_name, []).append(technology.name)
    return {
        recipe_name: sorted(technology_names)[0]
        for recipe_name, technology_names in unlocks.items()
    }


def _science_milestones(
    dataset: OptimizerRecipeDataset,
    recipes: Sequence[Recipe],
) -> tuple[MilestoneRecipeSet, ...]:
    package_recipe_names = {recipe.id for recipe in recipes}
    milestone_item_ids = sorted(
        (item.name for item in dataset.items if "science-pack" in item.name),
        key=lambda item_id: (
            SCIENCE_MILESTONE_INDEX.get(item_id, len(SCIENCE_MILESTONE_INDEX)),
            item_id,
        ),
    )
    return tuple(
        _science_milestone(dataset, item_id, package_recipe_names)
        for item_id in milestone_item_ids
    )


def _science_milestone(
    dataset: OptimizerRecipeDataset,
    item_id: str,
    package_recipe_names: set[str],
) -> MilestoneRecipeSet:
    completed_technologies = _researchable_technologies(
        dataset,
        allowed_science_packs=_allowed_science_packs(dataset, item_id),
    )
    result = calculate_milestone_recipe_set(
        dataset,
        MilestoneDefinition(
            name=item_id,
            completed_technologies=completed_technologies,
        ),
    )
    return MilestoneRecipeSet(
        milestone=result.milestone,
        recipe_names=tuple(
            recipe_name
            for recipe_name in result.recipe_names
            if recipe_name in package_recipe_names
        ),
        diagnostics=result.diagnostics,
    )


def _allowed_science_packs(
    dataset: OptimizerRecipeDataset,
    milestone_item_id: str,
) -> set[str]:
    science_pack_ids = {
        item.name for item in dataset.items if "science-pack" in item.name
    }
    if milestone_item_id not in SCIENCE_MILESTONE_INDEX:
        return set(science_pack_ids)
    milestone_index = SCIENCE_MILESTONE_INDEX[milestone_item_id]
    return {
        item_id
        for item_id in science_pack_ids
        if SCIENCE_MILESTONE_INDEX.get(item_id, len(SCIENCE_MILESTONE_INDEX))
        <= milestone_index
    }


def _researchable_technologies(
    dataset: OptimizerRecipeDataset,
    *,
    allowed_science_packs: set[str],
) -> tuple[str, ...]:
    technologies = {technology.name: technology for technology in dataset.technologies}
    reachable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for technology in dataset.technologies:
            if (
                technology.name in reachable
                or technology.hidden
                or not technology.enabled
            ):
                continue
            if not set(technology.science_pack_ingredients).issubset(
                allowed_science_packs,
            ):
                continue
            if not all(
                prerequisite in reachable or prerequisite not in technologies
                for prerequisite in technology.prerequisites
            ):
                continue
            reachable.add(technology.name)
            changed = True
    return tuple(sorted(reachable))


def _convert_recipe(
    recipe: RecipePrototype,
    technology_by_recipe: Mapping[str, str],
    item_kinds: Mapping[str, RecipeTermType],
) -> Recipe:
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
        energy_required=recipe.energy_required,
        ingredients=tuple(
            _convert_term(term, item_kinds) for term in recipe.ingredients
        )
        or tuple(
            RecipeTerm(
                type="unknown",
                name=coefficient.item_name,
                amount=-coefficient.amount,
            )
            for coefficient in recipe.coefficients
            if coefficient.amount < -TOLERANCE
        ),
        results=tuple(_convert_term(term, item_kinds) for term in recipe.results)
        or tuple(
            RecipeTerm(
                type="unknown",
                name=coefficient.item_name,
                amount=coefficient.amount,
            )
            for coefficient in recipe.coefficients
            if coefficient.amount > TOLERANCE
        ),
        production_cost=0.0,
        category=recipe.category,
        unlock_condition=_recipe_unlock_condition(recipe, technology_by_recipe),
        source_prototype_type=recipe.source_prototype_type,
        source_prototype_name=recipe.source_prototype_name,
    )


def _convert_term(
    term: RawRecipeTerm,
    item_kinds: Mapping[str, RecipeTermType],
) -> RecipeTerm:
    term_type = term.type
    known_kind = item_kinds.get(term.name)
    if term_type == "unknown" and known_kind is not None:
        term_type = known_kind
    if term_type in {"item", "fluid"} and known_kind != term_type:
        term_type = "unknown"
    return RecipeTerm(
        type=term_type,
        name=term.name,
        amount=term.amount,
        amount_min=term.amount_min,
        amount_max=term.amount_max,
        probability=term.probability,
        catalyst_amount=term.catalyst_amount,
        temperature=term.temperature,
        minimum_temperature=term.minimum_temperature,
        maximum_temperature=term.maximum_temperature,
        fluidbox_index=term.fluidbox_index,
    )


def _recipe_unlock_condition(
    recipe: RecipePrototype,
    technology_by_recipe: Mapping[str, str],
) -> UnlockCondition:
    technology_id = technology_by_recipe.get(recipe.name)
    if technology_id is not None:
        return UnlockCondition(type="technology", id=technology_id)
    if recipe.enabled:
        return UnlockCondition(type="start-unlocked")
    return UnlockCondition(type="unknown")
