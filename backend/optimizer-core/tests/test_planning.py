from __future__ import annotations

import json

from game_data_extractor.data_contracts import (
    ItemPrototype,
    OptimizerRecipeDataset,
    RecipeCoefficient,
    RecipePrototype,
    ResourceSource,
)

from factory_plan_optimizer.__main__ import main
from factory_plan_optimizer.planning import (
    accepted_early_pyanodon_inputs,
    dataset_to_factory_data_package,
    solve_planning_lp,
)


def test_conversion_aggregates_coefficients_and_input_policy() -> None:
    dataset = OptimizerRecipeDataset(
        items=[
            ItemPrototype("iron-ore", "item"),
            ItemPrototype("water", "fluid"),
            ItemPrototype("plate", "item"),
            ItemPrototype("kerogen", "item"),
            ItemPrototype("phosphate-rock", "item"),
            ItemPrototype("raw-coal", "item"),
            ItemPrototype("sulfur", "item"),
        ],
        recipes=[
            RecipePrototype(
                "smelt",
                "crafting",
                1.0,
                [
                    RecipeCoefficient("iron-ore", -2.0, "input"),
                    RecipeCoefficient("iron-ore", -3.0, "input"),
                    RecipeCoefficient("water", -1.0, "input"),
                    RecipeCoefficient("plate", 1.0, "output"),
                    RecipeCoefficient("plate", 1.0, "output"),
                ],
            ),
        ],
        resource_sources=[
            ResourceSource("kerogen-patch", "kerogen", 1.0, "basic-solid")
        ],
    )

    assert accepted_early_pyanodon_inputs(dataset) == (
        "iron-ore",
        "kerogen",
        "phosphate-rock",
        "raw-coal",
        "sulfur",
        "water",
    )
    package = dataset_to_factory_data_package(dataset, {"plate": 1.0})

    assert {item.id for item in package.items} == {
        "iron-ore",
        "water",
        "plate",
        "kerogen",
        "phosphate-rock",
        "raw-coal",
        "sulfur",
    }
    assert package.recipes[0].coefficients == {
        "iron-ore": -5.0,
        "water": -1.0,
        "plate": 2.0,
    }
    assert set(package.external_supplies) == {
        "iron-ore",
        "water",
        "kerogen",
        "phosphate-rock",
        "raw-coal",
        "sulfur",
    }
    assert package.final_demands == {"plate": 1.0}


def test_relaxation_adds_consumed_input_until_solved() -> None:
    dataset = OptimizerRecipeDataset(
        items=[ItemPrototype("catalyst", "item"), ItemPrototype("science", "item")],
        recipes=[
            RecipePrototype(
                "make-science",
                "crafting",
                1.0,
                [
                    RecipeCoefficient("catalyst", -1.0, "input"),
                    RecipeCoefficient("science", 1.0, "output"),
                ],
            ),
        ],
    )

    strict = solve_planning_lp(dataset, {"science": 1.0})
    relaxed = solve_planning_lp(dataset, {"science": 1.0}, allow_relax_inputs=True)

    assert strict.result.unmet_demand["science"] > 0.0
    assert relaxed.result.unmet_demand["science"] == 0.0
    assert relaxed.result.recipe_rates["make-science"] > 0.0
    assert [step.added_input for step in relaxed.relaxation_steps] == ["catalyst"]


def test_py_science_pack_1_policy_accepts_raw_coal() -> None:
    dataset = OptimizerRecipeDataset(
        items=[
            ItemPrototype("raw-coal", "item"),
            ItemPrototype("coal", "item"),
            ItemPrototype("water", "fluid"),
            ItemPrototype("iron-ore", "item"),
            ItemPrototype("iron-plate", "item"),
            ItemPrototype("copper-ore", "item"),
            ItemPrototype("copper-plate", "item"),
            ItemPrototype("py-science-pack-1", "item"),
        ],
        recipes=[
            RecipePrototype(
                "process-raw-coal",
                "crafting",
                1.0,
                [
                    RecipeCoefficient("raw-coal", -1.0, "input"),
                    RecipeCoefficient("coal", 1.0, "output"),
                ],
                enabled=True,
            ),
            RecipePrototype(
                "smelt-iron",
                "smelting",
                1.0,
                [
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("iron-plate", 1.0, "output"),
                ],
                enabled=True,
            ),
            RecipePrototype(
                "smelt-copper",
                "smelting",
                1.0,
                [
                    RecipeCoefficient("copper-ore", -1.0, "input"),
                    RecipeCoefficient("copper-plate", 1.0, "output"),
                ],
                enabled=True,
            ),
            RecipePrototype(
                "craft-py-science-pack-1",
                "crafting",
                1.0,
                [
                    RecipeCoefficient("iron-plate", -1.0, "input"),
                    RecipeCoefficient("copper-plate", -1.0, "input"),
                    RecipeCoefficient("coal", -1.0, "input"),
                    RecipeCoefficient("water", -1.0, "input"),
                    RecipeCoefficient("py-science-pack-1", 1.0, "output"),
                ],
                enabled=True,
            ),
        ],
    )

    plan = solve_planning_lp(dataset, {"py-science-pack-1": 1.0})

    assert plan.result.unmet_demand["py-science-pack-1"] == 0.0
    assert plan.result.recipe_rates["craft-py-science-pack-1"] == 1.0
    assert plan.result.external_supplies["raw-coal"] == 1.0


def test_plan_cli_smoke(tmp_path) -> None:  # noqa: ANN001
    dataset = OptimizerRecipeDataset(
        items=[ItemPrototype("iron-ore", "item"), ItemPrototype("plate", "item")],
        recipes=[
            RecipePrototype(
                "smelt",
                "crafting",
                1.0,
                [
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("plate", 1.0, "output"),
                ],
            ),
        ],
    )
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "plan.json"
    dataset_path.write_text(dataset.to_json(), encoding="utf-8")

    exit_code = main(
        [
            "plan",
            "--dataset",
            str(dataset_path),
            "--demand",
            "plate=60/min",
            "--output",
            str(output_path),
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "optimal"
    assert output["selected_recipe_rates_per_second"] == {"smelt": 1.0}
    assert output["raw_external_inputs_per_second"] == {"iron-ore": 1.0}
