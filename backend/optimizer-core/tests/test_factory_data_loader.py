import json
from collections.abc import Callable
from typing import cast

import pytest
from game_data_extractor.data_contracts import (
    SCHEMA_VERSION,
    FactoryDataPackage,
    FactoryDataPackageParseError,
    load_factory_data_package,
)

type PackageJson = dict[str, object]
ENERGY_REQUIRED = 3.2


def _minimal_package() -> PackageJson:
    return {
        "schema_version": SCHEMA_VERSION,
        "items": [{"id": "iron-ore"}, {"id": "iron-plate", "kind": "item"}],
        "recipes": [
            {
                "id": "smelt-iron",
                "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
                "energy_required": ENERGY_REQUIRED,
                "ingredients": [{"type": "unknown", "name": "iron-ore", "amount": 1.0}],
                "results": [{"type": "item", "name": "iron-plate", "amount": 1.0}],
                "production_cost": 0.5,
            },
        ],
        "final_demands": {"iron-plate": 60.0},
        "external_supplies": {"iron-ore": {"cost": 1.0}},
        "unmet_demand_penalty_rate": 1000.0,
    }


def _load(data: PackageJson) -> FactoryDataPackage:
    return load_factory_data_package(json.dumps(data))


def _first_recipe(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", cast("list[object]", data["recipes"])[0])


def _coefficients(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", _first_recipe(data)["coefficients"])


def _first_ingredient(data: PackageJson) -> dict[str, object]:
    ingredients = cast("list[object]", _first_recipe(data)["ingredients"])
    return cast("dict[str, object]", ingredients[0])


def _final_demands(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", data["final_demands"])


def _external_supplies(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", data["external_supplies"])


def _first_item(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", cast("list[object]", data["items"])[0])


def _iron_ore_supply(data: PackageJson) -> dict[str, object]:
    return cast("dict[str, object]", _external_supplies(data)["iron-ore"])


def test_loads_minimal_package_with_kind_default_and_immutable_structures() -> None:
    package = _load(_minimal_package())

    assert package.schema_version == SCHEMA_VERSION
    assert isinstance(package.items, tuple)
    assert package.items[0].kind == "unknown"
    assert package.items[0].category == "unknown"
    assert package.items[0].unlock_condition.type == "unknown"
    assert package.items[0].unlock_condition.id is None
    assert package.items[1].kind == "item"
    assert isinstance(package.recipes, tuple)
    assert dict(package.recipes[0].coefficients) == {
        "iron-ore": -1.0,
        "iron-plate": 1.0,
    }
    assert package.external_supplies["iron-ore"].capacity is None
    assert package.recipes[0].energy_required == ENERGY_REQUIRED
    assert package.recipes[0].source_prototype_type == "recipe"
    assert package.recipes[0].source_prototype_name == "smelt-iron"


def test_loads_valid_category_and_unlock_metadata() -> None:
    data = _minimal_package()
    _first_item(data)["category"] = "raw"
    _first_item(data)["unlock_condition"] = {"type": "unknown", "id": None}
    _first_recipe(data)["category"] = "smelting"
    _first_recipe(data)["unlock_condition"] = {
        "type": "technology",
        "id": "advanced-smelting",
    }

    package = _load(data)

    assert package.items[0].category == "raw"
    assert package.items[0].unlock_condition.id is None
    assert package.recipes[0].category == "smelting"
    assert package.recipes[0].unlock_condition.type == "technology"
    assert package.recipes[0].unlock_condition.id == "advanced-smelting"


def test_loads_non_technology_unlock_with_omitted_id() -> None:
    data = _minimal_package()
    _first_recipe(data)["unlock_condition"] = {"type": "start-unlocked"}

    package = _load(data)

    assert package.recipes[0].unlock_condition.type == "start-unlocked"
    assert package.recipes[0].unlock_condition.id is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_cost", -1.0),
        ("production_cost", float("nan")),
        ("production_cost", float("inf")),
    ],
)
def test_rejects_negative_or_nonfinite_recipe_numeric_values(
    field: str,
    value: float,
) -> None:
    data = _minimal_package()
    _first_recipe(data)[field] = value

    with pytest.raises(FactoryDataPackageParseError):
        _load(data)


def test_rejects_duplicate_item_ids() -> None:
    data = _minimal_package()
    data["items"] = [{"id": "iron-ore"}, {"id": "iron-ore"}]

    with pytest.raises(FactoryDataPackageParseError, match="duplicate item id"):
        _load(data)


def test_rejects_duplicate_recipe_ids() -> None:
    data = _minimal_package()
    recipe = _first_recipe(data)
    data["recipes"] = [recipe, recipe]

    with pytest.raises(FactoryDataPackageParseError, match="duplicate recipe id"):
        _load(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: data.__setitem__("unknown", "extra"),
        lambda data: _first_item(data).__setitem__("unknown", "extra"),
        lambda data: _first_recipe(data).__setitem__("unknown", "extra"),
        lambda data: _iron_ore_supply(data).__setitem__("unknown", "extra"),
    ],
)
def test_rejects_unknown_object_fields(
    mutator: Callable[[PackageJson], None],
) -> None:
    data = _minimal_package()
    mutator(data)

    with pytest.raises(FactoryDataPackageParseError, match="unknown field"):
        _load(data)


@pytest.mark.parametrize("field", ["items", "recipes"])
def test_rejects_empty_required_arrays(field: str) -> None:
    data = _minimal_package()
    data[field] = []

    with pytest.raises(FactoryDataPackageParseError, match="expected at least one"):
        _load(data)


def test_rejects_unsupported_schema_version() -> None:
    data = _minimal_package()
    data["schema_version"] = "future"

    with pytest.raises(
        FactoryDataPackageParseError,
        match="unsupported schema version",
    ):
        _load(data)


def test_rejects_legacy_v1_schema_version() -> None:
    data = _minimal_package()
    data["schema_version"] = "factory-data-v1"

    with pytest.raises(
        FactoryDataPackageParseError,
        match="unsupported schema version",
    ):
        _load(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: _first_recipe(data).__delitem__("energy_required"),
        lambda data: _first_recipe(data).__setitem__("energy_required", 0.0),
        lambda data: _first_recipe(data).__delitem__("ingredients"),
        lambda data: _first_ingredient(data).__delitem__("amount"),
        lambda data: _first_ingredient(data).__setitem__("amount", -1.0),
        lambda data: _first_ingredient(data).__setitem__("probability", 1.1),
        lambda data: _first_ingredient(data).__setitem__("catalyst_amount", -1.0),
        lambda data: _first_ingredient(data).__setitem__("temperature", float("inf")),
        lambda data: _first_ingredient(data).__setitem__("fluidbox_index", -1),
        lambda data: _first_ingredient(data).__setitem__("name", "copper"),
        lambda data: _first_ingredient(data).__setitem__("type", "fluid"),
        lambda data: _first_recipe(data).__setitem__("source_prototype_type", "boiler"),
    ],
)
def test_rejects_invalid_v2_recipe_fields(
    mutator: Callable[[PackageJson], None],
) -> None:
    data = _minimal_package()
    mutator(data)

    with pytest.raises(FactoryDataPackageParseError):
        _load(data)


def test_accepts_boiler_source_with_explicit_name_and_range_term() -> None:
    data = _minimal_package()
    recipe = _first_recipe(data)
    recipe["source_prototype_type"] = "boiler"
    recipe["source_prototype_name"] = "burner-boiler"
    recipe["results"] = [
        {
            "type": "item",
            "name": "iron-plate",
            "amount_min": 1.0,
            "amount_max": 2.0,
            "probability": 0.5,
            "catalyst_amount": 0.0,
            "fluidbox_index": 0,
        }
    ]

    package = _load(data)

    assert package.recipes[0].source_prototype_type == "boiler"
    assert package.recipes[0].source_prototype_name == "burner-boiler"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: _coefficients(data).__setitem__("copper", 1.0),
        lambda data: _final_demands(data).__setitem__("copper", 1.0),
        lambda data: _external_supplies(data).__setitem__("copper", {"cost": 1.0}),
    ],
)
def test_rejects_unknown_item_references(
    mutator: Callable[[PackageJson], None],
) -> None:
    data = _minimal_package()
    mutator(data)

    with pytest.raises(FactoryDataPackageParseError, match="unknown item id"):
        _load(data)


def test_rejects_zero_coefficient() -> None:
    data = _minimal_package()
    _coefficients(data)["iron-ore"] = 0.0

    with pytest.raises(FactoryDataPackageParseError, match="zero coefficient"):
        _load(data)


def test_rejects_empty_coefficients_and_invalid_kind_and_bad_ids() -> None:
    for patch in (
        lambda data: _first_recipe(data).__setitem__("coefficients", {}),
        lambda data: _first_item(data).__setitem__("kind", "gas"),
        lambda data: _first_item(data).__setitem__("id", "bad id"),
    ):
        data = _minimal_package()
        patch(data)
        with pytest.raises(FactoryDataPackageParseError):
            _load(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: _final_demands(data).__setitem__("iron-plate", -1.0),
        lambda data: _iron_ore_supply(data).__setitem__("cost", -1.0),
        lambda data: _iron_ore_supply(data).__setitem__(
            "capacity",
            float("inf"),
        ),
        lambda data: data.__setitem__("unmet_demand_penalty_rate", float("nan")),
    ],
)
def test_rejects_negative_or_nonfinite_nonnegative_fields(
    mutator: Callable[[PackageJson], None],
) -> None:
    data = _minimal_package()
    mutator(data)

    with pytest.raises(FactoryDataPackageParseError):
        _load(data)
