import json
from pathlib import Path

import pytest

from game_data_extractor.__main__ import main
from game_data_extractor.data_contracts import (
    DumpProvenance,
    ImportDiagnostic,
    ItemPrototype,
    MilestoneRecipeSet,
    OptimizerRecipeDataset,
    RecipeCoefficient,
    RecipePrototype,
    SaveSettingsProvenance,
    StartupSetting,
)


def test_report_cli_prints_deterministic_import_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_path = tmp_path / "settings.json"
    dataset_path = tmp_path / "dataset.json"
    milestone_path = tmp_path / "milestone.json"
    settings_dataset = OptimizerRecipeDataset(
        startup_settings=(StartupSetting("py-setting", "enabled"),),
        save_settings_provenance=SaveSettingsProvenance(
            save_name="py-test.zip",
            save_sha256="abc123",
            factorio_version="2.0.0",
            enabled_mods=("base", "pyalienlife"),
            warnings=("fixture settings",),
        ),
    )
    dataset = OptimizerRecipeDataset(
        items=(ItemPrototype("iron-ore", "item"), ItemPrototype("iron-plate", "item")),
        recipes=(
            RecipePrototype(
                name="iron-smelting",
                category="smelting",
                energy_required=3.2,
                coefficients=(
                    RecipeCoefficient("iron-ore", -1.0, "input"),
                    RecipeCoefficient("iron-plate", 1.0, "output"),
                ),
                enabled=True,
            ),
        ),
        startup_settings=settings_dataset.startup_settings,
        save_settings_provenance=settings_dataset.save_settings_provenance,
        diagnostics=(
            ImportDiagnostic("warning", "disabled-recipe", "disabled", "foo"),
        ),
    )
    milestone = MilestoneRecipeSet(
        "basic-circuits",
        ("iron-smelting",),
        (ImportDiagnostic("info", "recipe_missing_unlock_path", "missing", "bar"),),
    )
    settings_path.write_text(settings_dataset.to_json(), encoding="utf-8")
    dataset_path.write_text(dataset.to_json(), encoding="utf-8")
    milestone_path.write_text(json.dumps(milestone.to_json_value()), encoding="utf-8")

    status = main(
        [
            "report",
            "--settings",
            str(settings_path),
            "--dataset",
            str(dataset_path),
            "--milestone-output",
            str(milestone_path),
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "Save settings provenance:" in output
    assert "save: py-test.zip" in output
    assert "enabled mods: 2" in output
    assert "Normalized dataset counts:" in output
    assert "items: 2" in output
    assert "recipes: 1" in output
    assert "Diagnostics:" in output
    assert "warning disabled-recipe: 1" in output
    assert "Milestone recipe set:" in output
    assert "milestone: basic-circuits" in output
    assert "dataset recipes: 1" in output
    assert "milestone recipes: 1" in output
    assert "excluded recipes: 0" in output

    status = main(
        [
            "report",
            "--settings",
            str(settings_path),
            "--dataset",
            str(dataset_path),
            "--milestone-output",
            str(milestone_path),
        ]
    )
    assert status == 0
    assert capsys.readouterr().out == output


def test_report_cli_reads_new_milestone_dataset_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset_path = tmp_path / "dataset.json"
    milestone_path = tmp_path / "milestone-dataset.json"
    dataset = OptimizerRecipeDataset(
        recipes=(
            RecipePrototype("a", "crafting", 1.0, ()),
            RecipePrototype("b", "crafting", 1.0, ()),
        )
    )
    milestone_dataset = OptimizerRecipeDataset(
        recipes=(RecipePrototype("a", "crafting", 1.0, ()),),
        milestones=(MilestoneRecipeSet("m", ("a",)),),
    )
    dataset_path.write_text(dataset.to_json(), encoding="utf-8")
    milestone_path.write_text(milestone_dataset.to_json(), encoding="utf-8")

    status = main(
        [
            "report",
            "--dataset",
            str(dataset_path),
            "--milestone-output",
            str(milestone_path),
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "milestone: m" in output
    assert "milestone recipes: 1" in output
    assert "excluded recipes: 1" in output


def test_report_cli_orders_diagnostics_and_reports_dump_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset = OptimizerRecipeDataset(
        dump_provenance=DumpProvenance(
            factorio_executable="/opt/factorio/bin/x64/factorio",
            dump_path="evidence/data-raw.json",
            command=("factorio", "--dump-data"),
            dry_run=True,
        ),
        diagnostics=(
            ImportDiagnostic("warning", "z-warning", "later"),
            ImportDiagnostic("info", "a-info", "earlier"),
        ),
    )
    dataset_path.write_text(dataset.to_json(), encoding="utf-8")

    status = main(["report", "--dataset", str(dataset_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "Dump provenance:" in output
    assert "dump_path: evidence/data-raw.json" in output
    assert "command: ['factorio', '--dump-data']" in output
    assert output.index("info a-info: 1") < output.index("warning z-warning: 1")


@pytest.mark.parametrize("flag", ["--settings", "--milestone-output"])
def test_report_cli_malformed_optional_json_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    dataset_path = tmp_path / "dataset.json"
    optional_path = tmp_path / "bad.json"
    dataset_path.write_text(OptimizerRecipeDataset().to_json(), encoding="utf-8")
    optional_path.write_text("{not json", encoding="utf-8")

    status = main(["report", "--dataset", str(dataset_path), flag, str(optional_path)])

    captured = capsys.readouterr()
    assert status != 0
    assert "invalid report input JSON" in captured.err
    assert str(optional_path) in captured.err


def test_report_cli_missing_dataset_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "missing.json"

    status = main(["report", "--dataset", str(missing_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert "dataset file not found" in captured.err
    assert str(missing_path) in captured.err
