import json
from pathlib import Path

import pytest

from game_data_extractor.__main__ import main
from game_data_extractor.data_contracts import (
    ItemPrototype,
    OptimizerRecipeDataset,
    RecipeCoefficient,
    RecipePrototype,
)


def test_export_factory_data_cli_writes_canonical_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "default.factory-data.json"
    dataset = OptimizerRecipeDataset(
        items=(
            ItemPrototype("iron-ore", "item"),
            ItemPrototype("iron-plate", "item"),
        ),
        recipes=(
            RecipePrototype(
                name="iron-smelting",
                category="smelting",
                energy_required=3.2,
                coefficients=(
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("iron-plate", 1.0, "output"),
                ),
            ),
        ),
    )
    dataset_path.write_text(dataset.to_json(), encoding="utf-8")

    status = main(
        [
            "export-factory-data",
            "--dataset",
            str(dataset_path),
            "--demand",
            "iron-plate=120/min",
            "--accepted-input",
            "iron-ore",
            "--output",
            str(output_path),
        ]
    )

    assert status == 0
    assert "exported factory data" in capsys.readouterr().out
    package = json.loads(output_path.read_text(encoding="utf-8"))
    assert package["schema_version"] == "factory-data-v1"
    assert package["final_demands"] == {"iron-plate": 2.0}
    assert package["external_supplies"] == {"iron-ore": {"capacity": None, "cost": 1.0}}
    assert package["recipes"][0]["id"] == "iron-smelting"
