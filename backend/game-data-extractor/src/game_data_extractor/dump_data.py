from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from game_data_extractor.data_contracts import DumpProvenance

if TYPE_CHECKING:
    from game_data_extractor.data_contracts import JsonValue

DUMP_DATA_CONTEXT = "dump-data"
DUMP_FILE = Path("script-output") / "data-raw-dump.json"
STAGED_SETTINGS_FILE = "save-derived-settings.json"


class DumpDataStatus(StrEnum):
    DRY_RUN = "dry_run"
    DUMPED = "dumped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DumpDataRequest:
    factorio_executable: Path
    settings_path: Path
    mod_directory: Path
    output_dir: Path
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class CommandRunResult:
    return_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...], *, cwd: Path) -> CommandRunResult: ...


@dataclass(frozen=True, slots=True)
class SubprocessCommandRunner:
    def run(self, command: tuple[str, ...], *, cwd: Path) -> CommandRunResult:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        return CommandRunResult(
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class DumpDataResult:
    status: DumpDataStatus
    provenance: DumpProvenance
    message: str

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "provenance": self.provenance.to_json_value(),
            "status": self.status.value,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class DumpDataError(Exception):
    status: DumpDataStatus
    code: str
    message: str
    next_action: str
    request: DumpDataRequest

    def __str__(self) -> str:
        return f"{self.code}: {self.message} Next action: {self.next_action}"

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
            "output_dir": str(self.request.output_dir),
            "status": self.status.value,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


def acquire_factorio_dump(
    request: DumpDataRequest,
    *,
    runner: CommandRunner | None = None,
) -> DumpDataResult:
    _validate_request_inputs(request)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    staged_settings_path = request.output_dir / STAGED_SETTINGS_FILE
    shutil.copyfile(request.settings_path, staged_settings_path)
    provenance = _build_provenance(request, staged_settings_path)

    if request.dry_run:
        return DumpDataResult(
            status=DumpDataStatus.DRY_RUN,
            provenance=provenance,
            message="Prepared Factorio --dump-data command without running it.",
        )

    raise DumpDataError(
        status=DumpDataStatus.ERROR,
        code="factorio_dump_unavailable",
        message=(
            "Non-dry-run dump-data is unavailable until an isolated Factorio "
            "settings workflow exists."
        ),
        next_action=(
            "Use --dry-run and run Factorio --dump-data manually in an isolated "
            "environment."
        ),
        request=request,
    )

    command_runner = SubprocessCommandRunner() if runner is None else runner
    completed = command_runner.run(tuple(provenance.command), cwd=request.output_dir)
    if completed.return_code != 0:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="factorio_dump_failed",
            message=f"Factorio exited with status {completed.return_code}.",
            next_action="Inspect Factorio stdout/stderr and rerun the dump command.",
            request=request,
        )

    _validate_dump_file(request.output_dir / DUMP_FILE, request)
    return DumpDataResult(
        status=DumpDataStatus.DUMPED,
        provenance=provenance,
        message="Factorio data.raw dump was created and validated.",
    )


def _validate_request_inputs(request: DumpDataRequest) -> None:
    if not request.factorio_executable.is_file() or not os.access(
        request.factorio_executable,
        os.X_OK,
    ):
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="missing_factorio_executable",
            message=(
                f"Factorio executable is unavailable: {request.factorio_executable}"
            ),
            next_action="Provide an existing Factorio executable path.",
            request=request,
        )
    if not request.mod_directory.is_dir():
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="missing_mod_directory",
            message=f"Mod directory is unavailable: {request.mod_directory}",
            next_action="Provide an existing Factorio mod directory.",
            request=request,
        )
    _validate_settings_json(request.settings_path, request)


def _validate_settings_json(settings_path: Path, request: DumpDataRequest) -> None:
    try:
        text = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="missing_settings_json",
            message=f"Startup settings JSON is unavailable: {settings_path}",
            next_action="Provide a readable startup settings JSON file.",
            request=request,
        ) from error
    except OSError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="unreadable_settings_json",
            message=f"Could not read startup settings JSON: {error}",
            next_action="Fix permissions or provide a readable settings JSON path.",
            request=request,
        ) from error

    try:
        parsed: JsonValue = json.loads(text)
    except JSONDecodeError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="malformed_settings_json",
            message=f"Startup settings JSON is malformed: {error.msg}",
            next_action="Fix or regenerate the startup settings JSON file.",
            request=request,
        ) from error
    if not isinstance(parsed, dict):
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="malformed_settings_json",
            message="Startup settings JSON must be an object.",
            next_action="Fix or regenerate the startup settings JSON file.",
            request=request,
        )


def _settings_json(settings_path: Path) -> dict[str, JsonValue]:
    text = settings_path.read_text(encoding="utf-8")
    parsed: JsonValue = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _build_provenance(
    request: DumpDataRequest,
    staged_settings_path: Path,
) -> DumpProvenance:
    settings = _settings_json(request.settings_path)
    provenance = settings.get("provenance")
    save_provenance = provenance if isinstance(provenance, dict) else settings
    save_name = save_provenance.get("save_name")
    save_sha256 = save_provenance.get("save_sha256")
    factorio_version = save_provenance.get("factorio_version")
    return DumpProvenance(
        factorio_executable=str(request.factorio_executable),
        dump_path=str(request.output_dir / DUMP_FILE),
        command=(
            str(request.factorio_executable),
            "--mod-directory",
            str(request.mod_directory),
            "--dump-data",
        ),
        settings_artifact=str(request.settings_path),
        staged_settings_path=str(staged_settings_path),
        mod_directory=str(request.mod_directory),
        output_directory=str(request.output_dir),
        dry_run=request.dry_run,
        factorio_version=(
            factorio_version if isinstance(factorio_version, str) else None
        ),
        save_name=save_name if isinstance(save_name, str) else None,
        save_sha256=save_sha256 if isinstance(save_sha256, str) else None,
    )


def _validate_dump_file(dump_path: Path, request: DumpDataRequest) -> None:
    try:
        text = dump_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="missing_data_raw_dump",
            message=f"Expected dump was not created: {dump_path}",
            next_action=(
                "Check Factorio script-output location and dump command output."
            ),
            request=request,
        ) from error
    except OSError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="unreadable_data_raw_dump",
            message=f"Could not read expected dump: {error}",
            next_action="Fix permissions on the Factorio script-output directory.",
            request=request,
        ) from error

    try:
        parsed: JsonValue = json.loads(text)
    except JSONDecodeError as error:
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="malformed_data_raw_dump",
            message=f"Factorio data.raw dump is malformed JSON: {error.msg}",
            next_action="Rerun Factorio --dump-data and inspect script-output.",
            request=request,
        ) from error
    if not isinstance(parsed, dict):
        raise DumpDataError(
            status=DumpDataStatus.ERROR,
            code="malformed_data_raw_dump",
            message="Factorio data.raw dump must be a JSON object.",
            next_action="Rerun Factorio --dump-data and inspect script-output.",
            request=request,
        )
