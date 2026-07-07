from __future__ import annotations

import json
import math
from json import JSONDecodeError
from typing import NoReturn, cast

from factory_plan_optimizer.optimizer.models import (
    SCHEMA_VERSION,
    ExternalSupply,
    FactoryDataPackage,
    Item,
    Recipe,
)

type JsonObject = dict[str, object]

_PACKAGE_KEYS = frozenset(
    {
        "schema_version",
        "items",
        "recipes",
        "final_demands",
        "external_supplies",
        "unmet_demand_penalty_rate",
    },
)
_ITEM_KEYS = frozenset({"id", "kind"})
_RECIPE_KEYS = frozenset({"id", "coefficients", "production_cost"})
_EXTERNAL_SUPPLY_KEYS = frozenset({"cost", "capacity"})


class FactoryDataPackageParseError(ValueError):
    """Raised when factory data package JSON cannot be parsed or validated."""

    def __init__(self, context: str, message: str) -> None:
        """Build a parse error with a validation context and message."""
        super().__init__(f"{context}: {message}")
        self.context = context
        self.message = message


def load_factory_data_package(text: str) -> FactoryDataPackage:
    try:
        parsed = json.loads(text)
    except JSONDecodeError as error:
        _raise_parse_error("factory data JSON", error.msg, error)
    mapping = _as_mapping(parsed, "factory data package")
    _reject_unknown_keys(mapping, _PACKAGE_KEYS, "factory data package")
    schema_version = _schema_version(mapping)
    items = _items(mapping)
    item_ids = {item.id for item in items}
    unmet_demand_penalty_rate = _nonnegative_number(
        mapping,
        "unmet_demand_penalty_rate",
    )
    return FactoryDataPackage(
        schema_version=schema_version,
        items=items,
        recipes=_recipes(mapping, item_ids),
        final_demands=_nonnegative_number_map(mapping, "final_demands", item_ids),
        external_supplies=_external_supplies(mapping, item_ids),
        unmet_demand_penalty_rate=unmet_demand_penalty_rate,
    )


def _schema_version(mapping: JsonObject) -> str:
    value = _string(mapping, "schema_version")
    if value != SCHEMA_VERSION:
        _raise_parse_error("schema_version", "unsupported schema version")
    return value


def _items(mapping: JsonObject) -> tuple[Item, ...]:
    seen: set[str] = set()
    items: list[Item] = []
    item_values = _array(mapping, "items")
    if not item_values:
        _raise_parse_error("items", "expected at least one item")
    for value in item_values:
        item_mapping = _as_mapping(value, "item")
        _reject_unknown_keys(item_mapping, _ITEM_KEYS, "item")
        item_id = _id(item_mapping, "id")
        if item_id in seen:
            _raise_parse_error("items", f"duplicate item id {item_id!r}")
        seen.add(item_id)
        kind = item_mapping.get("kind", "unknown")
        if kind not in ("item", "fluid", "unknown"):
            _raise_parse_error("item.kind", "expected item, fluid, or unknown")
        items.append(Item(id=item_id, kind=kind))
    return tuple(items)


def _recipes(mapping: JsonObject, item_ids: set[str]) -> tuple[Recipe, ...]:
    seen: set[str] = set()
    recipes: list[Recipe] = []
    recipe_values = _array(mapping, "recipes")
    if not recipe_values:
        _raise_parse_error("recipes", "expected at least one recipe")
    for value in recipe_values:
        recipe_mapping = _as_mapping(value, "recipe")
        _reject_unknown_keys(recipe_mapping, _RECIPE_KEYS, "recipe")
        recipe_id = _id(recipe_mapping, "id")
        if recipe_id in seen:
            _raise_parse_error("recipes", f"duplicate recipe id {recipe_id!r}")
        seen.add(recipe_id)
        coefficients = _coefficient_map(recipe_mapping, item_ids)
        recipes.append(
            Recipe(
                id=recipe_id,
                coefficients=coefficients,
                production_cost=_nonnegative_number(recipe_mapping, "production_cost"),
            ),
        )
    return tuple(recipes)


def _coefficient_map(mapping: JsonObject, item_ids: set[str]) -> dict[str, float]:
    coefficients = _as_mapping(mapping.get("coefficients"), "coefficients")
    if not coefficients:
        _raise_parse_error("coefficients", "expected at least one coefficient")
    result: dict[str, float] = {}
    for item_id, value in coefficients.items():
        _validate_id(item_id, "coefficient item id")
        if item_id not in item_ids:
            _raise_parse_error("coefficients", f"unknown item id {item_id!r}")
        coefficient = _number_value(value, f"coefficients[{item_id}]")
        if coefficient == 0.0:
            _raise_parse_error("coefficients", "zero coefficient is not allowed")
        result[item_id] = coefficient
    return result


def _external_supplies(
    mapping: JsonObject,
    item_ids: set[str],
) -> dict[str, ExternalSupply]:
    supplies = _as_mapping(mapping.get("external_supplies"), "external_supplies")
    result: dict[str, ExternalSupply] = {}
    for item_id, value in supplies.items():
        _validate_known_item_id(item_id, "external_supplies", item_ids)
        supply_mapping = _as_mapping(value, "external_supply")
        _reject_unknown_keys(
            supply_mapping,
            _EXTERNAL_SUPPLY_KEYS,
            "external_supply",
        )
        capacity_value = supply_mapping.get("capacity")
        capacity = (
            None
            if capacity_value is None
            else _nonnegative_number_value(
                capacity_value,
                f"external_supplies[{item_id}].capacity",
            )
        )
        result[item_id] = ExternalSupply(
            cost=_nonnegative_number(supply_mapping, "cost"),
            capacity=capacity,
        )
    return result


def _nonnegative_number_map(
    mapping: JsonObject,
    key: str,
    item_ids: set[str],
) -> dict[str, float]:
    values = _as_mapping(mapping.get(key), key)
    result: dict[str, float] = {}
    for item_id, value in values.items():
        _validate_known_item_id(item_id, key, item_ids)
        result[item_id] = _nonnegative_number_value(value, f"{key}[{item_id}]")
    return result


def _as_mapping(value: object, context: str) -> JsonObject:
    if isinstance(value, dict):
        return cast("JsonObject", value)
    return _raise_parse_error(context, "expected JSON object")


def _reject_unknown_keys(
    mapping: JsonObject,
    allowed: frozenset[str],
    context: str,
) -> None:
    unknown_keys = sorted(set(mapping) - allowed)
    if unknown_keys:
        joined_keys = ", ".join(repr(key) for key in unknown_keys)
        _raise_parse_error(context, f"unknown field(s): {joined_keys}")


def _array(mapping: JsonObject, key: str) -> list[object]:
    value = mapping.get(key)
    if isinstance(value, list):
        return value
    return _raise_parse_error(key, "expected JSON array")


def _string(mapping: JsonObject, key: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str):
        return value
    return _raise_parse_error(key, "expected string")


def _id(mapping: JsonObject, key: str) -> str:
    value = _string(mapping, key)
    _validate_id(value, key)
    return value


def _validate_id(value: str, context: str) -> None:
    if not value or any(character.isspace() for character in value):
        _raise_parse_error(context, "expected non-empty string with no whitespace")


def _validate_known_item_id(value: str, context: str, item_ids: set[str]) -> None:
    _validate_id(value, context)
    if value not in item_ids:
        _raise_parse_error(context, f"unknown item id {value!r}")


def _number_value(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        _raise_parse_error(context, "expected number")
    number = float(value)
    if not math.isfinite(number):
        _raise_parse_error(context, "expected finite number")
    return number


def _nonnegative_number(mapping: JsonObject, key: str) -> float:
    return _nonnegative_number_value(mapping.get(key), key)


def _nonnegative_number_value(value: object, context: str) -> float:
    number = _number_value(value, context)
    if number < 0.0:
        _raise_parse_error(context, "expected nonnegative number")
    return number


def _raise_parse_error(
    context: str,
    message: str,
    cause: BaseException | None = None,
) -> NoReturn:
    if cause is None:
        raise FactoryDataPackageParseError(context, message)
    raise FactoryDataPackageParseError(context, message) from cause
