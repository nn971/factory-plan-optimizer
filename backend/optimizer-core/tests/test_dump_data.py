import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory_plan_optimizer.dump_data import (
    CommandRunResult,
    DumpDataError,
    DumpDataRequest,
    DumpDataStatus,
    acquire_factorio_dump,
)
from paths import FIXTURES_ROOT

IMPORT_SETTINGS_FIXTURES = FIXTURES_ROOT / "import_settings"
MOD_FIXTURES = FIXTURES_ROOT / "mods"


class RecordingRunner:
    def __init__(self, output_dir: Path, *, write_dump: bool) -> None:
        self.commands: list[tuple[str, ...]] = []
        self._output_dir = output_dir
        self._write_dump = write_dump

    def run(self, command: tuple[str, ...], *, cwd: Path) -> CommandRunResult:
        # Given: a test seam standing in for Factorio without invoking it.
        self.commands.append(command)
        assert cwd == self._output_dir
        if self._write_dump:
            dump_path = self._output_dir / "script-output" / "data-raw-dump.json"
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text('{"recipe": {}}\n', encoding="utf-8")
        return CommandRunResult(return_code=0, stdout="factorio stdout", stderr="")


def test_dry_run_records_deterministic_command_and_provenance(tmp_path: Path) -> None:
    # Given: an existing executable, startup settings JSON, and mod directory.
    settings_path = IMPORT_SETTINGS_FIXTURES / "minimal-settings.json"
    mod_directory = MOD_FIXTURES
    mod_directory.mkdir(exist_ok=True)
    request = DumpDataRequest(
        factorio_executable=Path("/bin/echo"),
        settings_path=settings_path,
        mod_directory=mod_directory,
        output_dir=tmp_path,
        dry_run=True,
    )

    # When: dump acquisition is prepared in dry-run mode.
    result = acquire_factorio_dump(request)

    # Then: no Factorio process is invoked and command/provenance are deterministic.
    assert result.status is DumpDataStatus.DRY_RUN
    assert result.provenance.command == (
        "/bin/echo",
        "--mod-directory",
        str(mod_directory),
        "--dump-data",
    )
    assert result.provenance.settings_artifact == str(settings_path)
    assert result.provenance.staged_settings_path == str(
        tmp_path / "save-derived-settings.json",
    )
    assert result.provenance.dump_path == str(
        tmp_path / "script-output" / "data-raw-dump.json",
    )


def test_missing_factorio_executable_fails_before_runner(tmp_path: Path) -> None:
    # Given: a request with a missing Factorio executable.
    request = DumpDataRequest(
        factorio_executable=Path("/no/such/factorio"),
        settings_path=IMPORT_SETTINGS_FIXTURES / "minimal-settings.json",
        mod_directory=MOD_FIXTURES,
        output_dir=tmp_path,
        dry_run=True,
    )

    # When / Then: the service reports a structured unavailable failure.
    with pytest.raises(DumpDataError) as error:
        acquire_factorio_dump(request)

    assert error.value.status is DumpDataStatus.ERROR
    assert error.value.code == "missing_factorio_executable"
    assert error.value.next_action == "Provide an existing Factorio executable path."


def test_non_dry_run_is_unavailable_before_runner(tmp_path: Path) -> None:
    # Given: a runner seam that must not be invoked until isolation exists.
    request = DumpDataRequest(
        factorio_executable=Path("/bin/echo"),
        settings_path=IMPORT_SETTINGS_FIXTURES / "minimal-settings.json",
        mod_directory=MOD_FIXTURES,
        output_dir=tmp_path,
        dry_run=False,
    )
    runner = RecordingRunner(tmp_path, write_dump=True)

    # When / Then: real runs fail before any Factorio invocation.
    with pytest.raises(DumpDataError) as error:
        acquire_factorio_dump(request, runner=runner)

    assert error.value.code == "factorio_dump_unavailable"
    assert error.value.status is DumpDataStatus.ERROR
    assert runner.commands == []


def test_non_dry_run_does_not_report_missing_dump(tmp_path: Path) -> None:
    # Given: a runner that would exit successfully without creating the dump.
    request = DumpDataRequest(
        factorio_executable=Path("/bin/echo"),
        settings_path=IMPORT_SETTINGS_FIXTURES / "minimal-settings.json",
        mod_directory=MOD_FIXTURES,
        output_dir=tmp_path,
        dry_run=False,
    )
    runner = RecordingRunner(tmp_path, write_dump=False)

    # When / Then: the unsupported workflow is rejected before dump validation.
    with pytest.raises(DumpDataError) as error:
        acquire_factorio_dump(request, runner=runner)

    assert error.value.code == "factorio_dump_unavailable"
    assert error.value.status is DumpDataStatus.ERROR
    assert runner.commands == []


def test_dump_provenance_includes_save_provenance_from_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "provenance": {
                    "save_name": "py-test.zip",
                    "save_sha256": "abc123",
                    "factorio_version": "2.0.0",
                }
            }
        ),
        encoding="utf-8",
    )
    request = DumpDataRequest(
        factorio_executable=Path("/bin/echo"),
        settings_path=settings_path,
        mod_directory=MOD_FIXTURES,
        output_dir=tmp_path / "dump",
        dry_run=True,
    )

    result = acquire_factorio_dump(request)

    assert result.provenance.save_name == "py-test.zip"
    assert result.provenance.save_sha256 == "abc123"
    assert result.provenance.factorio_version == "2.0.0"


def test_malformed_settings_json_fails_at_boundary(tmp_path: Path) -> None:
    # Given: a malformed startup settings JSON file.
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not json", encoding="utf-8")
    request = DumpDataRequest(
        factorio_executable=Path("/bin/echo"),
        settings_path=settings_path,
        mod_directory=MOD_FIXTURES,
        output_dir=tmp_path / "dump",
        dry_run=True,
    )

    # When / Then: settings are rejected before any Factorio invocation.
    with pytest.raises(DumpDataError) as error:
        acquire_factorio_dump(request)

    assert error.value.code == "malformed_settings_json"


def test_cli_dump_data_dry_run_prints_json(tmp_path: Path) -> None:
    # Given: the real CLI dump-data surface in dry-run mode.
    output_dir = tmp_path / "dump"

    # When: the command is driven through python -m.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory_plan_optimizer",
            "dump-data",
            "--factorio-bin",
            "/bin/echo",
            "--settings",
            str(IMPORT_SETTINGS_FIXTURES / "minimal-settings.json"),
            "--mod-directory",
            str(MOD_FIXTURES),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: stdout is deterministic machine-readable provenance.
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "dry_run"
    assert payload["provenance"]["command"][3] == "--dump-data"
    assert payload["provenance"]["mod_directory"] == str(MOD_FIXTURES)


def test_cli_dump_data_missing_executable_exits_nonzero(tmp_path: Path) -> None:
    # Given: the real CLI dump-data surface with a missing executable.
    output_dir = tmp_path / "dump"

    # When: the command is invoked with an unavailable Factorio path.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory_plan_optimizer",
            "dump-data",
            "--factorio-bin",
            "/no/such/factorio",
            "--settings",
            str(IMPORT_SETTINGS_FIXTURES / "minimal-settings.json"),
            "--mod-directory",
            str(MOD_FIXTURES),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: the failure is structured and cannot be mistaken for success.
    assert completed.returncode == 1
    payload = json.loads(completed.stderr)
    assert payload["status"] == "error"
    assert payload["code"] == "missing_factorio_executable"
