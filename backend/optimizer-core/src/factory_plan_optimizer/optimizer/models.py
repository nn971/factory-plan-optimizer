from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SCHEMA_VERSION = "factory-data-v1"
type ItemKind = Literal["item", "fluid", "unknown"]
type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)


@dataclass(frozen=True, slots=True)
class Item:
    """Optimizer-facing item or fluid identifier."""

    id: str
    kind: ItemKind = "unknown"

    def to_json_value(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""
        return {"id": self.id, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class Recipe:
    """Optimizer-facing recipe with signed item coefficients."""

    id: str
    coefficients: Mapping[str, float]
    production_cost: float

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
            "production_cost": self.production_cost,
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
        from factory_plan_optimizer.optimizer.factory_data_loader import (  # noqa: PLC0415
            load_factory_data_package,
        )

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
