from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from json import JSONDecodeError
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NoReturn, cast

from game_data_extractor.data_contracts.provenance_models import (
    ImportDiagnostic,
    MilestoneRecipeSet,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SCHEMA_VERSION = "factory-data-v2"
type ItemKind = Literal["item", "fluid", "unknown"]
type RecipeTermType = Literal["item", "fluid", "unknown"]
type SourcePrototypeType = Literal["recipe", "boiler"]
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
class RecipeTerm:
    """Canonical Factorio recipe ingredient/result term."""

    type: RecipeTermType
    name: str
    amount: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    probability: float | None = None
    catalyst_amount: float | None = None
    temperature: float | None = None
    minimum_temperature: float | None = None
    maximum_temperature: float | None = None
    fluidbox_index: int | None = None

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {
            key: value
            for key, value in {
                "type": self.type,
                "name": self.name,
                "amount": self.amount,
                "amount_min": self.amount_min,
                "amount_max": self.amount_max,
                "probability": self.probability,
                "catalyst_amount": self.catalyst_amount,
                "temperature": self.temperature,
                "minimum_temperature": self.minimum_temperature,
                "maximum_temperature": self.maximum_temperature,
                "fluidbox_index": self.fluidbox_index,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class Recipe:
    """Optimizer-facing recipe with signed item coefficients."""

    id: str
    coefficients: Mapping[str, float]
    energy_required: float
    ingredients: Sequence[RecipeTerm]
    results: Sequence[RecipeTerm]
    production_cost: float
    category: str = "unknown"
    unlock_condition: UnlockCondition = field(default_factory=UnlockCondition)
    source_prototype_type: SourcePrototypeType = "recipe"
    source_prototype_name: str | None = None

    def __post_init__(self) -> None:
        """Freeze coefficients behind a read-only mapping."""
        object.__setattr__(
            self,
            "coefficients",
            MappingProxyType(dict(self.coefficients)),
        )
        object.__setattr__(self, "ingredients", tuple(self.ingredients))
        object.__setattr__(self, "results", tuple(self.results))
        if (
            self.source_prototype_name is None
            and self.source_prototype_type == "recipe"
        ):
            object.__setattr__(self, "source_prototype_name", self.id)

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {
            "id": self.id,
            "coefficients": dict(self.coefficients),
            "energy_required": self.energy_required,
            "ingredients": [term.to_json_value() for term in self.ingredients],
            "results": [term.to_json_value() for term in self.results],
            "category": self.category,
            "production_cost": self.production_cost,
            "source_prototype_name": self.source_prototype_name,
            "source_prototype_type": self.source_prototype_type,
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
    raw_input_suggestions: Sequence[str] | None = None
    milestones: Sequence[MilestoneRecipeSet] = ()

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
        if self.raw_input_suggestions is not None:
            object.__setattr__(
                self,
                "raw_input_suggestions",
                tuple(self.raw_input_suggestions),
            )
        object.__setattr__(self, "milestones", tuple(self.milestones))

    @classmethod
    def from_json(cls, text: str) -> FactoryDataPackage:
        """Parse and validate a package from JSON text."""
        return load_factory_data_package(text)

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        value: dict[str, JsonValue] = {
            "external_supplies": {
                item_id: supply.to_json_value()
                for item_id, supply in self.external_supplies.items()
            },
            "final_demands": dict(self.final_demands),
            "items": [item.to_json_value() for item in self.items],
            "milestones": [milestone.to_json_value() for milestone in self.milestones],
            "recipes": [recipe.to_json_value() for recipe in self.recipes],
            "schema_version": self.schema_version,
            "unmet_demand_penalty_rate": self.unmet_demand_penalty_rate,
        }
        if self.raw_input_suggestions is not None:
            value["raw_input_suggestions"] = list(self.raw_input_suggestions)
        return value

    def to_json(self) -> str:
        """Serialize the package as deterministic pretty-printed JSON."""
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


_PACKAGE_KEYS = frozenset(
    {
        "schema_version",
        "items",
        "milestones",
        "recipes",
        "final_demands",
        "external_supplies",
        "raw_input_suggestions",
        "unmet_demand_penalty_rate",
    },
)
_ITEM_KEYS = frozenset({"id", "kind", "category", "unlock_condition"})
_RECIPE_KEYS = frozenset(
    {
        "id",
        "coefficients",
        "energy_required",
        "ingredients",
        "results",
        "production_cost",
        "category",
        "unlock_condition",
        "source_prototype_type",
        "source_prototype_name",
    },
)
_RECIPE_TERM_KEYS = frozenset(
    {
        "type",
        "name",
        "amount",
        "amount_min",
        "amount_max",
        "probability",
        "catalyst_amount",
        "temperature",
        "minimum_temperature",
        "maximum_temperature",
        "fluidbox_index",
    },
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
    item_kinds: dict[str, ItemKind] = {item.id: item.kind for item in items}
    unmet_demand_penalty_rate = _nonnegative_number(
        mapping,
        "unmet_demand_penalty_rate",
    )
    return FactoryDataPackage(
        schema_version=schema_version,
        items=items,
        recipes=_recipes(mapping, item_kinds),
        final_demands=_nonnegative_number_map(
            mapping,
            "final_demands",
            set(item_kinds),
        ),
        external_supplies=_external_supplies(mapping, set(item_kinds)),
        unmet_demand_penalty_rate=unmet_demand_penalty_rate,
        raw_input_suggestions=_raw_input_suggestions(mapping, set(item_kinds)),
        milestones=_milestones(mapping),
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


def _recipes(
    mapping: JsonObject,
    item_kinds: Mapping[str, ItemKind],
) -> tuple[Recipe, ...]:
    seen: set[str] = set()
    recipes: list[Recipe] = []
    item_ids = set(item_kinds)
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
        source_type = recipe_mapping.get("source_prototype_type", "recipe")
        if source_type not in ("recipe", "boiler"):
            _raise_parse_error(
                "recipe.source_prototype_type",
                "expected recipe or boiler",
            )
        if source_type == "boiler" and "source_prototype_name" not in recipe_mapping:
            _raise_parse_error("recipe.source_prototype_name", "required for boiler")
        source_name = recipe_mapping.get("source_prototype_name", recipe_id)
        if not isinstance(source_name, str):
            _raise_parse_error("recipe.source_prototype_name", "expected string")
        _validate_id(source_name, "recipe.source_prototype_name")
        recipes.append(
            Recipe(
                id=recipe_id,
                coefficients=coefficients,
                energy_required=_positive_number(recipe_mapping, "energy_required"),
                ingredients=_recipe_terms(recipe_mapping, "ingredients", item_kinds),
                results=_recipe_terms(recipe_mapping, "results", item_kinds),
                production_cost=_nonnegative_number(recipe_mapping, "production_cost"),
                category=_category(recipe_mapping, "recipe.category"),
                unlock_condition=_unlock_condition(
                    recipe_mapping,
                    "recipe.unlock_condition",
                ),
                source_prototype_type=source_type,
                source_prototype_name=source_name,
            ),
        )
    return tuple(recipes)


def _recipe_terms(
    mapping: JsonObject,
    key: str,
    item_kinds: Mapping[str, ItemKind],
) -> tuple[RecipeTerm, ...]:
    terms = []
    for index, value in enumerate(_array(mapping, key)):
        context = f"recipe.{key}[{index}]"
        term_mapping = _as_mapping(value, context)
        _reject_unknown_keys(term_mapping, _RECIPE_TERM_KEYS, context)
        term_type = term_mapping.get("type")
        if term_type not in ("item", "fluid", "unknown"):
            _raise_parse_error(f"{context}.type", "expected item, fluid, or unknown")
        name = _id(term_mapping, "name")
        if name not in item_kinds:
            _raise_parse_error(f"{context}.name", f"unknown item id {name!r}")
        if term_type in ("item", "fluid") and item_kinds[name] != term_type:
            _raise_parse_error(f"{context}.type", f"expected known kind {term_type}")
        amount = _optional_positive_number(term_mapping, "amount", context)
        amount_min = _optional_positive_number(term_mapping, "amount_min", context)
        amount_max = _optional_positive_number(term_mapping, "amount_max", context)
        if amount is None and amount_min is None and amount_max is None:
            _raise_parse_error(context, "expected at least one quantity field")
        if (
            amount_min is not None
            and amount_max is not None
            and amount_min > amount_max
        ):
            _raise_parse_error(context, "amount_min must be <= amount_max")
        terms.append(
            RecipeTerm(
                type=term_type,
                name=name,
                amount=amount,
                amount_min=amount_min,
                amount_max=amount_max,
                probability=_optional_probability(term_mapping, "probability", context),
                catalyst_amount=_optional_nonnegative_number(
                    term_mapping,
                    "catalyst_amount",
                    context,
                ),
                temperature=_optional_nonnegative_number(
                    term_mapping,
                    "temperature",
                    context,
                ),
                minimum_temperature=_optional_nonnegative_number(
                    term_mapping,
                    "minimum_temperature",
                    context,
                ),
                maximum_temperature=_optional_nonnegative_number(
                    term_mapping,
                    "maximum_temperature",
                    context,
                ),
                fluidbox_index=_optional_nonnegative_int(
                    term_mapping,
                    "fluidbox_index",
                    context,
                ),
            )
        )
    return tuple(terms)


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


def _raw_input_suggestions(
    mapping: JsonObject,
    item_ids: set[str],
) -> tuple[str, ...] | None:
    if "raw_input_suggestions" not in mapping:
        return None
    values = mapping["raw_input_suggestions"]
    if not isinstance(values, list):
        _raise_parse_error("raw_input_suggestions", "expected JSON array")
    seen: set[str] = set()
    result: list[str] = []
    for index, value in enumerate(values):
        context = f"raw_input_suggestions[{index}]"
        if not isinstance(value, str):
            _raise_parse_error(context, "expected string")
        _validate_known_item_id(value, context, item_ids)
        if value in seen:
            _raise_parse_error("raw_input_suggestions", f"duplicate item id {value!r}")
        seen.add(value)
        result.append(value)
    return tuple(result)


def _milestones(mapping: JsonObject) -> tuple[MilestoneRecipeSet, ...]:
    result: list[MilestoneRecipeSet] = []
    milestone_values = mapping.get("milestones", [])
    if not isinstance(milestone_values, list):
        _raise_parse_error("milestones", "expected JSON array")
    for index, value in enumerate(milestone_values):
        context = f"milestones[{index}]"
        milestone_mapping = _as_mapping(value, context)
        milestone = _string(milestone_mapping, "milestone")
        recipe_names = tuple(_strings(milestone_mapping, "recipe_names"))
        diagnostics = tuple(
            _diagnostic(diagnostic, f"{context}.diagnostics")
            for diagnostic in _array(milestone_mapping, "diagnostics")
        )
        result.append(
            MilestoneRecipeSet(
                milestone=milestone,
                recipe_names=recipe_names,
                diagnostics=diagnostics,
            )
        )
    return tuple(result)


def _strings(mapping: JsonObject, key: str) -> list[str]:
    values = _array(mapping, key)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            _raise_parse_error(key, "expected string array")
        result.append(value)
    return result


def _diagnostic(value: object, context: str) -> ImportDiagnostic:
    mapping = _as_mapping(value, context)
    severity = _string(mapping, "severity")
    if severity not in ("info", "warning", "error"):
        _raise_parse_error(f"{context}.severity", "expected info, warning, or error")
    subject = mapping.get("subject")
    if subject is not None and not isinstance(subject, str):
        _raise_parse_error(f"{context}.subject", "expected string or null")
    return ImportDiagnostic(
        severity=cast("Literal['info', 'warning', 'error']", severity),
        code=_string(mapping, "code"),
        message=_string(mapping, "message"),
        subject=subject,
    )


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


def _positive_number(mapping: JsonObject, key: str) -> float:
    number = _number_value(mapping.get(key), key)
    if number <= 0.0:
        _raise_parse_error(key, "expected positive number")
    return number


def _optional_positive_number(
    mapping: JsonObject,
    key: str,
    context: str,
) -> float | None:
    if key not in mapping:
        return None
    number = _number_value(mapping[key], f"{context}.{key}")
    if number <= 0.0:
        _raise_parse_error(f"{context}.{key}", "expected positive number")
    return number


def _optional_nonnegative_number(
    mapping: JsonObject,
    key: str,
    context: str,
) -> float | None:
    if key not in mapping:
        return None
    return _nonnegative_number_value(mapping[key], f"{context}.{key}")


def _optional_probability(
    mapping: JsonObject,
    key: str,
    context: str,
) -> float | None:
    if key not in mapping:
        return None
    number = _number_value(mapping[key], f"{context}.{key}")
    if number < 0.0 or number > 1.0:
        _raise_parse_error(f"{context}.{key}", "expected number in [0, 1]")
    return number


def _optional_nonnegative_int(
    mapping: JsonObject,
    key: str,
    context: str,
) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        _raise_parse_error(f"{context}.{key}", "expected nonnegative integer")
    if value < 0:
        _raise_parse_error(f"{context}.{key}", "expected nonnegative integer")
    return value


def _raise_parse_error(
    context: str,
    message: str,
    cause: BaseException | None = None,
) -> NoReturn:
    if cause is None:
        raise FactoryDataPackageParseError(context, message)
    raise FactoryDataPackageParseError(context, message) from cause
