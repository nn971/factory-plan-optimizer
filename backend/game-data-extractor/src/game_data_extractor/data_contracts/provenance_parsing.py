from __future__ import annotations

from game_data_extractor.data_contracts.provenance_models import (
    DumpProvenance,
    SaveSettingsProvenance,
)
from game_data_extractor.data_contracts.types import DatasetParseError, JsonValue


def parse_save_provenance_from_optional(
    mapping: dict[str, JsonValue],
    key: str,
) -> SaveSettingsProvenance | None:
    value = mapping.get(key)
    if value is None:
        return None
    provenance = _as_mapping(value, key)
    return SaveSettingsProvenance(
        save_name=_string(provenance, "save_name"),
        save_sha256=_string(provenance, "save_sha256"),
        factorio_version=_optional_string(provenance, "factorio_version"),
        enabled_mods=_strings(provenance, "enabled_mods"),
        enabled_mod_versions=_string_mapping(provenance, "enabled_mod_versions"),
        warnings=_strings(provenance, "warnings"),
        acquisition_method=_string(
            provenance,
            "acquisition_method",
            default="save-settings-artifact",
        ),
        factorio_executable=_optional_string(provenance, "factorio_executable"),
        mod_directory=_optional_string(provenance, "mod_directory"),
    )


def parse_dump_provenance_from_optional(
    mapping: dict[str, JsonValue],
    key: str,
) -> DumpProvenance | None:
    value = mapping.get(key)
    if value is None:
        return None
    provenance = _as_mapping(value, key)
    return DumpProvenance(
        factorio_executable=_string(provenance, "factorio_executable"),
        dump_path=_string(provenance, "dump_path"),
        command=_strings(provenance, "command"),
        settings_artifact=_optional_string(provenance, "settings_artifact"),
        staged_settings_path=_optional_string(provenance, "staged_settings_path"),
        mod_directory=_optional_string(provenance, "mod_directory"),
        output_directory=_optional_string(provenance, "output_directory"),
        dry_run=_boolean(provenance, "dry_run", default=False),
        factorio_version=_optional_string(provenance, "factorio_version"),
        save_name=_optional_string(provenance, "save_name"),
        save_sha256=_optional_string(provenance, "save_sha256"),
    )


def _as_mapping(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise DatasetParseError(context, "expected JSON object")


def _strings(mapping: dict[str, JsonValue], key: str) -> list[str]:
    values = _array(mapping, key)
    strings: list[str] = []
    for value in values:
        if isinstance(value, str):
            strings.append(value)
        else:
            raise DatasetParseError(key, "expected string array")
    return strings


def _string_mapping(mapping: dict[str, JsonValue], key: str) -> dict[str, str]:
    value = mapping.get(key, {})
    nested_mapping = _as_mapping(value, key)
    strings: dict[str, str] = {}
    for nested_key, nested_value in nested_mapping.items():
        if isinstance(nested_value, str):
            strings[nested_key] = nested_value
        else:
            raise DatasetParseError(key, "expected string object")
    return strings


def _array(mapping: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = mapping.get(key, [])
    if isinstance(value, list):
        return value
    raise DatasetParseError(key, "expected JSON array")


def _string(
    mapping: dict[str, JsonValue],
    key: str,
    *,
    default: str | None = None,
) -> str:
    value = mapping.get(key, default)
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string")


def _optional_string(mapping: dict[str, JsonValue], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DatasetParseError(key, "expected string or null")


def _boolean(mapping: dict[str, JsonValue], key: str, *, default: bool) -> bool:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        return value
    raise DatasetParseError(key, "expected boolean")
