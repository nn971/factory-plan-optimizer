import json
from collections.abc import Callable, MutableMapping
from typing import cast

import pytest

from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    FactoryDataPackage,
    FactoryDataPackageParseError,
    ItemPrototype,
    OptimizerRecipeDataset,
    RawRecipeTerm,
    RecipeCoefficient,
    RecipePrototype,
    RecipeUnlock,
    TechnologyPrototype,
    dataset_to_factory_data_package,
)

MAXIMUM_TEMPERATURE = 15.0


def _minimal_factory_data() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "items": [{"id": "iron-ore"}, {"id": "iron-plate", "kind": "item"}],
        "recipes": [
            {
                "id": "smelt-iron",
                "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
                "energy_required": 3.2,
                "ingredients": [{"type": "unknown", "name": "iron-ore", "amount": 1.0}],
                "results": [{"type": "item", "name": "iron-plate", "amount": 1.0}],
                "production_cost": 0.5,
            },
        ],
        "final_demands": {"iron-plate": 1.0},
        "external_supplies": {"iron-ore": {"cost": 1.0, "capacity": None}},
        "unmet_demand_penalty_rate": 1000.0,
    }


def test_factory_data_package_from_json_to_json_roundtrip() -> None:
    text = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "items": [{"id": "iron-ore"}, {"id": "iron-plate", "kind": "item"}],
            "recipes": [
                {
                    "id": "smelt-iron",
                    "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
                    "energy_required": 3.2,
                    "ingredients": [
                        {"type": "unknown", "name": "iron-ore", "amount": 1.0}
                    ],
                    "results": [{"type": "item", "name": "iron-plate", "amount": 1.0}],
                    "production_cost": 0.5,
                },
            ],
            "final_demands": {"iron-plate": 1.0},
            "external_supplies": {"iron-ore": {"cost": 1.0, "capacity": None}},
            "unmet_demand_penalty_rate": 1000.0,
        }
    )

    package = FactoryDataPackage.from_json(text)
    reparsed = FactoryDataPackage.from_json(package.to_json())

    assert reparsed == package
    assert package.items[0].category == "unknown"
    assert package.items[0].unlock_condition.type == "unknown"
    assert package.recipes[0].category == "unknown"
    assert package.recipes[0].unlock_condition.type == "unknown"


def test_raw_input_suggestions_absent_parses_as_none_and_omits_serialization() -> None:
    package = FactoryDataPackage.from_json(json.dumps(_minimal_factory_data()))

    assert package.raw_input_suggestions is None
    assert "raw_input_suggestions" not in package.to_json_value()


def test_raw_input_suggestions_empty_survives_roundtrip() -> None:
    data = _minimal_factory_data()
    data["raw_input_suggestions"] = []

    package = FactoryDataPackage.from_json(json.dumps(data))
    reparsed = FactoryDataPackage.from_json(package.to_json())

    assert package.raw_input_suggestions == ()
    assert package.to_json_value()["raw_input_suggestions"] == []
    assert reparsed.raw_input_suggestions == ()


def test_raw_input_suggestions_roundtrip_preserves_present_ids() -> None:
    data = _minimal_factory_data()
    data["raw_input_suggestions"] = ["iron-ore"]

    package = FactoryDataPackage.from_json(json.dumps(data))

    assert package.raw_input_suggestions == ("iron-ore",)
    assert FactoryDataPackage.from_json(package.to_json()).raw_input_suggestions == (
        "iron-ore",
    )


@pytest.mark.parametrize(
    "suggestions",
    [["missing"], ["iron-ore", "iron-ore"], ["bad id"], [1]],
)
def test_raw_input_suggestions_reject_invalid_values(suggestions: object) -> None:
    data = _minimal_factory_data()
    data["raw_input_suggestions"] = suggestions

    with pytest.raises(FactoryDataPackageParseError):
        FactoryDataPackage.from_json(json.dumps(data))


def test_factory_data_package_accepts_explicit_metadata_unlock_forms() -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "items": [
            {
                "id": "iron-ore",
                "category": "raw",
                "unlock_condition": {"type": "unknown", "id": None},
            },
            {
                "id": "iron-plate",
                "kind": "item",
                "unlock_condition": {"type": "start-unlocked"},
            },
        ],
        "recipes": [
            {
                "id": "smelt-iron",
                "category": "smelting",
                "unlock_condition": {"type": "technology", "id": "advanced-smelting"},
                "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
                "energy_required": 3.2,
                "ingredients": [{"type": "unknown", "name": "iron-ore", "amount": 1.0}],
                "results": [{"type": "item", "name": "iron-plate", "amount": 1.0}],
                "production_cost": 0.5,
            },
        ],
        "final_demands": {"iron-plate": 1.0},
        "external_supplies": {"iron-ore": {"cost": 1.0}},
        "unmet_demand_penalty_rate": 1000.0,
    }

    package = FactoryDataPackage.from_json(json.dumps(data))

    assert package.items[0].category == "raw"
    assert package.items[0].unlock_condition.id is None
    assert package.items[1].unlock_condition.type == "start-unlocked"
    assert package.recipes[0].unlock_condition.id == "advanced-smelting"
    serialized_items = cast("list[dict[str, object]]", package.to_json_value()["items"])
    assert serialized_items[0]["unlock_condition"] == {"type": "unknown", "id": None}
    assert serialized_items[1]["unlock_condition"] == {
        "type": "start-unlocked",
        "id": None,
    }


@pytest.mark.parametrize(
    "patch",
    [
        lambda item: item.__setitem__("category", None),
        lambda item: item.__setitem__("category", "bad category"),
        lambda item: item.__setitem__("unlock_condition", {"type": "technology"}),
        lambda item: item.__setitem__(
            "unlock_condition", {"type": "unknown", "id": "tech"}
        ),
        lambda item: item.__setitem__(
            "unlock_condition", {"type": "start-unlocked", "id": "tech"}
        ),
        lambda item: item.__setitem__("unlock_condition", {"type": "mystery"}),
        lambda item: item.__setitem__(
            "unlock_condition", {"type": "unknown", "extra": None}
        ),
    ],
)
def test_factory_data_package_rejects_invalid_metadata(
    patch: Callable[[MutableMapping[str, object]], None],
) -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "items": [{"id": "iron-ore"}],
        "recipes": [
            {
                "id": "mine-iron",
                "coefficients": {"iron-ore": 1.0},
                "energy_required": 1.0,
                "ingredients": [],
                "results": [{"type": "unknown", "name": "iron-ore", "amount": 1.0}],
                "production_cost": 0.5,
            },
        ],
        "final_demands": {"iron-ore": 1.0},
        "external_supplies": {},
        "unmet_demand_penalty_rate": 1000.0,
    }
    patch(data["items"][0])

    with pytest.raises(FactoryDataPackageParseError):
        FactoryDataPackage.from_json(json.dumps(data))


def test_planning_adapter_derives_category_and_unlocks() -> None:
    dataset = OptimizerRecipeDataset(
        items=(ItemPrototype("iron-ore", "item"),),
        recipes=(
            RecipePrototype(
                "mine-iron",
                "mining",
                1.0,
                (RecipeCoefficient("iron-ore", 1.0, "output"),),
                results=(RawRecipeTerm(type="item", name="iron-ore", amount=1.0),),
                enabled=False,
            ),
            RecipePrototype(
                "free-iron",
                "crafting",
                1.0,
                (RecipeCoefficient("iron-ore", 1.0, "output"),),
                enabled=True,
                source_prototype_type="boiler",
                source_prototype_name="free-boiler",
            ),
            RecipePrototype(
                "manual-iron",
                "crafting",
                1.0,
                (RecipeCoefficient("iron-ore", 1.0, "output"),),
                enabled=True,
            ),
        ),
        technologies=(
            TechnologyPrototype(
                "z-tech",
                unlocks=(
                    RecipeUnlock("z-tech", "mine-iron"),
                    RecipeUnlock("z-tech", "free-iron"),
                ),
            ),
            TechnologyPrototype(
                "a-tech",
                unlocks=(RecipeUnlock("a-tech", "mine-iron"),),
            ),
        ),
    )

    package = dataset_to_factory_data_package(dataset, {"iron-ore": 1.0}, ())

    assert package.items[0].category == "unknown"
    assert package.recipes[0].category == "mining"
    assert package.recipes[0].unlock_condition.type == "technology"
    assert package.recipes[0].unlock_condition.id == "a-tech"
    assert package.recipes[0].results[0].type == "item"
    assert package.recipes[0].results[0].name == "iron-ore"
    assert package.recipes[1].unlock_condition.type == "technology"
    assert package.recipes[1].unlock_condition.id == "z-tech"
    assert package.recipes[1].source_prototype_type == "boiler"
    assert package.recipes[1].source_prototype_name == "free-boiler"
    assert package.recipes[1].production_cost == 0.0
    assert package.recipes[2].unlock_condition.type == "start-unlocked"


def test_planning_adapter_sets_raw_input_suggestions_from_accepted_inputs() -> None:
    dataset = OptimizerRecipeDataset(
        items=(ItemPrototype("iron-ore", "item"), ItemPrototype("iron-plate", "item")),
        recipes=(
            RecipePrototype(
                "smelt-iron",
                "smelting",
                1.0,
                (
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("iron-plate", 1.0, "output"),
                ),
                enabled=True,
            ),
        ),
    )

    package = dataset_to_factory_data_package(
        dataset,
        {"iron-plate": 1.0},
        ("iron-ore",),
    )

    assert package.raw_input_suggestions == ("iron-ore",)


def test_planning_adapter_explicit_empty_accepted_inputs_disables_fallback() -> None:
    dataset = OptimizerRecipeDataset(
        items=(
            ItemPrototype("copper-ore", "item"),
            ItemPrototype("copper-plate", "item"),
        ),
        recipes=(
            RecipePrototype(
                "smelt-copper",
                "smelting",
                1.0,
                (
                    RecipeCoefficient("copper-ore", -1.0, "input"),
                    RecipeCoefficient("copper-plate", 1.0, "output"),
                ),
                enabled=True,
            ),
        ),
    )

    package = dataset_to_factory_data_package(
        dataset,
        {"copper-plate": 1.0},
        (),
    )

    assert package.external_supplies == {}
    assert package.raw_input_suggestions == ()


def test_planning_adapter_derives_science_milestone_recipe_sets() -> None:
    dataset = OptimizerRecipeDataset(
        items=(
            ItemPrototype("iron-ore", "item"),
            ItemPrototype("automation-science-pack", "item"),
            ItemPrototype("py-science-pack-1", "item"),
        ),
        recipes=(
            RecipePrototype(
                "mine-iron",
                "mining",
                1.0,
                (RecipeCoefficient("iron-ore", 1.0, "output"),),
                enabled=True,
            ),
            RecipePrototype(
                "make-automation-science",
                "crafting",
                1.0,
                (
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("automation-science-pack", 1.0, "output"),
                ),
                enabled=True,
            ),
            RecipePrototype(
                "make-py1-science",
                "crafting",
                1.0,
                (
                    RecipeCoefficient("automation-science-pack", -1.0, "input"),
                    RecipeCoefficient("py-science-pack-1", 1.0, "output"),
                ),
                enabled=False,
            ),
        ),
        technologies=(
            TechnologyPrototype(
                "py1-tech",
                science_pack_ingredients=(
                    "automation-science-pack",
                    "py-science-pack-1",
                ),
                unlocks=(RecipeUnlock("py1-tech", "make-py1-science"),),
            ),
        ),
    )

    package = dataset_to_factory_data_package(dataset, {"py-science-pack-1": 1.0}, ())
    reparsed = FactoryDataPackage.from_json(package.to_json())

    milestones = {milestone.milestone: milestone for milestone in reparsed.milestones}
    assert milestones["automation-science-pack"].recipe_names == (
        "make-automation-science",
        "mine-iron",
    )
    assert milestones["py-science-pack-1"].recipe_names == (
        "make-automation-science",
        "make-py1-science",
        "mine-iron",
    )


def test_planning_adapter_deduplicates_generated_parameter_items() -> None:
    dataset = OptimizerRecipeDataset(
        items=(
            ItemPrototype("parameter-0", "item"),
            ItemPrototype("parameter-0", "item"),
            ItemPrototype("iron-plate", "item"),
        ),
        recipes=(
            RecipePrototype(
                "make-iron",
                "crafting",
                1.0,
                (RecipeCoefficient("iron-plate", 1.0, "output"),),
                results=(RawRecipeTerm(type="item", name="iron-plate", amount=1.0),),
                enabled=True,
            ),
        ),
    )

    package = dataset_to_factory_data_package(dataset, {"iron-plate": 1.0}, ())
    reparsed = FactoryDataPackage.from_json(package.to_json())

    assert [item.id for item in reparsed.items] == ["parameter-0", "iron-plate"]


def test_planning_adapter_skips_zero_coefficient_recipes() -> None:
    dataset = OptimizerRecipeDataset(
        items=(ItemPrototype("iron-plate", "item"),),
        recipes=(
            RecipePrototype(
                "empty-generated-recipe",
                "crafting",
                1.0,
                (),
                enabled=True,
            ),
            RecipePrototype(
                "net-zero-generated-recipe",
                "crafting",
                1.0,
                (
                    RecipeCoefficient("iron-plate", 1.0, "output"),
                    RecipeCoefficient("iron-plate", -1.0, "input"),
                ),
                enabled=True,
            ),
            RecipePrototype(
                "make-iron",
                "crafting",
                1.0,
                (RecipeCoefficient("iron-plate", 1.0, "output"),),
                results=(RawRecipeTerm(type="item", name="iron-plate", amount=1.0),),
                enabled=True,
            ),
        ),
    )

    package = dataset_to_factory_data_package(dataset, {"iron-plate": 1.0}, ())
    reparsed = FactoryDataPackage.from_json(package.to_json())

    assert [recipe.id for recipe in reparsed.recipes] == ["make-iron"]


def test_optimizer_recipe_dataset_from_json_to_json_roundtrip() -> None:
    text = json.dumps(
        {
            "items": [{"name": "iron-ore", "prototype_type": "item"}],
            "recipes": [
                {
                    "name": "mine-iron",
                    "category": "mining",
                    "energy_required": 1.0,
                    "coefficients": [
                        {
                            "item_name": "iron-ore",
                            "amount": 1.0,
                            "coefficient_kind": "output",
                        }
                    ],
                    "ingredients": [],
                    "results": [
                        {
                            "type": "item",
                            "name": "iron-ore",
                            "amount_min": 1.0,
                            "amount_max": 2.0,
                            "probability": 0.5,
                            "temperature": 10.0,
                            "minimum_temperature": 5.0,
                            "maximum_temperature": MAXIMUM_TEMPERATURE,
                            "catalyst_amount": 0.0,
                            "fluidbox_index": 0,
                        }
                    ],
                    "enabled": True,
                    "hidden": False,
                    "source_prototype_type": "boiler",
                    "source_prototype_name": "mine-boiler",
                }
            ],
            "technologies": [],
            "resource_sources": [],
            "startup_settings": [],
            "save_settings_provenance": None,
            "dump_provenance": None,
            "diagnostics": [],
            "milestones": [],
        }
    )

    dataset = OptimizerRecipeDataset.from_json(text)
    reparsed = OptimizerRecipeDataset.from_json(dataset.to_json())

    assert reparsed == dataset
    assert reparsed.recipes[0].results[0].maximum_temperature == MAXIMUM_TEMPERATURE
    assert reparsed.recipes[0].source_prototype_type == "boiler"
    assert reparsed.recipes[0].source_prototype_name == "mine-boiler"
