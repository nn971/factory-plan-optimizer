from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts import (
    DatasetParseError,
    ImportDiagnostic,
    ItemPrototype,
    OptimizerRecipeDataset,
    RecipeCoefficient,
    RecipePrototype,
    RecipeUnlock,
    ResourceSource,
    TechnologyPrototype,
)

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import DiagnosticSeverity, JsonValue

FACTORIO_TUPLE_MINIMUM_LENGTH = 2
ITEM_LIKE_PROTOTYPE_TYPES = (
    "item",
    "tool",
    "module",
    "ammo",
    "armor",
    "capsule",
    "gun",
    "item-with-entity-data",
    "item-with-inventory",
    "item-with-label",
    "item-with-tags",
    "repair-tool",
    "selection-tool",
    "spidertron-remote",
    "rail-planner",
    "blueprint",
    "blueprint-book",
    "deconstruction-item",
    "upgrade-item",
    "fluid",
)


def normalize_data_raw_dump(text: str) -> OptimizerRecipeDataset:
    try:
        parsed: JsonValue = json.loads(text)
    except JSONDecodeError as error:
        context = "data.raw JSON"
        raise DatasetParseError(context, error.msg) from error
    data_raw = _mapping(parsed, "data.raw")
    diagnostics: list[ImportDiagnostic] = []

    items = _parse_items(data_raw, diagnostics)
    known_items = {item.name for item in items}
    recipes = _parse_recipes(data_raw, known_items, diagnostics)
    technologies = _parse_technologies(data_raw, diagnostics)
    sources = _parse_resources(data_raw, known_items, diagnostics)

    return OptimizerRecipeDataset(
        items=sorted(items, key=lambda item: item.name),
        recipes=sorted(recipes, key=lambda recipe: recipe.name),
        technologies=sorted(technologies, key=lambda technology: technology.name),
        resource_sources=sorted(sources, key=lambda source: source.name),
        diagnostics=sorted(
            diagnostics,
            key=lambda diagnostic: (
                diagnostic.severity,
                diagnostic.code,
                diagnostic.subject or "",
                diagnostic.message,
            ),
        ),
    )


def _parse_items(
    data_raw: dict[str, JsonValue],
    diagnostics: list[ImportDiagnostic],
) -> list[ItemPrototype]:
    items: list[ItemPrototype] = []
    for prototype_type in ITEM_LIKE_PROTOTYPE_TYPES:
        section = _section(data_raw, prototype_type)
        for name, value in sorted(section.items()):
            try:
                prototype = _mapping(value, f"data.raw {prototype_type} {name}")
                items.append(
                    ItemPrototype(
                        name=_string(prototype, "name", default=name),
                        prototype_type="fluid" if prototype_type == "fluid" else "item",
                        stack_size=_optional_int(prototype, "stack_size"),
                    ),
                )
            except DatasetParseError as error:
                diagnostics.append(
                    _diagnostic("error", "malformed-prototype", str(error), name)
                )
    return items


def _parse_recipes(
    data_raw: dict[str, JsonValue],
    known_items: set[str],
    diagnostics: list[ImportDiagnostic],
) -> list[RecipePrototype]:
    recipes: list[RecipePrototype] = []
    for name, value in sorted(_section(data_raw, "recipe").items()):
        try:
            prototype = _mapping(value, f"data.raw recipe {name}")
            body = _recipe_body(prototype, name, diagnostics)
            recipe_name = _string(prototype, "name", default=name)
            coefficients = _recipe_coefficients(
                body, recipe_name, known_items, diagnostics
            )
            enabled = _bool(body, "enabled", default=True)
            hidden = _bool(body, "hidden", default=False)
            if hidden:
                diagnostics.append(
                    _diagnostic(
                        "info", "hidden-recipe", "recipe is hidden", recipe_name
                    )
                )
            if not enabled:
                diagnostics.append(
                    _diagnostic(
                        "info",
                        "disabled-recipe",
                        "recipe is not initially enabled",
                        recipe_name,
                    )
                )
            recipes.append(
                RecipePrototype(
                    name=recipe_name,
                    category=_string(body, "category", default="crafting"),
                    energy_required=_number(
                        body,
                        "energy_required",
                        default=0.5,
                    ),
                    coefficients=coefficients,
                    enabled=enabled,
                    hidden=hidden,
                ),
            )
        except DatasetParseError as error:
            diagnostics.append(
                _diagnostic("error", "malformed-prototype", str(error), name)
            )
    return recipes


def _recipe_body(
    prototype: dict[str, JsonValue],
    name: str,
    diagnostics: list[ImportDiagnostic],
) -> dict[str, JsonValue]:
    if "normal" in prototype or "expensive" in prototype:
        if "expensive" in prototype:
            diagnostics.append(
                _diagnostic(
                    "warning",
                    "unsupported-recipe-variant",
                    "expensive recipe variant ignored",
                    name,
                )
            )
        if "normal" in prototype:
            return _mapping(prototype["normal"], f"recipe {name} normal")
        if "expensive" in prototype:
            return _mapping(prototype["expensive"], f"recipe {name} expensive")
    return prototype


def _recipe_coefficients(
    body: dict[str, JsonValue],
    recipe_name: str,
    known_items: set[str],
    diagnostics: list[ImportDiagnostic],
) -> list[RecipeCoefficient]:
    coefficients: list[RecipeCoefficient] = []
    for item_name, amount in _products(
        body.get("ingredients", []), f"recipe {recipe_name} ingredients"
    ):
        _diagnose_unknown(item_name, known_items, diagnostics)
        coefficients.append(
            RecipeCoefficient(
                item_name=item_name, amount=-amount, coefficient_kind="input"
            )
        )
    outputs = body.get("results")
    if outputs is not None:
        products = _products(outputs, f"recipe {recipe_name} results")
    else:
        products = [
            (_string(body, "result"), _number(body, "result_count", default=1.0))
        ]
    for item_name, amount in products:
        _diagnose_unknown(item_name, known_items, diagnostics)
        coefficients.append(
            RecipeCoefficient(
                item_name=item_name, amount=amount, coefficient_kind="output"
            )
        )
    return coefficients


def _parse_technologies(
    data_raw: dict[str, JsonValue],
    diagnostics: list[ImportDiagnostic],
) -> list[TechnologyPrototype]:
    technologies: list[TechnologyPrototype] = []
    for name, value in sorted(_section(data_raw, "technology").items()):
        try:
            prototype = _mapping(value, f"data.raw technology {name}")
            tech_name = _string(prototype, "name", default=name)
            technologies.append(
                TechnologyPrototype(
                    name=tech_name,
                    prerequisites=_strings(
                        prototype.get("prerequisites", []),
                        "technology prerequisites",
                    ),
                    unlocks=[
                        RecipeUnlock(
                            technology_name=tech_name,
                            recipe_name=_string(effect, "recipe"),
                        )
                        for effect in (
                            _mapping(effect, "technology effect")
                            for effect in _list(
                                prototype.get("effects", []), "technology effects"
                            )
                        )
                        if effect.get("type") == "unlock-recipe"
                    ],
                    enabled=_bool(prototype, "enabled", default=True),
                    hidden=_bool(prototype, "hidden", default=False),
                ),
            )
        except DatasetParseError as error:
            diagnostics.append(
                _diagnostic("error", "malformed-prototype", str(error), name)
            )
    return technologies


def _parse_resources(
    data_raw: dict[str, JsonValue],
    known_items: set[str],
    diagnostics: list[ImportDiagnostic],
) -> list[ResourceSource]:
    sources: list[ResourceSource] = []
    for name, value in sorted(_section(data_raw, "resource").items()):
        try:
            prototype = _mapping(value, f"data.raw resource {name}")
            minable = _mapping(prototype.get("minable", {}), f"resource {name} minable")
            products = (
                _products(minable["results"], f"resource {name} results")
                if "results" in minable
                else [
                    (
                        _string(minable, "result"),
                        _number(minable, "count", default=1.0),
                    )
                ]
            )
            source_count = len(products)
            for item_name, amount in products:
                _diagnose_unknown(item_name, known_items, diagnostics)
                source_name = name if source_count == 1 else f"{name}:{item_name}"
                sources.append(
                    ResourceSource(
                        name=source_name,
                        item_name=item_name,
                        amount=amount,
                        category=_string(prototype, "category", default="basic-solid"),
                    )
                )
        except DatasetParseError as error:
            diagnostics.append(
                _diagnostic("error", "malformed-prototype", str(error), name)
            )
    return sources


def _products(value: JsonValue, context: str) -> list[tuple[str, float]]:
    products: list[tuple[str, float]] = []
    for entry in _list(value, context):
        if (
            isinstance(entry, list)
            and len(entry) >= FACTORIO_TUPLE_MINIMUM_LENGTH
            and isinstance(entry[0], str)
        ):
            amount = entry[1]
            if isinstance(amount, int | float) and not isinstance(amount, bool):
                products.append((entry[0], float(amount)))
                continue
        if isinstance(entry, dict):
            products.append(
                (
                    _string(entry, "name"),
                    _number(
                        entry,
                        "amount",
                        default=_number(entry, "amount_min", default=1.0),
                    ),
                )
            )
            continue
        raise DatasetParseError(context, "expected product array or object")
    return products


def _diagnose_unknown(
    item_name: str, known_items: set[str], diagnostics: list[ImportDiagnostic]
) -> None:
    if item_name not in known_items:
        diagnostics.append(
            _diagnostic(
                "warning",
                "unknown-item-reference",
                f"unknown item/fluid reference: {item_name}",
                item_name,
            )
        )


def _diagnostic(
    severity: DiagnosticSeverity, code: str, message: str, subject: str | None
) -> ImportDiagnostic:
    return ImportDiagnostic(
        severity=severity, code=code, message=message, subject=subject
    )


def _section(data_raw: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    return _mapping(data_raw.get(key, {}), f"data.raw {key}")


def _mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise DatasetParseError(context, "expected JSON object")


def _list(value: JsonValue, context: str) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    raise DatasetParseError(context, "expected JSON array")


def _strings(value: JsonValue, context: str) -> list[str]:
    strings: list[str] = []
    for entry in _list(value, context):
        if not isinstance(entry, str):
            raise DatasetParseError(context, "expected string array")
        strings.append(entry)
    return strings


def _string(
    mapping: dict[str, JsonValue], key: str, *, default: str | None = None
) -> str:
    value = mapping.get(key, default)
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string")


def _number(
    mapping: dict[str, JsonValue], key: str, *, default: float | None = None
) -> float:
    value = mapping.get(key, default)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise DatasetParseError(key, "expected number")


def _optional_int(mapping: dict[str, JsonValue], key: str) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise DatasetParseError(key, "expected integer or null")


def _bool(mapping: dict[str, JsonValue], key: str, *, default: bool) -> bool:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        return value
    raise DatasetParseError(key, "expected boolean")
