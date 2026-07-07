import json

import pytest
from game_data_extractor.data_contracts import (
    DatasetParseError,
    ItemPrototype,
    OptimizerRecipeDataset,
    RecipeCoefficient,
    RecipePrototype,
)

from paths import FIXTURES_ROOT


def test_recipe_coefficients_round_trip_with_deterministic_json_order() -> None:
    # Given: a tiny dataset with one input coefficient and one output coefficient.
    dataset = OptimizerRecipeDataset(
        items=[
            ItemPrototype(name="iron-ore", prototype_type="item"),
            ItemPrototype(name="iron-plate", prototype_type="item"),
        ],
        recipes=[
            RecipePrototype(
                name="smelt-iron",
                category="smelting",
                energy_required=3.2,
                coefficients=[
                    RecipeCoefficient(
                        item_name="iron-ore",
                        amount=-1.0,
                        coefficient_kind="input",
                    ),
                    RecipeCoefficient(
                        item_name="iron-plate",
                        amount=1.0,
                        coefficient_kind="output",
                    ),
                ],
            ),
        ],
    )

    # When: the dataset is serialized and loaded back through the JSON boundary.
    json_text = dataset.to_json()
    reloaded_dataset = OptimizerRecipeDataset.from_json(json_text)

    # Then: JSON keys are deterministic and coefficient signs follow a_ir.
    assert list(json.loads(json_text)) == [
        "diagnostics",
        "dump_provenance",
        "items",
        "milestones",
        "recipes",
        "resource_sources",
        "save_settings_provenance",
        "startup_settings",
        "technologies",
    ]
    coefficients = reloaded_dataset.recipes[0].coefficients
    assert coefficients[0].amount < 0
    assert coefficients[1].amount > 0


def test_dataset_parse_rejects_negative_output_coefficients() -> None:
    # Given: a fixture with an output coefficient using a negative a_ir value.
    dataset_path = FIXTURES_ROOT / "invalid_negative_output.json"

    # When / Then: parsing rejects the malformed recipe at the JSON boundary.
    with pytest.raises(DatasetParseError, match="output coefficient"):
        OptimizerRecipeDataset.from_json(dataset_path.read_text(encoding="utf-8"))
