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


def _minimal_package() -> PackageJson:
    return {
        "schema_version": SCHEMA_VERSION,
        "items": [{"id": "iron-ore"}, {"id": "iron-plate", "kind": "item"}],
        "recipes": [
            {
                "id": "smelt-iron",
                "coefficients": {"iron-ore": -1.0, "iron-plate": 1.0},
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
    assert package.items[1].kind == "item"
    assert isinstance(package.recipes, tuple)
    assert dict(package.recipes[0].coefficients) == {
        "iron-ore": -1.0,
        "iron-plate": 1.0,
    }
    assert package.external_supplies["iron-ore"].capacity is None


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
