from __future__ import annotations

from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    ExternalSupply,
    FactoryDataPackage,
    ItemKind,
)

from factory_plan_api.dtos import (
    ClusterDiagnosticsDto,
    ExternalInputDto,
    ItemDto,
    MilestoneDto,
    ProblemDto,
    SolveResultDto,
)

if TYPE_CHECKING:
    from factory_plan_optimizer.optimizer.global_recipe_lp import GlobalRecipeLpResult


DEFAULT_PACKAGE_ID = "default-first-3-science-v1"
DEFAULT_SCENARIO_ID = "first-3-science-v1"
DEFAULT_SCENARIO_LABEL = "First 3 science packs"
DEFAULT_EXTERNAL_INPUT_CAPACITY = 100_000.0
FREE_RESOURCE_DEFAULTS = frozenset({"water"})
SCIENCE_TARGET_DEMANDS = [
    "automation-science-pack",
    "py-science-pack-1",
    "logistic-science-pack",
    "py-science-pack-2",
    "military-science-pack",
    "chemical-science-pack",
]
SCIENCE_TARGET_ORDER = {
    item_id: index for index, item_id in enumerate(SCIENCE_TARGET_DEMANDS)
}


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
        milestones=_milestone_dtos(package),
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
            source="default_input",
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
    science_pack_ids = [item.id for item in package.items if "science-pack" in item.id]
    if science_pack_ids:
        return sorted(
            science_pack_ids,
            key=lambda item_id: (
                SCIENCE_TARGET_ORDER.get(item_id, len(SCIENCE_TARGET_ORDER)),
                item_id,
            ),
        )
    return list(package.final_demands)


def package_with_edits(
    package: FactoryDataPackage,
    demands: dict[str, float],
    external_inputs: list[ExternalInputDto],
    selected_milestone: str | None = None,
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
    recipes = package.recipes
    if selected_milestone is not None and selected_milestone.strip():
        milestone_id = selected_milestone.strip()
        milestone = next(
            (
                candidate
                for candidate in package.milestones
                if candidate.milestone == milestone_id
            ),
            None,
        )
        if milestone is None:
            raise ValueError(f"unknown selected milestone: {milestone_id}")
        recipe_ids = set(milestone.recipe_names)
        recipes = tuple(recipe for recipe in package.recipes if recipe.id in recipe_ids)
    return FactoryDataPackage(
        schema_version=package.schema_version,
        items=package.items,
        recipes=recipes,
        final_demands=demands,
        external_supplies=supplies,
        unmet_demand_penalty_rate=package.unmet_demand_penalty_rate,
        milestones=package.milestones,
    )


def _milestone_dtos(package: FactoryDataPackage) -> list[MilestoneDto]:
    recipe_ids = {recipe.id for recipe in package.recipes}
    return [
        MilestoneDto(
            item_id=milestone.milestone,
            recipe_ids=[
                recipe_id
                for recipe_id in milestone.recipe_names
                if recipe_id in recipe_ids
            ],
        )
        for milestone in package.milestones
    ]


def result_to_dto(result: GlobalRecipeLpResult) -> SolveResultDto:
    cluster_diagnostics = _cluster_diagnostics_to_dto(
        getattr(result, "cluster_diagnostics", {}),
    )
    return SolveResultDto(
        solver_status=result.status,
        objective_value=result.objective_value,
        objective_components=dict(result.objective_components),
        recipe_rates=dict(result.recipe_rates),
        external_supplies=dict(result.external_supplies),
        unmet_demand=dict(result.unmet_demand),
        surplus=dict(result.surplus),
        balance_residuals=dict(result.balance_residuals),
        cluster_diagnostics=cluster_diagnostics,
        message=result.message,
        details=result.details,
    )


def _cluster_diagnostics_to_dto(
    diagnostics: object,
) -> ClusterDiagnosticsDto | None:
    if not diagnostics:
        return None
    return ClusterDiagnosticsDto.model_validate(diagnostics)
