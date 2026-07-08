from __future__ import annotations

from typing import TYPE_CHECKING

from factory_plan_api.dtos import (
    ExplorerItemDto,
    ExplorerOverviewDto,
    ExplorerRecipeDto,
    ExplorerRecipeIODto,
    ExplorerRecipeLinkDto,
    ExplorerResponseDto,
    UnlockConditionDto,
)

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import FactoryDataPackage, Item, Recipe


def explorer_from_package(
    package: FactoryDataPackage,
    package_id: str,
) -> ExplorerResponseDto:
    """Build an explorer read model from a trusted factory data package."""
    item_by_id = {item.id: item for item in package.items}
    produced_by: dict[str, list[Recipe]] = {item.id: [] for item in package.items}
    consumed_by: dict[str, list[Recipe]] = {item.id: [] for item in package.items}

    for recipe in package.recipes:
        for item_id, coefficient in recipe.coefficients.items():
            if coefficient > 0.0:
                produced_by.setdefault(item_id, []).append(recipe)
            elif coefficient < 0.0:
                consumed_by.setdefault(item_id, []).append(recipe)

    items = [
        ExplorerItemDto(
            id=item.id,
            kind=item.kind,
            category=item.category,
            unlock_condition=_unlock_condition_dto(item),
            produced_by=_recipe_links(produced_by.get(item.id, [])),
            consumed_by=_recipe_links(consumed_by.get(item.id, [])),
        )
        for item in sorted(package.items, key=_category_id_key)
    ]
    recipes = [
        ExplorerRecipeDto(
            id=recipe.id,
            category=recipe.category,
            unlock_condition=_unlock_condition_dto(recipe),
            production_cost=recipe.production_cost,
            inputs=_recipe_io(recipe, item_by_id, sign=-1),
            outputs=_recipe_io(recipe, item_by_id, sign=1),
        )
        for recipe in sorted(package.recipes, key=_category_id_key)
    ]
    return ExplorerResponseDto(
        package_id=package_id,
        overview=ExplorerOverviewDto(
            item_count=len(package.items),
            fluid_count=sum(1 for item in package.items if item.kind == "fluid"),
            recipe_count=len(package.recipes),
            item_categories=sorted({item.category for item in package.items}),
            recipe_categories=sorted({recipe.category for recipe in package.recipes}),
        ),
        items=items,
        recipes=recipes,
    )


def _unlock_condition_dto(item_or_recipe: Item | Recipe) -> UnlockConditionDto:
    unlock = item_or_recipe.unlock_condition
    return UnlockConditionDto(type=unlock.type, id=unlock.id)


def _recipe_links(recipes: list[Recipe]) -> list[ExplorerRecipeLinkDto]:
    return [
        ExplorerRecipeLinkDto(id=recipe.id, category=recipe.category)
        for recipe in sorted(recipes, key=_category_id_key)
    ]


def _recipe_io(
    recipe: Recipe,
    item_by_id: dict[str, Item],
    *,
    sign: int,
) -> list[ExplorerRecipeIODto]:
    rows: list[ExplorerRecipeIODto] = []
    for item_id, coefficient in recipe.coefficients.items():
        if coefficient * sign <= 0.0:
            continue
        item = item_by_id[item_id]
        rows.append(
            ExplorerRecipeIODto(
                item_id=item.id,
                kind=item.kind,
                category=item.category,
                amount=abs(coefficient),
            ),
        )
    return sorted(rows, key=lambda row: (row.category, row.item_id))


def _category_id_key(item_or_recipe: Item | Recipe) -> tuple[str, str]:
    return (item_or_recipe.category, item_or_recipe.id)
