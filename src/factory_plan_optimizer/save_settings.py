from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError
from typing import TYPE_CHECKING, Protocol
from zipfile import BadZipFile, ZipFile

from factory_plan_optimizer.import_models import (
    DatasetParseError,
    JsonValue,
    SaveSettingsProvenance,
    StartupSetting,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path


SETTINGS_MEMBER = "save-settings.json"


class SaveSettingsStatus(StrEnum):
    EXTRACTED = "extracted"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SaveSettingsExtractionRequest:
    save_path: Path
    factorio_executable: Path | None = None
    mod_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class SaveSettingsExtractionResult:
    status: SaveSettingsStatus
    startup_settings: Sequence[StartupSetting]
    provenance: SaveSettingsProvenance
    message: str
    next_action: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "startup_settings", tuple(self.startup_settings))

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "next_action": self.next_action,
            "provenance": self.provenance.to_json_value(),
            "startup_settings": [
                setting.to_json_value() for setting in self.startup_settings
            ],
            "status": self.status.value,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class SaveSettingsExtractionError(Exception):
    status: SaveSettingsStatus
    code: str
    message: str
    next_action: str
    save_path: Path

    def __str__(self) -> str:
        return f"{self.code}: {self.message} Next action: {self.next_action}"

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
            "save_path": str(self.save_path),
            "status": self.status.value,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_value(), indent=2, sort_keys=True) + "\n"


class SaveModSettingsExtractor(Protocol):
    def extract(
        self,
        save_path: Path,
        *,
        factorio_executable: Path | None = None,
        mod_directory: Path | None = None,
    ) -> SaveSettingsExtractionResult: ...


@dataclass(frozen=True, slots=True)
class FixtureSaveModSettingsExtractor:
    settings_member: str = SETTINGS_MEMBER

    def extract(
        self,
        save_path: Path,
        *,
        factorio_executable: Path | None = None,
        mod_directory: Path | None = None,
    ) -> SaveSettingsExtractionResult:
        if not save_path.exists():
            raise SaveSettingsExtractionError(
                status=SaveSettingsStatus.ERROR,
                code="missing_save",
                message=f"Save file does not exist: {save_path}",
                next_action="Provide an existing Factorio save path via --save.",
                save_path=save_path,
            )

        try:
            with ZipFile(save_path) as save_zip:
                raw_settings = save_zip.read(self.settings_member)
        except KeyError as error:
            raise SaveSettingsExtractionError(
                status=SaveSettingsStatus.UNAVAILABLE,
                code="settings_artifact_unavailable",
                message=f"Save does not contain {self.settings_member}.",
                next_action=(
                    "Run a supported Factorio save/settings sync workflow, then "
                    f"include {self.settings_member} in the save fixture."
                ),
                save_path=save_path,
            ) from error
        except BadZipFile as error:
            raise SaveSettingsExtractionError(
                status=SaveSettingsStatus.ERROR,
                code="invalid_save_archive",
                message=f"Save is not a readable zip archive: {save_path}",
                next_action="Provide a valid Factorio save zip via --save.",
                save_path=save_path,
            ) from error

        return _result_from_settings_artifact(
            raw_settings,
            request=SaveSettingsExtractionRequest(
                save_path=save_path,
                factorio_executable=factorio_executable,
                mod_directory=mod_directory,
            ),
        )


def _result_from_settings_artifact(
    raw_settings: bytes,
    *,
    request: SaveSettingsExtractionRequest,
) -> SaveSettingsExtractionResult:
    try:
        parsed: JsonValue = json.loads(raw_settings.decode("utf-8"))
        mapping = _mapping(parsed, "save settings artifact")
        enabled_mod_versions = _enabled_mod_versions(mapping)
        settings = _startup_settings(mapping)
        warnings = _strings(mapping, "warnings")
    except (UnicodeDecodeError, JSONDecodeError, DatasetParseError) as error:
        raise SaveSettingsExtractionError(
            status=SaveSettingsStatus.ERROR,
            code="malformed_settings_artifact",
            message=f"{SETTINGS_MEMBER} is malformed: {error}",
            next_action=(
                "Regenerate the save-derived startup settings artifact from the "
                "source save."
            ),
            save_path=request.save_path,
        ) from error

    provenance = SaveSettingsProvenance(
        save_name=request.save_path.name,
        save_sha256=_sha256(request.save_path),
        factorio_version=_optional_string(mapping, "factorio_version"),
        enabled_mods=tuple(enabled_mod_versions),
        enabled_mod_versions=enabled_mod_versions,
        warnings=warnings,
        factorio_executable=None
        if request.factorio_executable is None
        else str(request.factorio_executable),
        mod_directory=None
        if request.mod_directory is None
        else str(request.mod_directory),
    )
    return SaveSettingsExtractionResult(
        status=SaveSettingsStatus.EXTRACTED,
        startup_settings=settings,
        provenance=provenance,
        message="Extracted save-derived startup settings artifact.",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise DatasetParseError(context, "expected JSON object")


def _enabled_mod_versions(mapping: Mapping[str, JsonValue]) -> dict[str, str]:
    mods = _array(mapping, "enabled_mods")
    versions: dict[str, str] = {}
    for mod in mods:
        mod_mapping = _mapping(mod, "enabled mod")
        versions[_string(mod_mapping, "name")] = _string(mod_mapping, "version")
    return dict(sorted(versions.items()))


def _startup_settings(mapping: Mapping[str, JsonValue]) -> tuple[StartupSetting, ...]:
    settings = [
        StartupSetting(
            name=_string(setting_mapping, "name"),
            value=_string(setting_mapping, "value"),
            setting_type=_string(setting_mapping, "setting_type"),
        )
        for setting_mapping in (
            _mapping(setting, "startup setting")
            for setting in _array(mapping, "startup_settings")
        )
    ]
    return tuple(sorted(settings, key=lambda setting: setting.name))


def _array(mapping: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    value = mapping.get(key, [])
    if isinstance(value, list):
        return value
    raise DatasetParseError(key, "expected JSON array")


def _strings(mapping: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    strings: list[str] = []
    for value in _array(mapping, key):
        if isinstance(value, str):
            strings.append(value)
        else:
            raise DatasetParseError(key, "expected string array")
    return tuple(sorted(strings))


def _string(mapping: Mapping[str, JsonValue], key: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string")


def _optional_string(mapping: Mapping[str, JsonValue], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string or null")
