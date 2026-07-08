from __future__ import annotations

from game_data_extractor.data_contracts import (
    FactoryDataPackage,
    Item,
    Recipe,
    RecipeTerm,
    UnlockCondition,
)

from factory_plan_api.explorer import explorer_from_package

ITEM_COUNT = 3
FLUID_COUNT = 1
RECIPE_COUNT = 2
OUTPUT_TERM_COUNT = 2
OUTPUT_AMOUNT_MAX = 2.0
MINIMUM_TEMPERATURE = 15.0
MAXIMUM_TEMPERATURE = 100.0
PROBABILITY = 0.5
OUTPUT_TEMPERATURE = 165.0


def test_explorer_mapper_derives_relationships_io_and_sorting() -> None:
    package = FactoryDataPackage(
        schema_version="factory-data-v2",
        items=[
            Item(id="z-output", kind="item", category="b"),
            Item(id="a-input", kind="item", category="a"),
            Item(
                id="fluid-input",
                kind="fluid",
                category="a",
                unlock_condition=UnlockCondition(type="start-unlocked"),
            ),
        ],
        recipes=[
            Recipe(
                id="z-consume",
                coefficients={"z-output": -2.0},
                energy_required=1.0,
                ingredients=[RecipeTerm(type="item", name="z-output", amount=2.0)],
                results=[],
                production_cost=3.0,
                category="b",
            ),
            Recipe(
                id="a-make",
                coefficients={"a-input": -1.5, "fluid-input": -0.5, "z-output": 2.0},
                energy_required=1.0,
                ingredients=[
                    RecipeTerm(type="item", name="a-input", amount=1.5),
                    RecipeTerm(
                        type="fluid",
                        name="fluid-input",
                        amount=0.5,
                        minimum_temperature=MINIMUM_TEMPERATURE,
                        maximum_temperature=MAXIMUM_TEMPERATURE,
                        fluidbox_index=1,
                    ),
                ],
                results=[
                    RecipeTerm(type="item", name="z-output", amount=1.0),
                    RecipeTerm(
                        type="item",
                        name="z-output",
                        amount_min=1.0,
                        amount_max=OUTPUT_AMOUNT_MAX,
                        probability=PROBABILITY,
                        catalyst_amount=0.0,
                        temperature=OUTPUT_TEMPERATURE,
                    ),
                ],
                production_cost=1.0,
                category="a",
                unlock_condition=UnlockCondition(type="technology", id="tech-a"),
                source_prototype_type="boiler",
                source_prototype_name="test-boiler",
            ),
        ],
        final_demands={},
        external_supplies={},
        unmet_demand_penalty_rate=1000.0,
    )

    explorer = explorer_from_package(package, package_id="pkg-1")

    assert explorer.package_id == "pkg-1"
    assert explorer.overview.item_count == ITEM_COUNT
    assert explorer.overview.fluid_count == FLUID_COUNT
    assert explorer.overview.recipe_count == RECIPE_COUNT
    assert explorer.overview.item_categories == ["a", "b"]
    assert [item.id for item in explorer.items] == [
        "a-input",
        "fluid-input",
        "z-output",
    ]
    assert [recipe.id for recipe in explorer.recipes] == ["a-make", "z-consume"]

    output = next(item for item in explorer.items if item.id == "z-output")
    assert [recipe.id for recipe in output.produced_by] == ["a-make"]
    assert [recipe.id for recipe in output.consumed_by] == ["z-consume"]
    assert output.unlock_condition.type == "unknown"
    assert output.unlock_condition.id is None

    make = explorer.recipes[0]
    assert make.unlock_condition.type == "technology"
    assert make.unlock_condition.id == "tech-a"
    assert make.energy_required == 1.0
    assert make.source_prototype_type == "boiler"
    assert make.source_prototype_name == "test-boiler"
    assert [(row.item_id, row.amount) for row in make.inputs] == [
        ("a-input", 1.5),
        ("fluid-input", 0.5),
    ]
    assert [(row.item_id, row.amount) for row in make.outputs] == [("z-output", 2.0)]
    fluid_input = make.inputs[1]
    assert len(fluid_input.terms) == 1
    assert fluid_input.terms[0].minimum_temperature == MINIMUM_TEMPERATURE
    assert fluid_input.terms[0].maximum_temperature == MAXIMUM_TEMPERATURE
    assert fluid_input.terms[0].fluidbox_index == 1
    output_terms = make.outputs[0].terms
    assert len(output_terms) == OUTPUT_TERM_COUNT
    assert output_terms[0].amount == 1.0
    assert output_terms[1].amount_min == 1.0
    assert output_terms[1].amount_max == OUTPUT_AMOUNT_MAX
    assert output_terms[1].probability == PROBABILITY
    assert output_terms[1].catalyst_amount == 0.0
    assert output_terms[1].temperature == OUTPUT_TEMPERATURE
