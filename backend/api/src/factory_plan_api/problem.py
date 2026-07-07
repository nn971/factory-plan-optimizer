from __future__ import annotations

from typing import TYPE_CHECKING

from factory_plan_optimizer.optimizer.models import (
    ExternalSupply,
    FactoryDataPackage,
)

from factory_plan_api.dtos import ExternalInputDto, ItemDto, ProblemDto, SolveResultDto

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.global_recipe_lp import GlobalRecipeLpResult


def problem_from_package(package: FactoryDataPackage) -> ProblemDto:
    external_inputs = []
    for item in package.items:
        supply = package.external_supplies.get(item.id)
        external_inputs.append(
            ExternalInputDto(
                item_id=item.id,
                enabled=supply is not None,
                cost=0.0 if supply is None else supply.cost,
                capacity=None if supply is None else supply.capacity,
            ),
        )
    return ProblemDto(
        items=[ItemDto(id=item.id, kind=item.kind) for item in package.items],
        demands=dict(package.final_demands),
        external_inputs=external_inputs,
        recipe_ids=[recipe.id for recipe in package.recipes],
    )


def package_with_edits(
    package: FactoryDataPackage,
    demands: dict[str, float],
    external_inputs: list[ExternalInputDto],
) -> FactoryDataPackage:
    item_ids = {item.id for item in package.items}
    unknown_demand_ids = sorted(set(demands) - item_ids)
    if unknown_demand_ids:
        joined_ids = ", ".join(unknown_demand_ids)
        raise ValueError(f"unknown demand item id(s): {joined_ids}")
    external_input_ids = [external_input.item_id for external_input in external_inputs]
    unknown_external_input_ids = sorted(set(external_input_ids) - item_ids)
    if unknown_external_input_ids:
        joined_ids = ", ".join(unknown_external_input_ids)
        raise ValueError(f"unknown external input item id(s): {joined_ids}")
    duplicate_external_input_ids = sorted(
        item_id
        for item_id in set(external_input_ids)
        if external_input_ids.count(item_id) > 1
    )
    if duplicate_external_input_ids:
        joined_ids = ", ".join(duplicate_external_input_ids)
        raise ValueError(f"duplicate external_inputs entries: {joined_ids}")
    supplies = {
        external_input.item_id: ExternalSupply(
            cost=external_input.cost,
            capacity=external_input.capacity,
        )
        for external_input in external_inputs
        if external_input.enabled
    }
    return FactoryDataPackage(
        schema_version=package.schema_version,
        items=package.items,
        recipes=package.recipes,
        final_demands=demands,
        external_supplies=supplies,
        unmet_demand_penalty_rate=package.unmet_demand_penalty_rate,
    )


def result_to_dto(result: GlobalRecipeLpResult) -> SolveResultDto:
    return SolveResultDto(
        solver_status=result.status,
        objective_value=result.objective_value,
        objective_components=dict(result.objective_components),
        recipe_rates=dict(result.recipe_rates),
        external_supplies=dict(result.external_supplies),
        unmet_demand=dict(result.unmet_demand),
        surplus=dict(result.surplus),
        balance_residuals=dict(result.balance_residuals),
        message=result.message,
        details=result.details,
    )
