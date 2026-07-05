import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory_plan_optimizer.save_settings import (
    FixtureSaveModSettingsExtractor,
    SaveSettingsExtractionError,
    SaveSettingsStatus,
)

SHA256_HEX_LENGTH = 64
MISSING_SAVE_NEXT_ACTION = "Provide an existing Factorio save path via --save."


def test_extracts_fixture_save_settings_with_deterministic_provenance() -> None:
    # Given: a synthetic save zip containing a save-derived settings artifact.
    save_path = Path("tests/fixtures/save_settings/minimal-save.zip")
    extractor = FixtureSaveModSettingsExtractor()

    # When: the artifact is extracted through the save settings boundary.
    result = extractor.extract(save_path)

    # Then: startup settings, mod versions, save identity, and warnings are stable.
    assert result.status is SaveSettingsStatus.EXTRACTED
    assert [setting.name for setting in result.startup_settings] == [
        "toy-overhaul-enable-byproducts",
        "toy-overhaul-ore-richness",
    ]
    assert result.provenance.save_name == "minimal-save.zip"
    assert result.provenance.enabled_mods == ("base", "toy-overhaul")
    assert result.provenance.enabled_mod_versions == {
        "base": "1.1.110",
        "toy-overhaul": "0.2.0",
    }
    assert result.provenance.factorio_version == "1.1.110"
    assert result.provenance.warnings == (
        "synthetic fixture: not a real Factorio save",
    )
    assert len(result.provenance.save_sha256) == SHA256_HEX_LENGTH


def test_missing_save_path_fails_with_exact_next_action() -> None:
    # Given: a save path that does not exist.
    save_path = Path("tests/fixtures/save_settings/missing.zip")
    extractor = FixtureSaveModSettingsExtractor()

    # When / Then: extraction fails with a structured next action.
    with pytest.raises(SaveSettingsExtractionError) as error:
        extractor.extract(save_path)

    assert error.value.status is SaveSettingsStatus.ERROR
    assert error.value.next_action == MISSING_SAVE_NEXT_ACTION


def test_malformed_settings_member_fails_at_boundary() -> None:
    # Given: a synthetic save with an invalid settings artifact shape.
    save_path = Path("tests/fixtures/save_settings/malformed-save.zip")
    extractor = FixtureSaveModSettingsExtractor()

    # When / Then: invalid member data is rejected before optimizer models see it.
    with pytest.raises(SaveSettingsExtractionError) as error:
        extractor.extract(save_path)

    assert error.value.status is SaveSettingsStatus.ERROR
    assert error.value.code == "malformed_settings_artifact"


def test_cli_writes_settings_json_for_fixture_save(tmp_path: Path) -> None:
    # Given: the real CLI surface and a synthetic save zip.
    output_path = tmp_path / "settings.json"
    save_path = Path("tests/fixtures/save_settings/minimal-save.zip")

    # When: the extract-save-settings command is driven through the module CLI.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory_plan_optimizer",
            "extract-save-settings",
            "--save",
            str(save_path),
            "--output",
            str(output_path),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: it exits cleanly and writes deterministic JSON with provenance.
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "extracted"
    assert payload["provenance"]["save_name"] == "minimal-save.zip"
    assert payload["startup_settings"][0]["name"] == ("toy-overhaul-enable-byproducts")


def test_cli_missing_save_writes_structured_failure(tmp_path: Path) -> None:
    # Given: the real CLI surface and a missing save path.
    output_path = tmp_path / "missing.json"

    # When: extraction is requested for the missing save.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory_plan_optimizer",
            "extract-save-settings",
            "--save",
            "tests/fixtures/save_settings/missing.zip",
            "--output",
            str(output_path),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: the command fails loudly while still writing machine-readable status.
    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["next_action"] == MISSING_SAVE_NEXT_ACTION
