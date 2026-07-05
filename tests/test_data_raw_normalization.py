import json
import re
from pathlib import Path

import pytest

from factory_plan_optimizer.data_raw_normalization import normalize_data_raw_dump
from factory_plan_optimizer.import_models import DatasetParseError

FIXTURE_DIR = Path("tests/fixtures/data_raw")
VARIANT_ENERGY_REQUIRED = 3.0


def test_normalizes_common_data_raw_shapes() -> None:
    dataset = normalize_data_raw_dump(
        (FIXTURE_DIR / "minimal-py-like-data-raw.json").read_text(encoding="utf-8"),
    )

    item_names = {item.name for item in dataset.items}
    assert {"iron-ore", "iron-plate", "steam"} <= item_names

    recipes = {recipe.name: recipe for recipe in dataset.recipes}
    assert recipes["copper-smelting"].enabled is True
    assert recipes["hidden-steam"].hidden is True
    assert recipes["iron-gear-wheel"].enabled is False

    copper_coefficients = {
        coefficient.item_name: coefficient.amount
        for coefficient in recipes["copper-smelting"].coefficients
    }
    assert copper_coefficients == {"copper-ore": -1.0, "copper-plate": 1.0}

    byproduct_coefficients = {
        coefficient.item_name: coefficient.amount
        for coefficient in recipes["iron-smelting-with-ash"].coefficients
    }
    assert byproduct_coefficients == {"iron-ore": -1.0, "iron-plate": 1.0, "ash": 0.25}

    technologies = {technology.name: technology for technology in dataset.technologies}
    assert technologies["automation"].prerequisites == ("starter-tech",)
    assert [unlock.recipe_name for unlock in technologies["automation"].unlocks] == [
        "iron-gear-wheel",
    ]

    sources = {source.name: source for source in dataset.resource_sources}
    assert sources["iron-ore"].item_name == "iron-ore"
    assert sources["iron-ore"].amount == 1.0

    diagnostics = {
        (diagnostic.code, diagnostic.subject) for diagnostic in dataset.diagnostics
    }
    assert ("unknown-item-reference", "mystery-dust") in diagnostics
    assert ("hidden-recipe", "hidden-steam") in diagnostics
    assert ("disabled-recipe", "iron-gear-wheel") in diagnostics


def test_normalized_dataset_json_is_deterministic_and_valid() -> None:
    dataset = normalize_data_raw_dump(
        (FIXTURE_DIR / "minimal-py-like-data-raw.json").read_text(encoding="utf-8"),
    )

    parsed = json.loads(dataset.to_json())

    assert [item["name"] for item in parsed["items"]] == sorted(
        item["name"] for item in parsed["items"]
    )
    assert [recipe["name"] for recipe in parsed["recipes"]] == sorted(
        recipe["name"] for recipe in parsed["recipes"]
    )


def test_malformed_data_raw_fails_clearly() -> None:
    with pytest.raises(
        DatasetParseError,
        match=re.escape("data.raw item: expected JSON object"),
    ):
        normalize_data_raw_dump(
            (FIXTURE_DIR / "malformed-data-raw.json").read_text(encoding="utf-8"),
        )


def test_omitted_recipe_enabled_defaults_to_true() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "item": {"ore": {"name": "ore"}, "plate": {"name": "plate"}},
                "recipe": {
                    "make-plate": {
                        "ingredients": [["ore", 1]],
                        "result": "plate",
                    },
                    "disabled-plate": {
                        "enabled": False,
                        "ingredients": [["ore", 1]],
                        "result": "plate",
                    },
                },
            }
        ),
    )

    recipes = {recipe.name: recipe for recipe in dataset.recipes}
    assert recipes["make-plate"].enabled is True
    assert recipes["disabled-plate"].enabled is False


def test_common_item_like_prototype_sections_are_items() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "tool": {"science-pack": {"name": "science-pack", "stack_size": 200}},
                "module": {"speed-module": {"name": "speed-module"}},
                "recipe": {
                    "make-science": {
                        "ingredients": [["speed-module", 1]],
                        "result": "science-pack",
                    }
                },
            }
        ),
    )

    assert {item.name: item.prototype_type for item in dataset.items} == {
        "science-pack": "item",
        "speed-module": "item",
    }
    assert not [
        diagnostic
        for diagnostic in dataset.diagnostics
        if diagnostic.code == "unknown-item-reference"
    ]


def test_malformed_technology_and_resource_emit_diagnostics() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "item": {"ore": {"name": "ore"}},
                "technology": {
                    "bad-tech": {
                        "effects": [],
                        "prerequisites": [1],
                    },
                    "not-an-object": [],
                },
                "resource": {
                    "bad-resource": {"minable": []},
                    "not-an-object": [],
                },
            }
        ),
    )

    assert dataset.technologies == ()
    assert dataset.resource_sources == ()
    diagnostics = {
        (diagnostic.code, diagnostic.subject) for diagnostic in dataset.diagnostics
    }
    assert ("malformed-prototype", "bad-tech") in diagnostics
    assert ("malformed-prototype", "not-an-object") in diagnostics
    assert ("malformed-prototype", "bad-resource") in diagnostics


def test_recipe_variants_do_not_fall_back_to_top_level_fields() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "item": {
                    "ore": {"name": "ore"},
                    "normal-plate": {"name": "normal-plate"},
                    "top-plate": {"name": "top-plate"},
                },
                "recipe": {
                    "variant-recipe": {
                        "enabled": True,
                        "category": "top-category",
                        "energy_required": 99,
                        "ingredients": [["ore", 99]],
                        "result": "top-plate",
                        "normal": {
                            "enabled": False,
                            "hidden": True,
                            "category": "variant-category",
                            "energy_required": 3,
                            "ingredients": [["ore", 2]],
                            "result": "normal-plate",
                        },
                        "expensive": {
                            "ingredients": [["ore", 4]],
                            "result": "top-plate",
                        },
                    }
                },
            }
        ),
    )

    recipe = dataset.recipes[0]
    assert recipe.enabled is False
    assert recipe.hidden is True
    assert recipe.category == "variant-category"
    assert recipe.energy_required == VARIANT_ENERGY_REQUIRED
    assert {
        coefficient.item_name: coefficient.amount for coefficient in recipe.coefficients
    } == {
        "ore": -2.0,
        "normal-plate": 1.0,
    }
    assert ("unsupported-recipe-variant", "variant-recipe") in {
        (diagnostic.code, diagnostic.subject) for diagnostic in dataset.diagnostics
    }


def test_expensive_only_variant_is_parsed_with_diagnostic() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "item": {"ore": {"name": "ore"}, "plate": {"name": "plate"}},
                "recipe": {
                    "expensive-only": {
                        "expensive": {
                            "ingredients": [["ore", 3]],
                            "result": "plate",
                        }
                    }
                },
            }
        ),
    )

    assert {
        coefficient.item_name: coefficient.amount
        for coefficient in dataset.recipes[0].coefficients
    } == {
        "ore": -3.0,
        "plate": 1.0,
    }
    assert ("unsupported-recipe-variant", "expensive-only") in {
        (diagnostic.code, diagnostic.subject) for diagnostic in dataset.diagnostics
    }


def test_booleans_are_rejected_as_numbers_and_resource_names_are_unambiguous() -> None:
    dataset = normalize_data_raw_dump(
        json.dumps(
            {
                "item": {"ore-a": {"name": "ore-a"}, "ore-b": {"name": "ore-b"}},
                "resource": {
                    "mixed-ore": {
                        "minable": {
                            "results": [
                                {"name": "ore-a", "amount": 1},
                                {"name": "ore-b", "amount": 2},
                            ]
                        }
                    },
                    "bad-boolean": {"minable": {"result": "ore-a", "count": True}},
                },
            }
        ),
    )

    assert [source.name for source in dataset.resource_sources] == [
        "mixed-ore:ore-a",
        "mixed-ore:ore-b",
    ]
    assert ("malformed-prototype", "bad-boolean") in {
        (diagnostic.code, diagnostic.subject) for diagnostic in dataset.diagnostics
    }
