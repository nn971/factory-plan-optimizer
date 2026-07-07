import json

from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    FactoryDataPackage,
    OptimizerRecipeDataset,
)


def test_factory_data_package_from_json_to_json_roundtrip() -> None:
    text = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "items": [{"id": "iron-ore"}, {"id": "iron-plate", "kind": "item"}],
            "recipes": [
                {
                    "id": "smelt-iron",
                    "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
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
                    "enabled": True,
                    "hidden": False,
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
