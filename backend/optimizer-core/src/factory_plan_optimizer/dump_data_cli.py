from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from factory_plan_optimizer.dump_data import DUMP_DATA_CONTEXT, DumpDataRequest
from factory_plan_optimizer.import_models import DatasetParseError

if TYPE_CHECKING:
    from collections.abc import Sequence


def parse_dump_data_request(arguments: Sequence[str]) -> DumpDataRequest:
    paths: dict[str, Path] = {}
    dry_run = False
    index = 0

    while index < len(arguments):
        flag = arguments[index]
        match flag:
            case "--factorio-bin" | "--settings" | "--mod-directory" | "--output-dir":
                paths[flag] = Path(_flag_value(arguments, index, flag))
                index += 2
            case "--dry-run":
                dry_run = True
                index += 1
            case _:
                reason = f"unknown flag {flag}"
                raise DatasetParseError(DUMP_DATA_CONTEXT, reason)

    return DumpDataRequest(
        factorio_executable=_required_path(paths, "--factorio-bin"),
        settings_path=_required_path(paths, "--settings"),
        mod_directory=_required_path(paths, "--mod-directory"),
        output_dir=_required_path(paths, "--output-dir"),
        dry_run=dry_run,
    )


def _flag_value(arguments: Sequence[str], index: int, flag: str) -> str:
    value_index = index + 1
    if value_index >= len(arguments):
        reason = f"{flag} requires a value"
        raise DatasetParseError(DUMP_DATA_CONTEXT, reason)
    value = arguments[value_index]
    if value.startswith("--"):
        reason = f"{flag} requires a value"
        raise DatasetParseError(DUMP_DATA_CONTEXT, reason)
    return value


def _required_path(paths: dict[str, Path], flag: str) -> Path:
    path = paths.get(flag)
    if path is None:
        raise DatasetParseError(DUMP_DATA_CONTEXT, f"{flag} is required")
    return path
