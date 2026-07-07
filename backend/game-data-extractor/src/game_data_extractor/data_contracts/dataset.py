from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game_data_extractor.data_contracts.provenance_models import (
        DumpProvenance,
        ImportDiagnostic,
        MilestoneRecipeSet,
        SaveSettingsProvenance,
        StartupSetting,
    )
    from game_data_extractor.data_contracts.recipe_models import (
        ItemPrototype,
        RecipePrototype,
        ResourceSource,
        TechnologyPrototype,
    )
    from game_data_extractor.data_contracts.types import JsonValue


@dataclass(frozen=True, slots=True)
class OptimizerRecipeDataset:
    items: Sequence[ItemPrototype] = ()
    recipes: Sequence[RecipePrototype] = ()
    technologies: Sequence[TechnologyPrototype] = ()
    resource_sources: Sequence[ResourceSource] = ()
    startup_settings: Sequence[StartupSetting] = ()
    save_settings_provenance: SaveSettingsProvenance | None = None
    dump_provenance: DumpProvenance | None = None
    diagnostics: Sequence[ImportDiagnostic] = ()
    milestones: Sequence[MilestoneRecipeSet] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "recipes", tuple(self.recipes))
        object.__setattr__(self, "technologies", tuple(self.technologies))
        object.__setattr__(self, "resource_sources", tuple(self.resource_sources))
        object.__setattr__(self, "startup_settings", tuple(self.startup_settings))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "milestones", tuple(self.milestones))

    @classmethod
    def from_json(cls, text: str) -> OptimizerRecipeDataset:
        from game_data_extractor.data_contracts.parsing import (  # noqa: PLC0415
            parse_dataset_json,
        )

        return parse_dataset_json(text)

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "diagnostics": [
                diagnostic.to_json_value() for diagnostic in self.diagnostics
            ],
            "dump_provenance": None
            if self.dump_provenance is None
            else self.dump_provenance.to_json_value(),
            "items": [item.to_json_value() for item in self.items],
            "milestones": [milestone.to_json_value() for milestone in self.milestones],
            "recipes": [recipe.to_json_value() for recipe in self.recipes],
            "resource_sources": [
                source.to_json_value() for source in self.resource_sources
            ],
            "save_settings_provenance": None
            if self.save_settings_provenance is None
            else self.save_settings_provenance.to_json_value(),
            "startup_settings": [
                setting.to_json_value() for setting in self.startup_settings
            ],
            "technologies": [
                technology.to_json_value() for technology in self.technologies
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"
