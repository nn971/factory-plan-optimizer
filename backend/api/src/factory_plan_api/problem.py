from __future__ import annotations

from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    ExternalSupply,
    FactoryDataPackage,
    ItemKind,
)

from factory_plan_api.dtos import ExternalInputDto, ItemDto, ProblemDto, SolveResultDto

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.global_recipe_lp import GlobalRecipeLpResult


DEFAULT_PACKAGE_ID = "default-first-3-science-v1"
DEFAULT_SCENARIO_ID = "first-3-science-v1"
DEFAULT_SCENARIO_LABEL = "First 3 science packs"
DEFAULT_EXTERNAL_INPUT_CAPACITY = 100_000.0
FREE_RESOURCE_DEFAULTS = frozenset({"water"})
SCIENCE_TARGET_DEMANDS = [
    "automation-science-pack",
    "logistic-science-pack",
    "py-science-pack-1",
]


def problem_from_package(
    package: FactoryDataPackage,
    package_id: str | None = None,
    scenario_id: str | None = None,
    scenario_label: str = DEFAULT_SCENARIO_LABEL,
) -> ProblemDto:
    target_demands = _target_demands(package)
    raw_input_candidates = infer_raw_input_candidates(package, target_demands)
    return ProblemDto(
        package_id=package_id,
        scenario_id=scenario_id or package_id,
        scenario_label=scenario_label,
        items=[ItemDto(id=item.id, kind=item.kind) for item in package.items],
        demands=dict(package.final_demands),
        target_demands=target_demands,
        # Compatibility alias for existing clients; new clients should prefer
        # raw_input_candidates because it includes source/default metadata.
        external_inputs=raw_input_candidates,
        raw_input_candidates=raw_input_candidates,
        recipe_ids=[recipe.id for recipe in package.recipes],
    )


def infer_raw_input_candidates(
    package: FactoryDataPackage,
    target_demands: list[str] | None = None,
) -> list[ExternalInputDto]:
    target_ids = set(target_demands or [])
    produced_ids = {
        item_id
        for recipe in package.recipes
        for item_id, coefficient in recipe.coefficients.items()
        if coefficient > 0.0
    }
    item_ids = [item.id for item in package.items]
    kind_by_item_id = {item.id: item.kind for item in package.items}
    fluid_ids = {
        item_id for item_id, kind in kind_by_item_id.items() if kind == "fluid"
    }
    unproduced_ids = {
        item_id
        for item_id in item_ids
        if item_id not in produced_ids and item_id not in target_ids
    }
    candidate_ids = set(package.external_supplies) | unproduced_ids | fluid_ids
    if "raw-coal" in item_ids:
        candidate_ids.discard("coal")
    return [
        _raw_input_candidate(
            item_id,
            kind_by_item_id[item_id],
            package.external_supplies.get(item_id),
            is_inferred_fluid=item_id in fluid_ids and item_id not in unproduced_ids,
        )
        for item_id in item_ids
        if item_id in candidate_ids and item_id not in target_ids
    ]


def _raw_input_candidate(
    item_id: str,
    kind: ItemKind,
    supply: ExternalSupply | None,
    *,
    is_inferred_fluid: bool = False,
) -> ExternalInputDto:
    if supply is not None:
        return ExternalInputDto(
            item_id=item_id,
            kind=kind,
            enabled=True,
            cost=supply.cost,
            capacity=supply.capacity
            if supply.capacity is not None
            else DEFAULT_EXTERNAL_INPUT_CAPACITY,
            source="package_external_supply",
            default_approved=True,
        )
    return ExternalInputDto(
        item_id=item_id,
        kind=kind,
        enabled=False,
        cost=0.0 if item_id in FREE_RESOURCE_DEFAULTS else 1.0,
        capacity=DEFAULT_EXTERNAL_INPUT_CAPACITY,
        source="inferred_fluid" if is_inferred_fluid else "inferred_unproduced",
        default_approved=False,
    )


def _target_demands(package: FactoryDataPackage) -> list[str]:
    item_ids = {item.id for item in package.items}
    if all(target_id in item_ids for target_id in SCIENCE_TARGET_DEMANDS):
        return list(SCIENCE_TARGET_DEMANDS)
    return list(package.final_demands)


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
