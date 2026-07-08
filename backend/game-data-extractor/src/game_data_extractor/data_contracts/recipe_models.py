from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from game_data_extractor.data_contracts.types import (
    CoefficientKind,
    DatasetParseError,
    JsonValue,
    PrototypeType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

type RawRecipeTermType = Literal["item", "fluid", "unknown"]
type SourcePrototypeType = Literal["recipe", "boiler"]


@dataclass(frozen=True, slots=True)
class RawRecipeTerm:
    type: RawRecipeTermType
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
class ItemPrototype:
    name: str
    prototype_type: PrototypeType
    stack_size: int | None = None

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "prototype_type": self.prototype_type,
            "stack_size": self.stack_size,
        }


@dataclass(frozen=True, slots=True)
class RecipeCoefficient:
    item_name: str
    amount: float
    coefficient_kind: CoefficientKind

    def __post_init__(self) -> None:
        if self.coefficient_kind == "input" and self.amount >= 0:
            raise DatasetParseError(
                self.item_name,
                "input coefficient must be negative",
            )
        if self.coefficient_kind == "output" and self.amount <= 0:
            raise DatasetParseError(
                self.item_name,
                "output coefficient must be positive",
            )

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "amount": self.amount,
            "coefficient_kind": self.coefficient_kind,
            "item_name": self.item_name,
        }


@dataclass(frozen=True, slots=True)
class RecipePrototype:
    name: str
    category: str
    energy_required: float
    coefficients: Sequence[RecipeCoefficient]
    ingredients: Sequence[RawRecipeTerm] = ()
    results: Sequence[RawRecipeTerm] = ()
    enabled: bool = False
    hidden: bool = False
    source_prototype_type: SourcePrototypeType = "recipe"
    source_prototype_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "coefficients", tuple(self.coefficients))
        object.__setattr__(self, "ingredients", tuple(self.ingredients))
        object.__setattr__(self, "results", tuple(self.results))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "category": self.category,
            "coefficients": [
                coefficient.to_json_value() for coefficient in self.coefficients
            ],
            "enabled": self.enabled,
            "energy_required": self.energy_required,
            "hidden": self.hidden,
            "ingredients": [term.to_json_value() for term in self.ingredients],
            "name": self.name,
            "results": [term.to_json_value() for term in self.results],
            "source_prototype_name": self.source_prototype_name,
            "source_prototype_type": self.source_prototype_type,
        }


@dataclass(frozen=True, slots=True)
class RecipeUnlock:
    technology_name: str
    recipe_name: str

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "recipe_name": self.recipe_name,
            "technology_name": self.technology_name,
        }


@dataclass(frozen=True, slots=True)
class TechnologyPrototype:
    name: str
    prerequisites: Sequence[str] = ()
    science_pack_ingredients: Sequence[str] = ()
    unlocks: Sequence[RecipeUnlock] = ()
    enabled: bool = True
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))
        object.__setattr__(
            self,
            "science_pack_ingredients",
            tuple(self.science_pack_ingredients),
        )
        object.__setattr__(self, "unlocks", tuple(self.unlocks))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "enabled": self.enabled,
            "hidden": self.hidden,
            "name": self.name,
            "prerequisites": list(self.prerequisites),
            "science_pack_ingredients": list(self.science_pack_ingredients),
            "unlocks": [unlock.to_json_value() for unlock in self.unlocks],
        }


@dataclass(frozen=True, slots=True)
class ResourceSource:
    name: str
    item_name: str
    amount: float
    category: str

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "amount": self.amount,
            "category": self.category,
            "item_name": self.item_name,
            "name": self.name,
        }
