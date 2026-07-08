from __future__ import annotations

import json
from json import JSONDecodeError
from typing import cast

from game_data_extractor.data_contracts.dataset import OptimizerRecipeDataset
from game_data_extractor.data_contracts.provenance_models import (
    ImportDiagnostic,
    MilestoneRecipeSet,
    StartupSetting,
)
from game_data_extractor.data_contracts.provenance_parsing import (
    parse_dump_provenance_from_optional,
    parse_save_provenance_from_optional,
)
from game_data_extractor.data_contracts.recipe_models import (
    ItemPrototype,
    RawRecipeTerm,
    RawRecipeTermType,
    RecipeCoefficient,
    RecipePrototype,
    RecipeUnlock,
    ResourceSource,
    SourcePrototypeType,
    TechnologyPrototype,
)
from game_data_extractor.data_contracts.types import (
    CoefficientKind,
    DatasetParseError,
    DiagnosticSeverity,
    JsonValue,
    PrototypeType,
)


def parse_dataset_json(text: str) -> OptimizerRecipeDataset:
    try:
        parsed: JsonValue = json.loads(text)
    except JSONDecodeError as error:
        context = "dataset JSON"
        raise DatasetParseError(context, error.msg) from error
    return _dataset_from_mapping(_as_mapping(parsed, "dataset"))


def _dataset_from_mapping(mapping: dict[str, JsonValue]) -> OptimizerRecipeDataset:
    return OptimizerRecipeDataset(
        items=[_item_from_mapping(item) for item in _array(mapping, "items")],
        recipes=[_recipe_from_mapping(recipe) for recipe in _array(mapping, "recipes")],
        technologies=[
            _technology_from_mapping(technology)
            for technology in _array(mapping, "technologies")
        ],
        resource_sources=[
            _resource_from_mapping(source)
            for source in _array(mapping, "resource_sources")
        ],
        startup_settings=[
            _startup_setting_from_mapping(setting)
            for setting in _array(mapping, "startup_settings")
        ],
        save_settings_provenance=parse_save_provenance_from_optional(
            mapping,
            "save_settings_provenance",
        ),
        dump_provenance=parse_dump_provenance_from_optional(
            mapping,
            "dump_provenance",
        ),
        diagnostics=[
            _diagnostic_from_mapping(diagnostic)
            for diagnostic in _array(mapping, "diagnostics")
        ],
        milestones=[
            _milestone_recipe_set_from_mapping(milestone)
            for milestone in _array(mapping, "milestones")
        ],
    )


def _item_from_mapping(value: JsonValue) -> ItemPrototype:
    mapping = _as_mapping(value, "item")
    return ItemPrototype(
        name=_string(mapping, "name"),
        prototype_type=_prototype_type(mapping, "prototype_type"),
        stack_size=_optional_int(mapping, "stack_size"),
    )


def _recipe_from_mapping(value: JsonValue) -> RecipePrototype:
    mapping = _as_mapping(value, "recipe")
    return RecipePrototype(
        name=_string(mapping, "name"),
        category=_string(mapping, "category"),
        energy_required=_number(mapping, "energy_required"),
        coefficients=[
            _coefficient_from_mapping(coefficient)
            for coefficient in _array(mapping, "coefficients")
        ],
        ingredients=[
            _recipe_term_from_mapping(term) for term in _array(mapping, "ingredients")
        ],
        results=[
            _recipe_term_from_mapping(term) for term in _array(mapping, "results")
        ],
        enabled=_boolean(mapping, "enabled", default=False),
        hidden=_boolean(mapping, "hidden", default=False),
        source_prototype_type=cast(
            "SourcePrototypeType",
            _string(mapping, "source_prototype_type", default="recipe"),
        ),
        source_prototype_name=_optional_string(mapping, "source_prototype_name"),
    )


def _coefficient_from_mapping(value: JsonValue) -> RecipeCoefficient:
    mapping = _as_mapping(value, "recipe coefficient")
    return RecipeCoefficient(
        item_name=_string(mapping, "item_name"),
        amount=_number(mapping, "amount"),
        coefficient_kind=_coefficient_kind(mapping, "coefficient_kind"),
    )


def _recipe_term_from_mapping(value: JsonValue) -> RawRecipeTerm:
    mapping = _as_mapping(value, "recipe term")
    return RawRecipeTerm(
        type=_recipe_term_type(mapping, "type"),
        name=_string(mapping, "name"),
        amount=_optional_number(mapping, "amount"),
        amount_min=_optional_number(mapping, "amount_min"),
        amount_max=_optional_number(mapping, "amount_max"),
        probability=_optional_number(mapping, "probability"),
        catalyst_amount=_optional_number(mapping, "catalyst_amount"),
        temperature=_optional_number(mapping, "temperature"),
        minimum_temperature=_optional_number(mapping, "minimum_temperature"),
        maximum_temperature=_optional_number(mapping, "maximum_temperature"),
        fluidbox_index=_optional_int(mapping, "fluidbox_index"),
    )


def _technology_from_mapping(value: JsonValue) -> TechnologyPrototype:
    mapping = _as_mapping(value, "technology")
    return TechnologyPrototype(
        name=_string(mapping, "name"),
        prerequisites=_strings(mapping, "prerequisites"),
        unlocks=[
            _recipe_unlock_from_mapping(unlock) for unlock in _array(mapping, "unlocks")
        ],
        enabled=_boolean(mapping, "enabled", default=True),
        hidden=_boolean(mapping, "hidden", default=False),
    )


def _recipe_unlock_from_mapping(value: JsonValue) -> RecipeUnlock:
    mapping = _as_mapping(value, "recipe unlock")
    return RecipeUnlock(
        technology_name=_string(mapping, "technology_name"),
        recipe_name=_string(mapping, "recipe_name"),
    )


def _resource_from_mapping(value: JsonValue) -> ResourceSource:
    mapping = _as_mapping(value, "resource source")
    return ResourceSource(
        name=_string(mapping, "name"),
        item_name=_string(mapping, "item_name"),
        amount=_number(mapping, "amount"),
        category=_string(mapping, "category"),
    )


def _startup_setting_from_mapping(value: JsonValue) -> StartupSetting:
    mapping = _as_mapping(value, "startup setting")
    return StartupSetting(
        name=_string(mapping, "name"),
        value=_string(mapping, "value"),
        setting_type=_string(mapping, "setting_type", default="startup"),
    )


def _diagnostic_from_mapping(value: JsonValue) -> ImportDiagnostic:
    mapping = _as_mapping(value, "diagnostic")
    return ImportDiagnostic(
        severity=_diagnostic_severity(mapping, "severity"),
        code=_string(mapping, "code"),
        message=_string(mapping, "message"),
        subject=_optional_string(mapping, "subject"),
    )


def _milestone_recipe_set_from_mapping(value: JsonValue) -> MilestoneRecipeSet:
    mapping = _as_mapping(value, "milestone recipe set")
    return MilestoneRecipeSet(
        milestone=_string(mapping, "milestone"),
        recipe_names=_strings(mapping, "recipe_names"),
        diagnostics=[
            _diagnostic_from_mapping(diagnostic)
            for diagnostic in _array(mapping, "diagnostics")
        ],
    )


def _as_mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise DatasetParseError(context, "expected JSON object")


def _array(mapping: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = mapping.get(key, [])
    if isinstance(value, list):
        return value
    raise DatasetParseError(key, "expected JSON array")


def _strings(mapping: dict[str, JsonValue], key: str) -> list[str]:
    values = _array(mapping, key)
    strings: list[str] = []
    for value in values:
        if isinstance(value, str):
            strings.append(value)
        else:
            raise DatasetParseError(key, "expected string array")
    return strings


def _string(
    mapping: dict[str, JsonValue],
    key: str,
    *,
    default: str | None = None,
) -> str:
    value = mapping.get(key, default)
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string")


def _optional_string(mapping: dict[str, JsonValue], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string or null")


def _number(mapping: dict[str, JsonValue], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise DatasetParseError(key, "expected number")


def _optional_number(mapping: dict[str, JsonValue], key: str) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise DatasetParseError(key, "expected number or null")


def _optional_int(mapping: dict[str, JsonValue], key: str) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise DatasetParseError(key, "expected integer or null")


def _boolean(mapping: dict[str, JsonValue], key: str, *, default: bool) -> bool:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        return value
    raise DatasetParseError(key, "expected boolean")


def _coefficient_kind(mapping: dict[str, JsonValue], key: str) -> CoefficientKind:
    value = _string(mapping, key)
    match value:
        case "input":
            return "input"
        case "output":
            return "output"
    raise DatasetParseError(key, "expected input or output")


def _recipe_term_type(mapping: dict[str, JsonValue], key: str) -> RawRecipeTermType:
    value = _string(mapping, key)
    match value:
        case "item" | "fluid" | "unknown":
            return value
    raise DatasetParseError(key, "expected item, fluid, or unknown")


def _diagnostic_severity(
    mapping: dict[str, JsonValue],
    key: str,
) -> DiagnosticSeverity:
    value = _string(mapping, key)
    match value:
        case "info":
            return "info"
        case "warning":
            return "warning"
        case "error":
            return "error"
    raise DatasetParseError(key, "expected info, warning, or error")


def _prototype_type(mapping: dict[str, JsonValue], key: str) -> PrototypeType:
    value = _string(mapping, key)
    match value:
        case "item":
            return "item"
        case "fluid":
            return "fluid"
    raise DatasetParseError(key, "expected item or fluid")
