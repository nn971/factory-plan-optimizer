from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts.provenance_models import (
    ImportDiagnostic,
    MilestoneDefinition,
    MilestoneRecipeSet,
)
from game_data_extractor.data_contracts.types import DatasetParseError

if TYPE_CHECKING:
    from game_data_extractor.data_contracts.dataset import OptimizerRecipeDataset
    from game_data_extractor.data_contracts.recipe_models import (
        RecipePrototype,
        TechnologyPrototype,
    )
    from game_data_extractor.data_contracts.types import JsonValue


@dataclass(frozen=True, slots=True)
class MilestoneFailure(Exception):  # noqa: N818
    """Structured milestone calculation failure."""

    diagnostics: tuple[ImportDiagnostic, ...]

    def __str__(self) -> str:
        return "; ".join(diagnostic.message for diagnostic in self.diagnostics)


def load_milestone_definitions(text: str) -> dict[str, MilestoneDefinition]:
    try:
        parsed: JsonValue = json.loads(text)
    except JSONDecodeError as error:
        context = "milestone JSON"
        raise DatasetParseError(context, error.msg) from error
    mapping = _as_mapping(parsed, "milestone JSON")
    definitions: dict[str, MilestoneDefinition] = {}
    for value in _array(mapping, "milestones"):
        milestone = _as_mapping(value, "milestone")
        definition = MilestoneDefinition(
            name=_string(milestone, "name"),
            completed_technologies=_strings(milestone, "completed_technologies"),
            include_hidden=_boolean(milestone, "include_hidden", default=False),
        )
        definitions[definition.name] = definition
    return dict(sorted(definitions.items()))


def calculate_milestone_recipe_set(
    dataset: OptimizerRecipeDataset,
    definition: MilestoneDefinition,
) -> MilestoneRecipeSet:
    recipes = {recipe.name: recipe for recipe in dataset.recipes}
    technologies = {technology.name: technology for technology in dataset.technologies}
    diagnostics = [
        ImportDiagnostic(
            severity="error",
            code="unknown_milestone_technology",
            message=(
                f"milestone {definition.name} references unknown technology "
                f"{technology_name}"
            ),
            subject=technology_name,
        )
        for technology_name in definition.completed_technologies
        if technology_name not in technologies
    ]
    if diagnostics:
        raise MilestoneFailure(tuple(diagnostics))

    reachable, closure_diagnostics = _technology_closure(definition, technologies)
    diagnostics.extend(closure_diagnostics)
    available = {
        recipe.name
        for recipe in dataset.recipes
        if recipe.enabled and (definition.include_hidden or not recipe.hidden)
    }
    all_validly_unlocked_recipe_names, unlock_diagnostics = _all_unlocks(
        dataset, recipes
    )
    diagnostics.extend(unlock_diagnostics)

    for technology_name in sorted(reachable):
        technology = technologies[technology_name]
        for unlock in sorted(technology.unlocks, key=lambda item: item.recipe_name):
            recipe = recipes.get(unlock.recipe_name)
            if recipe is None:
                continue
            if definition.include_hidden or not recipe.hidden:
                available.add(recipe.name)

    for recipe in dataset.recipes:
        if recipe.enabled or recipe.name in all_validly_unlocked_recipe_names:
            continue
        diagnostics.append(
            ImportDiagnostic(
                severity="warning",
                code="recipe_missing_unlock_path",
                message=(
                    f"recipe {recipe.name} has no unlock path and is not "
                    "initially enabled"
                ),
                subject=recipe.name,
            )
        )

    return MilestoneRecipeSet(
        milestone=definition.name,
        recipe_names=tuple(sorted(available)),
        diagnostics=tuple(
            sorted(diagnostics, key=lambda item: (item.code, item.subject or ""))
        ),
    )


def _all_unlocks(
    dataset: OptimizerRecipeDataset,
    recipes: dict[str, RecipePrototype],
) -> tuple[set[str], list[ImportDiagnostic]]:
    unlocked_recipe_names: set[str] = set()
    diagnostics: list[ImportDiagnostic] = []
    for technology in dataset.technologies:
        for unlock in sorted(technology.unlocks, key=lambda item: item.recipe_name):
            recipe = recipes.get(unlock.recipe_name)
            if recipe is None:
                diagnostics.append(
                    ImportDiagnostic(
                        severity="warning",
                        code="recipe_unlock_missing_recipe",
                        message=(
                            f"technology {technology.name} unlocks missing recipe "
                            f"{unlock.recipe_name}"
                        ),
                        subject=unlock.recipe_name,
                    )
                )
                continue
            unlocked_recipe_names.add(recipe.name)
    return unlocked_recipe_names, diagnostics


def _technology_closure(
    definition: MilestoneDefinition,
    technologies: dict[str, TechnologyPrototype],
) -> tuple[set[str], list[ImportDiagnostic]]:
    reachable: set[str] = set()
    visiting: set[str] = set()
    diagnostics: list[ImportDiagnostic] = []

    def visit(technology_name: str) -> None:
        if technology_name in reachable:
            return
        if technology_name in visiting:
            diagnostic = ImportDiagnostic(
                severity="error",
                code="technology_prerequisite_cycle",
                message=f"technology prerequisite cycle reaches {technology_name}",
                subject=technology_name,
            )
            raise MilestoneFailure((diagnostic,))
        visiting.add(technology_name)
        technology = technologies[technology_name]
        for prerequisite in sorted(technology.prerequisites):
            if prerequisite not in technologies:
                diagnostics.append(
                    ImportDiagnostic(
                        severity="warning",
                        code="technology_missing_prerequisite",
                        message=(
                            f"technology {technology.name} references missing "
                            f"prerequisite {prerequisite}"
                        ),
                        subject=prerequisite,
                    )
                )
                continue
            visit(prerequisite)
        visiting.remove(technology_name)
        reachable.add(technology_name)

    for technology_name in sorted(definition.completed_technologies):
        visit(technology_name)
    return reachable, diagnostics


def _as_mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise DatasetParseError(context, "expected JSON object")


def _array(mapping: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = mapping.get(key, [])
    if isinstance(value, list):
        return value
    raise DatasetParseError(key, "expected JSON array")


def _strings(mapping: dict[str, JsonValue], key: str) -> list[str]:
    values = _array(mapping, key)
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise DatasetParseError(key, "expected string array")
        strings.append(value)
    if len(strings) == len(values):
        return strings
    raise DatasetParseError(key, "expected string array")


def _string(mapping: dict[str, JsonValue], key: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string")


def _boolean(mapping: dict[str, JsonValue], key: str, *, default: bool) -> bool:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        return value
    raise DatasetParseError(key, "expected boolean")
