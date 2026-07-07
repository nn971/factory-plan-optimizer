import json
from pathlib import Path

import pytest

from factory_plan_optimizer.__main__ import main
from factory_plan_optimizer.import_models import (
    MilestoneRecipeSet,
    OptimizerRecipeDataset,
    RecipePrototype,
    RecipeUnlock,
    TechnologyPrototype,
)
from factory_plan_optimizer.milestones import (
    MilestoneFailure,
    calculate_milestone_recipe_set,
    load_milestone_definitions,
)


def test_milestone_recipe_set_closes_prerequisites_includes_enabled() -> None:
    dataset = _milestone_dataset()
    definitions = load_milestone_definitions(
        '{"milestones":[{"name":"basic-circuits","completed_technologies":["electronics"]}]}',
    )

    result = calculate_milestone_recipe_set(dataset, definitions["basic-circuits"])

    assert result.recipe_names == (
        "copper-cable",
        "manual-enabled",
        "starter-plate",
    )
    assert _diagnostic_subjects(result, "recipe_missing_unlock_path") == ("orphan",)
    assert _diagnostic_subjects(result, "recipe_unlock_missing_recipe") == (
        "missing-recipe",
    )


def test_hidden_recipe_excluded_by_default_and_deterministic_ordering() -> None:
    dataset = _milestone_dataset()
    definition = load_milestone_definitions(
        '{"milestones":[{"name":"automation","completed_technologies":["automation"]}]}',
    )["automation"]

    result = calculate_milestone_recipe_set(dataset, definition)

    assert result.recipe_names == (
        "assembler",
        "copper-cable",
        "manual-enabled",
        "starter-plate",
    )
    assert "debug-secret" not in result.recipe_names


def test_hidden_recipe_included_when_configured() -> None:
    dataset = _milestone_dataset()
    definition = load_milestone_definitions(
        '{"milestones":[{"name":"automation","completed_technologies":["automation"],"include_hidden":true}]}',
    )["automation"]

    result = calculate_milestone_recipe_set(dataset, definition)

    assert "debug-secret" in result.recipe_names


def test_missing_prerequisite_reference_is_diagnostic() -> None:
    dataset = OptimizerRecipeDataset(
        technologies=(TechnologyPrototype(name="a", prerequisites=("missing",)),),
    )
    definition = load_milestone_definitions(
        '{"milestones":[{"name":"missing-prereq","completed_technologies":["a"]}]}',
    )["missing-prereq"]

    result = calculate_milestone_recipe_set(dataset, definition)

    assert _diagnostic_subjects(result, "technology_missing_prerequisite") == (
        "missing",
    )


def test_unknown_technology_is_structured_failure() -> None:
    dataset = _milestone_dataset()
    definition = load_milestone_definitions(
        '{"milestones":[{"name":"missing-tech","completed_technologies":["does-not-exist"]}]}',
    )["missing-tech"]

    with pytest.raises(MilestoneFailure) as failure:
        calculate_milestone_recipe_set(dataset, definition)
    assert failure.value.diagnostics[0].code == "unknown_milestone_technology"
    assert "does-not-exist" in failure.value.diagnostics[0].message


def test_prerequisite_cycle_is_structured_failure() -> None:
    dataset = OptimizerRecipeDataset(
        technologies=(
            TechnologyPrototype(name="a", prerequisites=("b",)),
            TechnologyPrototype(name="b", prerequisites=("a",)),
        ),
    )
    definition = load_milestone_definitions(
        '{"milestones":[{"name":"cycle","completed_technologies":["a"]}]}',
    )["cycle"]

    with pytest.raises(MilestoneFailure) as failure:
        calculate_milestone_recipe_set(dataset, definition)
    assert failure.value.diagnostics[0].code == "technology_prerequisite_cycle"


def test_cli_exports_milestone(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    milestones_path = tmp_path / "milestones.json"
    output_path = tmp_path / "milestone.json"
    dataset_path.write_text(_milestone_dataset().to_json(), encoding="utf-8")
    milestones_path.write_text(
        '{"milestones":[{"name":"basic-circuits","completed_technologies":["electronics"]}]}',
        encoding="utf-8",
    )

    status = main(
        [
            "export-milestone",
            "--dataset",
            str(dataset_path),
            "--milestones",
            str(milestones_path),
            "--milestone",
            "basic-circuits",
            "--output",
            str(output_path),
        ]
    )

    assert status == 0
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["milestones"][0]["milestone"] == "basic-circuits"
    assert exported["milestones"][0]["recipe_names"] == [
        "copper-cable",
        "manual-enabled",
        "starter-plate",
    ]
    assert [recipe["name"] for recipe in exported["recipes"]] == [
        "starter-plate",
        "manual-enabled",
        "copper-cable",
    ]
    assert exported["diagnostics"]


def test_cli_unknown_milestone_technology_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset_path = tmp_path / "dataset.json"
    milestones_path = tmp_path / "milestones.json"
    dataset_path.write_text(_milestone_dataset().to_json(), encoding="utf-8")
    milestones_path.write_text(
        '{"milestones":[{"name":"missing-tech","completed_technologies":["does-not-exist"]}]}',
        encoding="utf-8",
    )

    status = main(
        [
            "export-milestone",
            "--dataset",
            str(dataset_path),
            "--milestones",
            str(milestones_path),
            "--milestone",
            "missing-tech",
        ]
    )

    assert status == 1
    assert "unknown technology does-not-exist" in capsys.readouterr().err


def _diagnostic_subjects(
    result: MilestoneRecipeSet, code: str
) -> tuple[str | None, ...]:
    return tuple(
        diagnostic.subject
        for diagnostic in result.diagnostics
        if diagnostic.code == code
    )


def _milestone_dataset() -> OptimizerRecipeDataset:
    return OptimizerRecipeDataset(
        recipes=(
            RecipePrototype("starter-plate", "crafting", 1.0, (), enabled=True),
            RecipePrototype("manual-enabled", "crafting", 1.0, (), enabled=True),
            RecipePrototype("copper-cable", "crafting", 1.0, ()),
            RecipePrototype("assembler", "crafting", 1.0, ()),
            RecipePrototype("debug-secret", "crafting", 1.0, (), hidden=True),
            RecipePrototype("orphan", "crafting", 1.0, ()),
        ),
        technologies=(
            TechnologyPrototype(
                name="electronics",
                prerequisites=("copper-processing",),
                unlocks=(
                    RecipeUnlock("electronics", "copper-cable"),
                    RecipeUnlock("electronics", "missing-recipe"),
                ),
            ),
            TechnologyPrototype(
                name="automation",
                prerequisites=("electronics",),
                unlocks=(
                    RecipeUnlock("automation", "assembler"),
                    RecipeUnlock("automation", "debug-secret"),
                ),
            ),
            TechnologyPrototype(name="copper-processing"),
        ),
    )
