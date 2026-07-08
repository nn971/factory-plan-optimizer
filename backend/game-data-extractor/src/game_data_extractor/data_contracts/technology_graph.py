from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game_data_extractor.data_contracts.dataset import OptimizerRecipeDataset
    from game_data_extractor.data_contracts.types import JsonValue


def technology_prerequisite_graph_json_value(
    dataset: OptimizerRecipeDataset,
) -> dict[str, JsonValue]:
    """Return a reproducible technology prerequisite graph helper artifact."""
    return {
        "technologies": [
            {
                "enabled": technology.enabled,
                "hidden": technology.hidden,
                "name": technology.name,
                "prerequisites": list(technology.prerequisites),
                "science_pack_ingredients": list(technology.science_pack_ingredients),
                "unlocked_recipes": [
                    unlock.recipe_name
                    for unlock in sorted(
                        technology.unlocks,
                        key=lambda unlock: unlock.recipe_name,
                    )
                ],
            }
            for technology in sorted(dataset.technologies, key=lambda item: item.name)
        ],
    }
