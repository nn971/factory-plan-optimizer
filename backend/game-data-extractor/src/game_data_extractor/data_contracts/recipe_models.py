from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game_data_extractor.data_contracts.types import (
    CoefficientKind,
    DatasetParseError,
    JsonValue,
    PrototypeType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


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
    enabled: bool = False
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "coefficients", tuple(self.coefficients))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "category": self.category,
            "coefficients": [
                coefficient.to_json_value() for coefficient in self.coefficients
            ],
            "enabled": self.enabled,
            "energy_required": self.energy_required,
            "hidden": self.hidden,
            "name": self.name,
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
    unlocks: Sequence[RecipeUnlock] = ()
    enabled: bool = True
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))
        object.__setattr__(self, "unlocks", tuple(self.unlocks))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "enabled": self.enabled,
            "hidden": self.hidden,
            "name": self.name,
            "prerequisites": list(self.prerequisites),
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
