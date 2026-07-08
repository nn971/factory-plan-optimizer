from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    FactoryDataPackage,
    accepted_early_pyanodon_inputs,
    dataset_to_factory_data_package,
)

from factory_plan_optimizer.optimizer.global_recipe_lp import (
    GlobalRecipeLpResult,
    solve_global_recipe_lp,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game_data_extractor.data_contracts import (
        OptimizerRecipeDataset,
        RecipePrototype,
    )

TOLERANCE = 1e-7


@dataclass(frozen=True, slots=True)
class RelaxationStep:
    """One attempted external-input relaxation."""

    added_input: str
    status: str
    unmet_demand: Mapping[str, float]
    selected_recipe_count: int


@dataclass(frozen=True, slots=True)
class PlanningResult:
    """Planning LP result with the package that produced it."""

    result: GlobalRecipeLpResult
    package: FactoryDataPackage
    accepted_input_policy: str
    relaxation_steps: Sequence[RelaxationStep] = field(default_factory=tuple)


def solve_planning_lp(
    dataset: OptimizerRecipeDataset,
    demands_per_second: Mapping[str, float],
    *,
    allow_relax_inputs: bool = False,
    tolerance: float = TOLERANCE,
) -> PlanningResult:
    accepted = list(accepted_early_pyanodon_inputs(dataset))
    policy = "early_pyanodon_raw_ores_water_stone_native_flora_kerogen"
    package = dataset_to_factory_data_package(dataset, demands_per_second, accepted)
    result = solve_global_recipe_lp(package, solve_mode="soft_diagnostics")
    steps: list[RelaxationStep] = []
    if not allow_relax_inputs or not _is_empty_or_unmet(
        result, demands_per_second, tolerance
    ):
        return PlanningResult(result, package, policy, tuple(steps))

    for candidate in _relaxation_candidates(dataset, accepted, demands_per_second):
        accepted.append(candidate)
        package = dataset_to_factory_data_package(dataset, demands_per_second, accepted)
        result = solve_global_recipe_lp(package, solve_mode="soft_diagnostics")
        steps.append(
            RelaxationStep(
                added_input=candidate,
                status=result.status,
                unmet_demand=_nonzero(result.unmet_demand, tolerance),
                selected_recipe_count=len(_nonzero(result.recipe_rates, tolerance)),
            )
        )
        if not _is_empty_or_unmet(result, demands_per_second, tolerance):
            break
    return PlanningResult(result, package, policy, tuple(steps))


def _is_empty_or_unmet(
    result: GlobalRecipeLpResult,
    demands: Mapping[str, float],
    tolerance: float,
) -> bool:
    if result.status != "optimal":
        return True
    if any(result.unmet_demand.get(item, 0.0) > tolerance for item in demands):
        return True
    return not any(rate > tolerance for rate in result.recipe_rates.values())


def _relaxation_candidates(  # noqa: C901
    dataset: OptimizerRecipeDataset,
    accepted: Sequence[str],
    demands: Mapping[str, float],
) -> tuple[str, ...]:
    accepted_set = set(accepted)
    producers: dict[str, list[RecipePrototype]] = {}
    for recipe in dataset.recipes:
        for coefficient in recipe.coefficients:
            if coefficient.amount > 0.0:
                producers.setdefault(coefficient.item_name, []).append(recipe)

    ordered: list[str] = []
    seen = set(accepted_set)
    queue = sorted(demands)
    for item_name in queue:
        if item_name not in producers and item_name not in seen:
            ordered.append(item_name)
            seen.add(item_name)

    index = 0
    while index < len(queue):
        item_name = queue[index]
        index += 1
        for recipe in sorted(producers.get(item_name, ()), key=lambda item: item.name):
            inputs = sorted(
                coefficient.item_name
                for coefficient in recipe.coefficients
                if coefficient.amount < 0.0
            )
            for input_name in inputs:
                if input_name in seen:
                    continue
                ordered.append(input_name)
                seen.add(input_name)
                if input_name in producers:
                    queue.append(input_name)

    fallback_consumed = sorted(
        coefficient.item_name
        for recipe in dataset.recipes
        for coefficient in recipe.coefficients
        if coefficient.amount < 0.0 and coefficient.item_name not in seen
    )
    return (*ordered, *fallback_consumed)


def _nonzero(
    values: Mapping[str, float], tolerance: float = TOLERANCE
) -> dict[str, float]:
    return {name: value for name, value in values.items() if abs(value) > tolerance}
