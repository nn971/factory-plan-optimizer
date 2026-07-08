from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from json import JSONDecodeError
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NoReturn, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SCHEMA_VERSION = "factory-data-v1"
type ItemKind = Literal["item", "fluid", "unknown"]
type UnlockConditionType = Literal["technology", "start-unlocked", "unknown"]
type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
type JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class UnlockCondition:
    """How an item or recipe becomes available."""

    type: UnlockConditionType = "unknown"
    id: str | None = None

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {"type": self.type, "id": self.id if self.type == "technology" else None}


@dataclass(frozen=True, slots=True)
class Item:
    """Optimizer-facing item or fluid identifier."""

    id: str
    kind: ItemKind = "unknown"
    category: str = "unknown"
    unlock_condition: UnlockCondition = field(default_factory=UnlockCondition)

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {
            "category": self.category,
            "id": self.id,
            "kind": self.kind,
            "unlock_condition": self.unlock_condition.to_json_value(),
        }


@dataclass(frozen=True, slots=True)
class Recipe:
    """Optimizer-facing recipe with signed item coefficients."""

    id: str
    coefficients: Mapping[str, float]
    production_cost: float
    category: str = "unknown"
    unlock_condition: UnlockCondition = field(default_factory=UnlockCondition)

    def __post_init__(self) -> None:
        """Freeze coefficients behind a read-only mapping."""
        object.__setattr__(
            self,
            "coefficients",
            MappingProxyType(dict(self.coefficients)),
        )

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {
            "id": self.id,
            "coefficients": dict(self.coefficients),
            "category": self.category,
            "production_cost": self.production_cost,
            "unlock_condition": self.unlock_condition.to_json_value(),
        }


@dataclass(frozen=True, slots=True)
class ExternalSupply:
    """External item supply policy for the initial optimizer input."""

    cost: float
    capacity: float | None = None

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {"cost": self.cost, "capacity": self.capacity}


@dataclass(frozen=True, slots=True)
class FactoryDataPackage:
    """Canonical optimizer-facing data package."""

    schema_version: str
    items: Sequence[Item]
    recipes: Sequence[Recipe]
    final_demands: Mapping[str, float]
    external_supplies: Mapping[str, ExternalSupply]
    unmet_demand_penalty_rate: float

    def __post_init__(self) -> None:
        """Freeze sequence and mapping fields behind immutable containers."""
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "recipes", tuple(self.recipes))
        object.__setattr__(
            self,
            "final_demands",
            MappingProxyType(dict(self.final_demands)),
        )
        object.__setattr__(
            self,
            "external_supplies",
            MappingProxyType(dict(self.external_supplies)),
        )

    @classmethod
    def from_json(cls, text: str) -> FactoryDataPackage:
        """Parse and validate a package from JSON text."""
        return load_factory_data_package(text)

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {
            "external_supplies": {
                item_id: supply.to_json_value()
                for item_id, supply in self.external_supplies.items()
            },
            "final_demands": dict(self.final_demands),
            "items": [item.to_json_value() for item in self.items],
            "recipes": [recipe.to_json_value() for recipe in self.recipes],
            "schema_version": self.schema_version,
            "unmet_demand_penalty_rate": self.unmet_demand_penalty_rate,
        }

    def to_json(self) -> str:
        """Serialize the package as deterministic pretty-printed JSON."""
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


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
_ITEM_KEYS = frozenset({"id", "kind", "category", "unlock_condition"})
_RECIPE_KEYS = frozenset(
    {"id", "coefficients", "production_cost", "category", "unlock_condition"},
)
_UNLOCK_CONDITION_KEYS = frozenset({"type", "id"})
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
        items.append(
            Item(
                id=item_id,
                kind=kind,
                category=_category(item_mapping, "item.category"),
                unlock_condition=_unlock_condition(
                    item_mapping, "item.unlock_condition"
                ),
            ),
        )
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
                category=_category(recipe_mapping, "recipe.category"),
                unlock_condition=_unlock_condition(
                    recipe_mapping,
                    "recipe.unlock_condition",
                ),
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


def _category(mapping: JsonObject, context: str) -> str:
    value = mapping.get("category", "unknown")
    if not isinstance(value, str):
        _raise_parse_error(context, "expected string")
    _validate_id(value, context)
    return value


def _unknown_unlock() -> UnlockCondition:
    return UnlockCondition(type="unknown", id=None)


def _unlock_condition(mapping: JsonObject, context: str) -> UnlockCondition:
    if "unlock_condition" not in mapping:
        return _unknown_unlock()
    value = mapping["unlock_condition"]
    unlock_mapping = _as_mapping(value, context)
    _reject_unknown_keys(unlock_mapping, _UNLOCK_CONDITION_KEYS, context)
    unlock_type = unlock_mapping.get("type")
    if unlock_type not in ("technology", "start-unlocked", "unknown"):
        _raise_parse_error(
            f"{context}.type",
            "expected technology, start-unlocked, or unknown",
        )
    unlock_id = unlock_mapping.get("id")
    if unlock_type == "technology":
        if not isinstance(unlock_id, str):
            _raise_parse_error(f"{context}.id", "expected string")
        _validate_id(unlock_id, f"{context}.id")
        return UnlockCondition(type="technology", id=unlock_id)
    if unlock_id is not None:
        _raise_parse_error(f"{context}.id", "expected null or omitted")
    return UnlockCondition(type=unlock_type, id=None)


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
